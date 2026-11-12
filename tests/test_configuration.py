import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from stats_tracker.configuration import (
    load_tournament_configuration,
    tournament_configuration_from_dict,
)
from stats_tracker.models import game_export_from_dict
from stats_tracker.validation import validate_game_export


ROOT = Path(__file__).parents[1]


def load_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text())


def test_configuration_round_trips_and_builds_validation_context() -> None:
    configuration = load_tournament_configuration(
        ROOT / "examples/tournament_configuration_v1.json"
    )

    assert configuration.to_dict() == load_json("examples/tournament_configuration_v1.json")
    assert configuration.rosters == {
        "team-home": frozenset(
            {"player-home-01", "player-home-02", "player-home-03"}
        ),
        "team-away": frozenset({"player-away-01"}),
    }

    game_export = game_export_from_dict(load_json("examples/valid_game_export_v1.json"))
    assert validate_game_export(
        game_export, configuration.to_validation_context()
    ).is_accepted


def test_configuration_matches_its_json_schema() -> None:
    schema = load_json("schemas/tournament_configuration_v1.schema.json")
    configuration = load_json("examples/tournament_configuration_v1.json")

    assert list(Draft202012Validator(schema).iter_errors(configuration)) == []


def test_player_id_must_be_unique_across_the_tournament() -> None:
    payload = load_json("examples/tournament_configuration_v1.json")
    teams = payload["teams"]
    assert isinstance(teams, list)
    second_team = teams[1]
    assert isinstance(second_team, dict)
    players = second_team["players"]
    assert isinstance(players, list)
    second_player = players[0]
    assert isinstance(second_player, dict)
    second_player["player_id"] = "player-home-01"

    with pytest.raises(ValueError, match="unique within a tournament"):
        tournament_configuration_from_dict(payload)


def test_schema_rejects_numeric_jersey_number() -> None:
    payload = load_json("examples/tournament_configuration_v1.json")
    teams = payload["teams"]
    assert isinstance(teams, list)
    first_team = teams[0]
    assert isinstance(first_team, dict)
    players = first_team["players"]
    assert isinstance(players, list)
    first_player = players[0]
    assert isinstance(first_player, dict)
    first_player["jersey_number"] = 4

    schema = load_json("schemas/tournament_configuration_v1.schema.json")
    assert list(Draft202012Validator(schema).iter_errors(payload))
