import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stats_tracker.models import (
    EventVoidedEvent,
    ShotOutcome,
    StatisticKind,
    StatRecordedEvent,
    game_export_from_dict,
)


ROOT = Path(__file__).parents[1]


def load_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text())


def test_valid_fixture_round_trips_through_models() -> None:
    payload = load_json("examples/valid_game_export_v1.json")

    game_export = game_export_from_dict(payload)

    assert game_export.game.game_id == "0e80e110-2b44-4ed0-9ad1-0030c86dad10"
    assert len(game_export.events) == 12
    assert game_export.to_dict() == payload


def test_non_shooting_statistic_rejects_a_shot_outcome() -> None:
    with pytest.raises(ValueError, match="non-shooting"):
        StatRecordedEvent(
            event_id="event-1",
            game_id="game-1",
            sequence=1,
            recorded_at=datetime.now(timezone.utc),
            team_id="team-1",
            player_id="player-1",
            statistic_kind=StatisticKind.ASSIST,
            outcome=ShotOutcome.MADE,
        )


def test_void_event_contains_only_its_target() -> None:
    event = EventVoidedEvent(
        event_id="event-2",
        game_id="game-1",
        sequence=2,
        recorded_at=datetime.now(timezone.utc),
        target_event_id="event-1",
    )

    assert event.to_dict()["target_event_id"] == "event-1"
    assert "void_reason" not in event.to_dict()
