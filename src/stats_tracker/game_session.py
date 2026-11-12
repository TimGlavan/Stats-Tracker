"""Application service for live, GUI-independent game entry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from .calculations import GameBoxScore, calculate_box_score
from .models import (
    EventVoidedEvent,
    GameEvent,
    GameExport,
    GameMetadata,
    GameStatus,
    PlayerParticipationMarkedEvent,
    ShotOutcome,
    StatisticKind,
    StatRecordedEvent,
)
from .validation import (
    TournamentValidationContext,
    ValidationResult,
    validate_game_export,
)


TimestampProvider = Callable[[], datetime]
IdentifierProvider = Callable[[], str]


class GameExportStore(Protocol):
    """Persistence boundary used by the game-entry application service."""

    def save(self, game_export: GameExport) -> None: ...


class GameSessionError(ValueError):
    """Base error for an action that cannot be applied to a game session."""


class GameSessionValidationError(GameSessionError):
    """Raised when an action would make the game semantically invalid."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        super().__init__("game action would create an invalid game export")


@dataclass(frozen=True, slots=True)
class GameSessionState:
    """The current export plus its derived, display-ready box score."""

    game_export: GameExport
    box_score: GameBoxScore


class GameSession:
    """Coordinates scorer actions without making any GUI or storage assumptions.

    The session keeps the canonical event list in memory. A future SQLite
    repository will persist the export produced by each successful action.
    """

    def __init__(
        self,
        game_export: GameExport,
        context: TournamentValidationContext,
        *,
        actor_id: str | None = None,
        timestamp_provider: TimestampProvider | None = None,
        identifier_provider: IdentifierProvider | None = None,
        repository: GameExportStore | None = None,
    ) -> None:
        self._context = context
        self._actor_id = actor_id
        self._timestamp_provider = timestamp_provider or _utc_now
        self._identifier_provider = identifier_provider or _new_identifier
        self._repository = repository
        self._game_export = game_export
        self._ensure_valid(game_export)
        if self._repository is not None:
            self._repository.save(game_export)

    @classmethod
    def new(
        cls,
        game: GameMetadata,
        context: TournamentValidationContext,
        *,
        actor_id: str | None = None,
        timestamp_provider: TimestampProvider | None = None,
        identifier_provider: IdentifierProvider | None = None,
        repository: GameExportStore | None = None,
    ) -> "GameSession":
        now = timestamp_provider or _utc_now
        game_export = GameExport(
            schema_version=1,
            export_revision=1,
            exported_at=now(),
            game=game,
            events=(),
        )
        return cls(
            game_export,
            context,
            actor_id=actor_id,
            timestamp_provider=now,
            identifier_provider=identifier_provider,
            repository=repository,
        )

    @property
    def game_export(self) -> GameExport:
        return self._game_export

    @property
    def state(self) -> GameSessionState:
        return GameSessionState(
            game_export=self._game_export,
            box_score=calculate_box_score(self._game_export, self._context.rosters),
        )

    def mark_participation(self, team_id: str, player_id: str) -> GameSessionState:
        """Record a player who participated but may not have a statistic."""

        self._require_in_progress()
        if self._has_effective_participation(team_id, player_id):
            raise GameSessionError("player already has an effective participation marker")
        event = PlayerParticipationMarkedEvent(
            **self._common_event_fields(),
            team_id=team_id,
            player_id=player_id,
        )
        self._append_and_validate(event)
        return self.state

    def record_stat(
        self,
        team_id: str,
        player_id: str,
        statistic_kind: StatisticKind,
        outcome: ShotOutcome | None = None,
    ) -> GameSessionState:
        """Record one statistic and automatically mark first participation."""

        self._require_in_progress()
        events: list[GameEvent] = []
        if not self._has_effective_participation(team_id, player_id):
            events.append(
                PlayerParticipationMarkedEvent(
                    **self._common_event_fields(offset=len(events)),
                    team_id=team_id,
                    player_id=player_id,
                )
            )
        events.append(
            StatRecordedEvent(
                **self._common_event_fields(offset=len(events)),
                team_id=team_id,
                player_id=player_id,
                statistic_kind=statistic_kind,
                outcome=outcome,
            )
        )
        self._append_many_and_validate(events)
        return self.state

    def undo_last_stat(self) -> GameSessionState:
        """Append an undo event for the most recent effective statistic."""

        target = self._most_recent_effective_stat()
        if target is None:
            raise GameSessionError("there is no effective statistic event to undo")
        return self.undo_stat_event(target.event_id)

    def undo_stat_event(self, target_event_id: str) -> GameSessionState:
        """Append a void for any earlier active statistic selected by the scorer."""

        self._require_in_progress()
        target = next(
            (
                event
                for event in self._game_export.events
                if event.event_id == target_event_id
            ),
            None,
        )
        if not isinstance(target, StatRecordedEvent):
            raise GameSessionError("only statistic events can be undone")
        if target.event_id in _voided_event_ids(self._game_export.events):
            raise GameSessionError("the selected statistic has already been undone")
        undo_event = EventVoidedEvent(
            **self._common_event_fields(),
            target_event_id=target.event_id,
        )
        self._append_and_validate(undo_event)
        return self.state

    def complete_game(self) -> GameSessionState:
        """Mark an in-progress game complete without changing its event history."""

        self._require_in_progress()
        self._replace_and_validate(
            replace(
                self._game_export,
                game=replace(self._game_export.game, status=GameStatus.COMPLETED),
            )
        )
        return self.state

    def _common_event_fields(self, *, offset: int = 0) -> dict[str, object]:
        return {
            "event_id": self._identifier_provider(),
            "game_id": self._game_export.game.game_id,
            "sequence": len(self._game_export.events) + offset + 1,
            "recorded_at": self._timestamp_provider(),
            "actor_id": self._actor_id,
        }

    def _append_and_validate(self, event: GameEvent) -> None:
        self._append_many_and_validate([event])

    def _append_many_and_validate(self, events: list[GameEvent]) -> None:
        self._replace_and_validate(
            replace(self._game_export, events=(*self._game_export.events, *events))
        )

    def _replace_and_validate(self, candidate: GameExport) -> None:
        self._ensure_valid(candidate)
        if self._repository is not None:
            self._repository.save(candidate)
        self._game_export = candidate

    def _ensure_valid(self, candidate: GameExport) -> None:
        result = validate_game_export(candidate, self._context)
        if not result.is_accepted:
            raise GameSessionValidationError(result)

    def _require_in_progress(self) -> None:
        if self._game_export.game.status is not GameStatus.IN_PROGRESS:
            raise GameSessionError("game entry is allowed only while the game is in progress")

    def _has_effective_participation(self, team_id: str, player_id: str) -> bool:
        voided_event_ids = _voided_event_ids(self._game_export.events)
        return any(
            isinstance(event, PlayerParticipationMarkedEvent)
            and event.event_id not in voided_event_ids
            and event.team_id == team_id
            and event.player_id == player_id
            for event in self._game_export.events
        )

    def _most_recent_effective_stat(self) -> StatRecordedEvent | None:
        voided_event_ids = _voided_event_ids(self._game_export.events)
        for event in reversed(self._game_export.events):
            if isinstance(event, StatRecordedEvent) and event.event_id not in voided_event_ids:
                return event
        return None


def _voided_event_ids(events: tuple[GameEvent, ...]) -> set[str]:
    return {
        event.target_event_id
        for event in events
        if isinstance(event, EventVoidedEvent)
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_identifier() -> str:
    return str(uuid4())
