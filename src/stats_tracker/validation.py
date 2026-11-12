"""Cross-event and roster validation for game exports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .models import (
    EventBase,
    EventVoidedEvent,
    GameEvent,
    GameExport,
    PlayerParticipationMarkedEvent,
    StatRecordedEvent,
)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationCode(StrEnum):
    TOURNAMENT_MISMATCH = "tournament_mismatch"
    CONFIGURATION_VERSION_MISMATCH = "configuration_version_mismatch"
    UNKNOWN_GAME_TEAM = "unknown_game_team"
    DUPLICATE_EVENT_ID = "duplicate_event_id"
    INVALID_SEQUENCE = "invalid_sequence"
    EVENT_GAME_MISMATCH = "event_game_mismatch"
    EVENT_TEAM_NOT_IN_GAME = "event_team_not_in_game"
    UNKNOWN_PLAYER = "unknown_player"
    PLAYER_NOT_ON_TEAM = "player_not_on_team"
    VOID_TARGET_NOT_FOUND = "void_target_not_found"
    VOID_TARGET_INVALID_TYPE = "void_target_invalid_type"
    VOID_TARGET_ALREADY_VOIDED = "void_target_already_voided"
    DUPLICATE_PARTICIPATION = "duplicate_participation"
    STAT_WITHOUT_PARTICIPATION = "stat_without_participation"


@dataclass(frozen=True, slots=True)
class TournamentValidationContext:
    """The tournament configuration needed to validate one game export."""

    tournament_id: str
    configuration_version: int
    rosters: Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: ValidationCode
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.WARNING)

    @property
    def is_accepted(self) -> bool:
        return not self.errors


def validate_game_export(
    game_export: GameExport, context: TournamentValidationContext
) -> ValidationResult:
    """Validate semantic rules requiring the full event list or roster.

    Any scorer may void an earlier active statistic while a game is live.
    The void is appended to history, preserving the original statistic for
    audit and recovery.
    """

    issues: list[ValidationIssue] = []

    def error(code: ValidationCode, message: str, event: EventBase | None = None) -> None:
        issues.append(
            ValidationIssue(code=code, message=message, event_id=event.event_id if event else None)
        )

    game = game_export.game
    if game.tournament_id != context.tournament_id:
        error(ValidationCode.TOURNAMENT_MISMATCH, "game tournament_id does not match configuration")
    if game.configuration_version != context.configuration_version:
        error(
            ValidationCode.CONFIGURATION_VERSION_MISMATCH,
            "game configuration_version does not match configuration",
        )

    game_team_ids = {game.home_team_id, game.away_team_id}
    for team_id in game_team_ids:
        if team_id not in context.rosters:
            error(ValidationCode.UNKNOWN_GAME_TEAM, f"game team_id {team_id!r} is unknown")

    events_by_id: dict[str, GameEvent] = {}
    voided_event_ids: set[str] = set()
    for expected_sequence, event in enumerate(game_export.events, start=1):
        if event.sequence != expected_sequence:
            error(
                ValidationCode.INVALID_SEQUENCE,
                f"event sequence must be {expected_sequence}, not {event.sequence}",
                event,
            )
        if event.event_id in events_by_id:
            error(ValidationCode.DUPLICATE_EVENT_ID, f"event_id {event.event_id!r} is duplicated", event)
        else:
            events_by_id[event.event_id] = event
        if event.game_id != game.game_id:
            error(ValidationCode.EVENT_GAME_MISMATCH, "event game_id does not match the game", event)

        if isinstance(event, (StatRecordedEvent, PlayerParticipationMarkedEvent)):
            _validate_player_event(event, game_team_ids, context, error)
        elif isinstance(event, EventVoidedEvent):
            _validate_void_event(event, events_by_id, voided_event_ids, error)

    _validate_effective_participation(game_export.events, voided_event_ids, error)
    return ValidationResult(issues=tuple(issues))


def _validate_player_event(
    event: StatRecordedEvent | PlayerParticipationMarkedEvent,
    game_team_ids: set[str],
    context: TournamentValidationContext,
    error: "ErrorReporter",
) -> None:
    if event.team_id not in game_team_ids:
        error(
            ValidationCode.EVENT_TEAM_NOT_IN_GAME,
            f"event team_id {event.team_id!r} is not one of the game teams",
            event,
        )
    roster = context.rosters.get(event.team_id)
    if roster is None:
        error(ValidationCode.UNKNOWN_PLAYER, f"team_id {event.team_id!r} is unknown", event)
    elif event.player_id not in roster:
        error(
            ValidationCode.PLAYER_NOT_ON_TEAM,
            f"player_id {event.player_id!r} is not on team_id {event.team_id!r}",
            event,
        )


def _validate_void_event(
    event: EventVoidedEvent,
    events_by_id: Mapping[str, GameEvent],
    voided_event_ids: set[str],
    error: "ErrorReporter",
) -> None:
    target = events_by_id.get(event.target_event_id)
    if target is None:
        error(
            ValidationCode.VOID_TARGET_NOT_FOUND,
            f"target_event_id {event.target_event_id!r} does not exist earlier in the event list",
            event,
        )
        return
    if not isinstance(target, StatRecordedEvent):
        error(
            ValidationCode.VOID_TARGET_INVALID_TYPE,
            "an event_voided target must be a statistic event",
            event,
        )
        return
    if target.event_id in voided_event_ids:
        error(
            ValidationCode.VOID_TARGET_ALREADY_VOIDED,
            f"target_event_id {event.target_event_id!r} has already been voided",
            event,
        )
        return
    voided_event_ids.add(target.event_id)


def _validate_effective_participation(
    events: tuple[GameEvent, ...],
    voided_event_ids: set[str],
    error: "ErrorReporter",
) -> None:
    participation_counts: Counter[tuple[str, str]] = Counter()
    stat_events: list[StatRecordedEvent] = []
    for event in events:
        if event.event_id in voided_event_ids:
            continue
        if isinstance(event, PlayerParticipationMarkedEvent):
            participation_counts[(event.team_id, event.player_id)] += 1
        elif isinstance(event, StatRecordedEvent):
            stat_events.append(event)

    for (team_id, player_id), count in participation_counts.items():
        if count > 1:
            error(
                ValidationCode.DUPLICATE_PARTICIPATION,
                f"player_id {player_id!r} has {count} participation markers for team_id {team_id!r}",
            )
    for event in stat_events:
        if participation_counts[(event.team_id, event.player_id)] == 0:
            error(
                ValidationCode.STAT_WITHOUT_PARTICIPATION,
                "statistic event has no participation marker for its player",
                event,
            )


type ErrorReporter = Callable[[ValidationCode, str, EventBase | None], None]
