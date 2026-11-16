import json

from builders import ME, half
from onefix import cards
from onefix.models import match_from_dict


def load(*ms):
    return [match_from_dict(m) for m in ms]


def three_halves(iso=((1, 2), (3, 4), (5,)), **kw):
    return load(*(half(f"m{i}", iso_rounds=r, date=f"2026-11-0{i}", **kw)
                  for i, r in enumerate(iso, start=1)))


def test_fix_card_for_repeated_pattern():
    (card,) = cards.build_cards(three_halves(), ME)
    assert card["status"] == "fix"
    assert (card["map"], card["side"], card["place"]) == ("de_mirage", "T", "Palace")
    assert card["stats"]["fired_rounds"] == 5
    assert card["side_rounds"] == 36
    assert card["metric"]["baseline"] == 13.9
    assert card["metric"]["target"] == 7.0
    assert "5 of 36 rounds" in card["fix_text"]
    # The advice on its own (shown behind "How to fix it") is the end of the fix text.
    assert card["advice"].startswith("Stop taking first contact at Palace alone")
    assert card["fix_text"].endswith(card["advice"])


def test_evidence_links_to_real_rounds_most_recent_first():
    (card,) = cards.build_cards(three_halves(), ME)
    assert [(e["match_id"], e["round"]) for e in card["evidence"]] == [
        ("m3", 5), ("m2", 4), ("m2", 3)]


def test_thin_data_refuses():
    (card,) = cards.build_cards(load(half("m1", iso_rounds=(1, 2, 3, 4, 5))), ME)
    assert card["status"] == "insufficient_data"
    assert card["rounds_needed"] == 18
    assert "fix_text" not in card


def test_pattern_in_single_match_is_not_enough():
    (card,) = cards.build_cards(three_halves(iso=((1, 2, 3, 4, 5), (), ())), ME)
    assert card["status"] == "no_fix_found"


def test_too_few_fired_rounds_is_not_enough():
    (card,) = cards.build_cards(three_halves(iso=((1,), (2,), (3,))), ME)
    assert card["status"] == "no_fix_found"


def test_no_fix_when_pattern_does_not_cost_rounds():
    # Other rounds are all lost too, so the pattern shows no observed cost.
    (card,) = cards.build_cards(three_halves(clean_won=False), ME)
    assert card["status"] == "no_fix_found"


def test_one_card_per_map_side_and_highest_cost_wins():
    ms = three_halves() + load(
        half("m4", iso_rounds=(1, 2, 3), place="Apps", date="2026-11-04"),
        half("m5", iso_rounds=(1, 2, 3, 4), place="Apps", date="2026-11-05"),
        half("m6", side="CT", date="2026-11-06"),
    )
    out = cards.build_cards(ms, ME)
    assert [(c["side"], c["status"]) for c in out] == [
        ("CT", "insufficient_data"), ("T", "fix")]
    assert out[1]["place"] == "Apps"


def test_output_is_deterministic_and_order_independent():
    ms = three_halves()
    a = json.dumps(cards.build_cards(ms, ME), sort_keys=True)
    b = json.dumps(cards.build_cards(list(reversed(ms)), ME), sort_keys=True)
    assert a == b


def test_recheck_statuses():
    (card,) = cards.build_cards(three_halves(), ME)
    new = lambda iso: load(half("n1", iso_rounds=iso, date="2026-12-01"),
                           half("n2", date="2026-12-02"))
    assert cards.recheck(card, new(()), ME)["status"] == "fixed"
    assert cards.recheck(card, new((1, 2)), ME)["status"] == "improving"
    assert cards.recheck(card, new((1, 2, 3, 4)), ME)["status"] == "no_change"
    thin = cards.recheck(card, load(half("n1", date="2026-12-01")), ME)
    assert thin["status"] == "insufficient_data"


def test_recheck_ignores_other_maps():
    (card,) = cards.build_cards(three_halves(), ME)
    other = load(half("n1", map_="de_nuke"), half("n2", map_="de_nuke"))
    assert cards.recheck(card, other, ME)["status"] == "insufficient_data"
