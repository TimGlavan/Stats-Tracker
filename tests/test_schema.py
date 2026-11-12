import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).parents[1]


def load_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text())


def schema_validator() -> Draft202012Validator:
    schema = load_json("schemas/game_export_v1.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_valid_game_export_matches_version_1_schema() -> None:
    errors = list(
        schema_validator().iter_errors(load_json("examples/valid_game_export_v1.json"))
    )

    assert errors == []


def test_non_shooting_outcome_fixture_is_rejected_by_schema() -> None:
    errors = list(
        schema_validator().iter_errors(
            load_json("examples/invalid_game_export_v1_nonshooting_outcome.json")
        )
    )

    assert errors
