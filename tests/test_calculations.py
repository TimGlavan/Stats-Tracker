import json
from pathlib import Path

from stats_tracker.calculations import calculate_box_score
from stats_tracker.models import game_export_from_dict


ROOT = Path(__file__).parents[1]


def load_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text())


def fixture_rosters() -> dict[str, set[str]]:
    return {
        "team-home": {"player-home-01", "player-home-02"},
        "team-away": {"player-away-01"},
    }


def test_calculation_matches_expected_box_score_fixture() -> None:
    game_export = game_export_from_dict(load_json("examples/valid_game_export_v1.json"))
    expected = load_json("examples/valid_game_export_v1_expected_box_score.json")
    expected.pop("source_file")

    result = calculate_box_score(game_export, fixture_rosters())

    assert result.to_dict() == expected


def test_rostered_player_with_no_events_has_a_zero_stat_line() -> None:
    game_export = game_export_from_dict(load_json("examples/valid_game_export_v1.json"))
    rosters = fixture_rosters()
    rosters["team-home"].add("player-home-03")

    result = calculate_box_score(game_export, rosters)
    player = next(
        box_score
        for box_score in result.player_box_scores
        if box_score.player_id == "player-home-03"
    )

    assert player.participated is False
    assert player.games_played == 0
    assert player.totals.points == 0
    assert player.totals.two_point_percentage is None
    assert player.totals.field_goal_percentage is None
