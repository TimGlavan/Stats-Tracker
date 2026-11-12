import json
from dataclasses import replace
from pathlib import Path

from stats_tracker.models import EventVoidedEvent, GameExport, game_export_from_dict
from stats_tracker.validation import (
    TournamentValidationContext,
    ValidationCode,
    validate_game_export,
)


ROOT = Path(__file__).parents[1]


def valid_export() -> GameExport:
    payload = json.loads((ROOT / "examples/valid_game_export_v1.json").read_text())
    return game_export_from_dict(payload)


def validation_context() -> TournamentValidationContext:
    return TournamentValidationContext(
        tournament_id="tournament-2026",
        configuration_version=1,
        rosters={
            "team-home": frozenset(
                {"player-home-01", "player-home-02", "player-home-03"}
            ),
            "team-away": frozenset({"player-away-01"}),
        },
    )


def validation_codes(game_export: GameExport) -> set[ValidationCode]:
    result = validate_game_export(game_export, validation_context())
    return {issue.code for issue in result.issues}


def test_valid_fixture_is_accepted() -> None:
    result = validate_game_export(valid_export(), validation_context())

    assert result.is_accepted
    assert result.issues == ()


def test_duplicate_event_id_is_rejected() -> None:
    game_export = valid_export()
    duplicate = replace(game_export.events[1], event_id=game_export.events[0].event_id)
    invalid_export = replace(
        game_export, events=(game_export.events[0], duplicate, *game_export.events[2:])
    )

    assert ValidationCode.DUPLICATE_EVENT_ID in validation_codes(invalid_export)


def test_player_must_belong_to_the_event_team() -> None:
    game_export = valid_export()
    stat_event = replace(game_export.events[3], player_id="player-away-01")
    invalid_export = replace(
        game_export, events=(*game_export.events[:3], stat_event, *game_export.events[4:])
    )

    assert ValidationCode.PLAYER_NOT_ON_TEAM in validation_codes(invalid_export)


def test_void_can_target_an_earlier_active_statistic() -> None:
    game_export = valid_export()
    undo_event = game_export.events[8]
    assert isinstance(undo_event, EventVoidedEvent)
    invalid_undo = replace(undo_event, target_event_id=game_export.events[3].event_id)
    invalid_export = replace(
        game_export, events=(*game_export.events[:8], invalid_undo, *game_export.events[9:])
    )

    assert validation_codes(invalid_export) == set()


def test_void_cannot_target_a_participation_event() -> None:
    game_export = valid_export()
    void_event = game_export.events[8]
    assert isinstance(void_event, EventVoidedEvent)
    invalid_void = replace(void_event, target_event_id=game_export.events[0].event_id)
    invalid_export = replace(
        game_export, events=(*game_export.events[:8], invalid_void, *game_export.events[9:])
    )

    assert ValidationCode.VOID_TARGET_INVALID_TYPE in validation_codes(invalid_export)


def test_effective_stat_requires_participation_marker() -> None:
    game_export = valid_export()
    stat_event = replace(game_export.events[3], player_id="player-home-03")
    invalid_export = replace(
        game_export, events=(*game_export.events[:3], stat_event, *game_export.events[4:])
    )

    assert ValidationCode.STAT_WITHOUT_PARTICIPATION in validation_codes(invalid_export)
