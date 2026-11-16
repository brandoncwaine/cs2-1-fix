import json

from onefix.publish import publish, summary, write_data


def _match(match_id: str, rounds: int) -> dict:
    return {"match_id": match_id, "map": "de_mirage", "date": "",
            "rounds": [{"num": i + 1, "side": "T", "won": i % 2 == 0, "kills": []} for i in range(rounds)]}


def _fake_parser(rounds_by_demo: dict):
    calls = []

    def parse(demo, steamid, out_dir):
        calls.append((demo.name, steamid))
        if demo.stem not in rounds_by_demo:
            return False
        (out_dir / f"{demo.stem}.json").write_text(json.dumps(_match(demo.stem, rounds_by_demo[demo.stem])))
        return True

    return parse, calls


MANIFEST = {"players": [
    {"steamid": "1", "name": "Ann", "demos": ["/d/m1.dem", "/d/m2.dem", "/d/broken.dem"],
     "expired": 2, "failed": 1, "history_error": None},
    {"steamid": "2", "name": "Bob", "demos": [], "expired": 0, "failed": 0, "history_error": "403"},
]}


def test_each_player_is_parsed_into_their_own_folder_and_gets_cards(tmp_path):
    parse, calls = _fake_parser({"m1": 20, "m2": 15})
    data = publish(MANIFEST, tmp_path, "2026-11-16T06:00:00Z", parse)
    assert data["synced_at"] == "2026-11-16T06:00:00Z"
    ann, bob = data["players"]
    assert (ann["matches"], ann["rounds"]) == (2, 35)
    assert [(c["map"], c["side"], c["status"]) for c in ann["cards"]] == [("de_mirage", "T", "no_fix_found")]
    assert ann["problems"] == {"history_error": None, "fetch_failed": 1, "expired": 2, "parse_failed": 1}
    assert (tmp_path / "1" / "m1.json").exists()
    assert (bob["matches"], bob["cards"], bob["problems"]["history_error"]) == (0, [], "403")
    assert {c[1] for c in calls} == {"1"}


def test_already_parsed_demos_are_not_parsed_again(tmp_path):
    parse, calls = _fake_parser({"m1": 20, "m2": 15})
    publish(MANIFEST, tmp_path, "t", parse)
    first = len(calls)
    data = publish(MANIFEST, tmp_path, "t", parse)
    assert [c[0] for c in calls[first:]] == ["broken.dem"]  # only the failure is retried
    assert data["players"][0]["matches"] == 2


def test_parsed_matches_still_count_after_the_demo_file_is_gone(tmp_path):
    parse, _ = _fake_parser({"m1": 20, "m2": 15})
    publish(MANIFEST, tmp_path, "t", parse)
    later = {"players": [{**MANIFEST["players"][0], "demos": []}]}
    assert publish(later, tmp_path, "t", parse)["players"][0]["rounds"] == 35


def test_data_file_is_written_whole_and_summarised(tmp_path):
    parse, _ = _fake_parser({"m1": 20, "m2": 15})
    data = publish(MANIFEST, tmp_path / "parsed", "t", parse)
    dest = write_data(data, tmp_path / "web")
    assert json.loads(dest.read_text()) == data
    assert not (tmp_path / "web" / "data.json.tmp").exists()
    assert "Ann: 2 match(es), 35 rounds; 1 no_fix_found" in summary(data)
