from datetime import date, datetime, timezone
from itertools import count

import pytest

from stats_tracker.game_session import (
    GameSession,
    GameSessionError,
    GameSessionValidationError,
)
from stats_tracker.models import GameMetadata, GameStatus, ShotOutcome, StatisticKind
from stats_tracker.validation import TournamentValidationContext


def timestamp() -> datetime:
    return datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def identifier_provider():
    numbers = count(1)
    return lambda: f"event-{next(numbers)}"


def context() -> TournamentValidationContext:
    return TournamentValidationContext(
        tournament_id="tournament-2026",
        configuration_version=1,
        rosters={
            "team-home": frozenset({"player-home-01", "player-home-02"}),
            "team-away": frozenset({"player-away-01"}),
        },
    )


def new_session() -> GameSession:
    return GameSession.new(
        GameMetadata(
            game_id="game-001",
            tournament_id="tournament-2026",
            configuration_version=1,
            home_team_id="team-home",
            away_team_id="team-away",
            game_date=date(2026, 11, 10),
            overtime_periods=0,
            status=GameStatus.IN_PROGRESS,
        ),
        context(),
        actor_id="scorer-01",
        timestamp_provider=timestamp,
        identifier_provider=identifier_provider(),
    )


def test_record_stat_automatically_marks_player_participation() -> None:
    session = new_session()

    state = session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.TWO_POINT_FIELD_GOAL,
        ShotOutcome.MADE,
    )

    assert [event.sequence for event in state.game_export.events] == [1, 2]
    assert [event.event_type.value for event in state.game_export.events] == [
        "player_participation_marked",
        "stat_recorded",
    ]
    assert state.box_score.scoreboard == {"team-home": 2, "team-away": 0}
    player = state.box_score.player_box_scores[0]
    assert player.participated is True
    assert player.games_played == 1


def test_existing_participation_is_not_added_twice() -> None:
    session = new_session()
    session.mark_participation("team-home", "player-home-02")

    state = session.record_stat(
        "team-home", "player-home-02", StatisticKind.ASSIST
    )

    assert len(state.game_export.events) == 2
    assert [event.sequence for event in state.game_export.events] == [1, 2]
    player = state.box_score.player_box_scores[1]
    assert player.games_played == 1
    assert player.totals.assists == 1


def test_undo_appends_a_void_event_and_recalculates_score() -> None:
    session = new_session()
    session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.THREE_POINT_FIELD_GOAL,
        ShotOutcome.MADE,
    )

    state = session.undo_last_stat()

    assert [event.sequence for event in state.game_export.events] == [1, 2, 3]
    assert state.game_export.events[-1].event_type.value == "event_voided"
    assert state.box_score.scoreboard == {"team-home": 0, "team-away": 0}
    player = state.box_score.player_box_scores[0]
    assert player.totals.three_point_attempted == 0
    assert player.participated is True


def test_selected_earlier_stat_can_be_undone() -> None:
    session = new_session()
    first_state = session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.TWO_POINT_FIELD_GOAL,
        ShotOutcome.MADE,
    )
    first_stat = first_state.game_export.events[-1]
    session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.FREE_THROW,
        ShotOutcome.MADE,
    )

    state = session.undo_stat_event(first_stat.event_id)

    assert state.game_export.events[-1].event_type.value == "event_voided"
    assert state.box_score.scoreboard == {"team-home": 1, "team-away": 0}
    player = state.box_score.player_box_scores[0]
    assert player.totals.two_point_attempted == 0
    assert player.totals.free_throw_made == 1


def test_invalid_action_does_not_change_session_state() -> None:
    session = new_session()
    before = session.game_export

    with pytest.raises(GameSessionValidationError):
        session.record_stat(
            "team-home",
            "player-not-on-roster",
            StatisticKind.STEAL,
        )

    assert session.game_export == before


def test_completed_game_rejects_new_entry() -> None:
    session = new_session()
    state = session.complete_game()

    assert state.game_export.game.status is GameStatus.COMPLETED
    with pytest.raises(GameSessionError, match="in progress"):
        session.record_stat(
            "team-home",
            "player-home-01",
            StatisticKind.STEAL,
        )
