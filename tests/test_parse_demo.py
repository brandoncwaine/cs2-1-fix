"""Parser tests on a real, public HLTV demo kept outside git.

The demo is `bluejays-vs-incontrol-m1-mirage.dem` from the Hugging Face dataset
`aldigobbler/cs2demos` (see docs/HANDOFF.md). Download it with:

    curl -L -o <dir>/bluejays-vs-incontrol-m1-mirage.dem \
      https://huggingface.co/datasets/aldigobbler/cs2demos/resolve/main/bluejays-vs-incontrol-m1-mirage.dem

and point ONEFIX_DEMO_DIR at <dir> (default: ~/Documents/cs2-demos/hf-aldigobbler).
Skipped when the demo or demoparser2 is missing. No Steam IDs are hard-coded: the analysed
player is picked from the demo itself.
"""
import os
from pathlib import Path

import pytest

demoparser2 = pytest.importorskip("demoparser2")

from onefix import parse_demo  # noqa: E402
from onefix.models import match_from_dict  # noqa: E402

DEMO_DIR = Path(os.environ.get("ONEFIX_DEMO_DIR", "~/Documents/cs2-demos/hf-aldigobbler")).expanduser()
DEMO = DEMO_DIR / "bluejays-vs-incontrol-m1-mirage.dem"
pytestmark = pytest.mark.skipif(not DEMO.exists(), reason=f"real demo not found: {DEMO}")


@pytest.fixture(scope="module")
def player():
    """Lowest steamid on the team that starts CT (deterministic, nothing hard-coded)."""
    p = demoparser2.DemoParser(str(DEMO))
    first = int(p.parse_event("round_freeze_end")["tick"].min())
    df = p.parse_ticks(["team_name"], ticks=[first])
    return min(str(s) for s in df[df["team_name"] == "CT"]["steamid"])


@pytest.fixture(scope="module")
def parsed(player):
    return parse_demo.demo_to_match(DEMO, player)


def test_round_count_ignores_junk_round_end_before_match(parsed):
    # The demo has 17 round_end events; the first (tick 6, no winner) precedes round 1.
    assert parsed["map"] == "de_mirage"
    assert [r["num"] for r in parsed["rounds"]] == list(range(1, 17))


def test_sides_switch_at_half(parsed):
    assert [r["side"] for r in parsed["rounds"]] == ["CT"] * 12 + ["T"] * 4


def test_result_is_13_3(parsed):
    assert sum(r["won"] for r in parsed["rounds"]) == 13


def test_kills_are_well_formed(parsed, player):
    for r in parsed["rounds"]:
        per_side = {"T": 0, "CT": 0}
        for k in sorted(r["kills"], key=lambda k: k["t"]):
            assert 0 <= k["t"] <= 115 + 40 + 10  # round time + bomb timer + slack
            assert k["victim_side"] in ("T", "CT")
            assert k["attacker_side"] in ("T", "CT", None)
            assert k["place"] and len(k["pos"]) == 3
            # Living teammates never exceed 4, and shrink as the side loses players.
            assert len(k["victim_teammates_alive"]) <= 4 - per_side[k["victim_side"]]
            per_side[k["victim_side"]] += 1
        assert per_side["T"] <= 5 and per_side["CT"] <= 5


def test_player_dies_in_some_rounds(parsed, player):
    deaths = [k for r in parsed["rounds"] for k in r["kills"] if k["victim"] == player]
    assert 0 < len(deaths) <= len(parsed["rounds"])


def test_own_position_is_written_only_while_the_player_is_alive(parsed, player):
    assert parsed["schema"] == 2
    kills = [k for r in parsed["rounds"] for k in r["kills"]]
    assert all(k["player_pos"] is None and k["player_place"] is None
               for k in kills if k["victim"] == player)
    known = [k for k in kills if k["player_pos"] is not None]
    assert known and all(len(k["player_pos"]) == 3 and k["player_place"] for k in known)
    # Alive at the kill tick means not yet dead this round.
    for r in parsed["rounds"]:
        died = min((k["t"] for k in r["kills"] if k["victim"] == player), default=1e9)
        assert all(k["t"] <= died for k in r["kills"] if k["player_pos"] is not None)


def test_tickrate_matches_round_timer():
    # A round that ends on time lasts the 115 s round timer; at TICKRATE that is 7360 ticks.
    p = demoparser2.DemoParser(str(DEMO))
    freeze = sorted(int(t) for t in p.parse_event("round_freeze_end")["tick"])
    ends = p.parse_event("round_end")
    timeouts = ends[ends["reason"] == "time_ran_out"]["tick"]
    assert len(timeouts) > 0
    for end in timeouts:
        start = max(f for f in freeze if f < int(end))
        assert (int(end) - start) / parse_demo.TICKRATE == pytest.approx(115, abs=1)


def test_output_loads_into_schema_and_is_deterministic(parsed, player):
    m = match_from_dict(parsed)
    assert len(m.rounds) == 16
    assert parse_demo.demo_to_match(DEMO, player) == parsed
