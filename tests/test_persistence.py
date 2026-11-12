from dataclasses import replace
from datetime import date, datetime, timezone
from itertools import count

import pytest

from stats_tracker.game_session import GameSession, GameSessionValidationError
from stats_tracker.models import GameMetadata, GameStatus, ShotOutcome, StatisticKind
from stats_tracker.persistence import PersistenceConflictError, SQLiteGameRepository
from stats_tracker.validation import TournamentValidationContext


def timestamp() -> datetime:
    return datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc)


def identifiers(start: int = 1):
    values = count(start)
    return lambda: f"event-{next(values)}"


def context() -> TournamentValidationContext:
    return TournamentValidationContext(
        tournament_id="tournament-2026",
        configuration_version=1,
        rosters={
            "team-home": frozenset({"player-home-01"}),
            "team-away": frozenset({"player-away-01"}),
        },
    )


def new_session(repository: SQLiteGameRepository) -> GameSession:
    return GameSession.new(
        GameMetadata(
            game_id="game-persisted",
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
        identifier_provider=identifiers(),
        repository=repository,
    )


def test_session_autosaves_and_recovers_after_reopening_database(tmp_path) -> None:
    database_path = tmp_path / "active_games.sqlite3"
    repository = SQLiteGameRepository(database_path)
    session = new_session(repository)
    state = session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.THREE_POINT_FIELD_GOAL,
        ShotOutcome.MADE,
    )
    repository.close()

    reopened_repository = SQLiteGameRepository(database_path)
    recovered_export = reopened_repository.load("game-persisted")

    assert recovered_export == state.game_export
    resumed_session = GameSession(
        recovered_export,
        context(),
        actor_id="scorer-01",
        timestamp_provider=timestamp,
        identifier_provider=identifiers(start=3),
        repository=reopened_repository,
    )
    resumed_state = resumed_session.undo_last_stat()

    assert reopened_repository.load("game-persisted") == resumed_state.game_export
    assert resumed_state.box_score.scoreboard == {"team-home": 0, "team-away": 0}
    reopened_repository.close()


def test_invalid_session_action_is_not_persisted(tmp_path) -> None:
    repository = SQLiteGameRepository(tmp_path / "active_games.sqlite3")
    session = new_session(repository)
    before = repository.load("game-persisted")

    with pytest.raises(GameSessionValidationError):
        session.record_stat("team-home", "unknown-player", StatisticKind.STEAL)

    assert repository.load("game-persisted") == before
    repository.close()


def test_repository_refuses_to_rewrite_existing_event_history(tmp_path) -> None:
    repository = SQLiteGameRepository(tmp_path / "active_games.sqlite3")
    session = new_session(repository)
    session.record_stat(
        "team-home",
        "player-home-01",
        StatisticKind.STEAL,
    )
    first_event = session.game_export.events[0]
    rewritten_event = replace(first_event, actor_id="different-scorer")
    conflicting_export = replace(
        session.game_export,
        events=(rewritten_event, *session.game_export.events[1:]),
    )

    with pytest.raises(PersistenceConflictError, match="rewrite"):
        repository.save(conflicting_export)

    assert repository.list_game_ids() == ("game-persisted",)
    repository.close()
