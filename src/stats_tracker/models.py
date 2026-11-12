"""Typed domain models for version-1 game exports.

These models validate fields that belong to a single object. Validation
that compares multiple events (for example, sequence gaps or a void target)
belongs in the separate semantic-validation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Mapping, TypeAlias


class EventType(StrEnum):
    STAT_RECORDED = "stat_recorded"
    PLAYER_PARTICIPATION_MARKED = "player_participation_marked"
    EVENT_VOIDED = "event_voided"


class StatisticKind(StrEnum):
    TWO_POINT_FIELD_GOAL = "two_point_field_goal"
    THREE_POINT_FIELD_GOAL = "three_point_field_goal"
    FREE_THROW = "free_throw"
    OFFENSIVE_REBOUND = "offensive_rebound"
    DEFENSIVE_REBOUND = "defensive_rebound"
    ASSIST = "assist"
    STEAL = "steal"
    TURNOVER = "turnover"


class ShotOutcome(StrEnum):
    MADE = "made"
    MISSED = "missed"


class GameStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


SHOOTING_STATISTICS = frozenset(
    {
        StatisticKind.TWO_POINT_FIELD_GOAL,
        StatisticKind.THREE_POINT_FIELD_GOAL,
        StatisticKind.FREE_THROW,
    }
)


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")


def _optional_identifier(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_identifier(value, field_name)


def _timestamp_to_json(value: datetime) -> str:
    _require_utc(value, "timestamp")
    return value.isoformat().replace("+00:00", "Z")


def _timestamp_from_json(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be an ISO 8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from error
    _require_utc(parsed, field_name)
    return parsed


def _require_string(mapping: Mapping[str, object], field_name: str) -> str:
    value = mapping.get(field_name)
    _require_identifier(value, field_name)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


def _optional_string(mapping: Mapping[str, object], field_name: str) -> str | None:
    value = mapping.get(field_name)
    if value is None:
        return None
    _require_identifier(value, field_name)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class GameMetadata:
    game_id: str
    tournament_id: str
    configuration_version: int
    home_team_id: str
    away_team_id: str
    game_date: date
    overtime_periods: int
    status: GameStatus

    def __post_init__(self) -> None:
        for field_name in (
            "game_id",
            "tournament_id",
            "home_team_id",
            "away_team_id",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        if self.home_team_id == self.away_team_id:
            raise ValueError("home_team_id and away_team_id must be different")
        if not isinstance(self.game_date, date):
            raise ValueError("game_date must be a date")
        if self.configuration_version < 1:
            raise ValueError("configuration_version must be at least 1")
        if self.overtime_periods < 0:
            raise ValueError("overtime_periods cannot be negative")
        if not isinstance(self.status, GameStatus):
            raise ValueError("status must be a GameStatus")

    def to_dict(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "tournament_id": self.tournament_id,
            "configuration_version": self.configuration_version,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "game_date": self.game_date.isoformat(),
            "overtime_periods": self.overtime_periods,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EventBase:
    event_id: str
    game_id: str
    sequence: int
    recorded_at: datetime
    actor_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "event_id")
        _require_identifier(self.game_id, "game_id")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        _require_utc(self.recorded_at, "recorded_at")
        _optional_identifier(self.actor_id, "actor_id")

    @property
    def event_type(self) -> EventType:
        raise NotImplementedError

    def _common_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "event_id": self.event_id,
            "game_id": self.game_id,
            "sequence": self.sequence,
            "recorded_at": _timestamp_to_json(self.recorded_at),
            "event_type": self.event_type.value,
        }
        if self.actor_id is not None:
            result["actor_id"] = self.actor_id
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class StatRecordedEvent(EventBase):
    team_id: str
    player_id: str
    statistic_kind: StatisticKind
    outcome: ShotOutcome | None = None

    def __post_init__(self) -> None:
        super(StatRecordedEvent, self).__post_init__()
        _require_identifier(self.team_id, "team_id")
        _require_identifier(self.player_id, "player_id")
        if not isinstance(self.statistic_kind, StatisticKind):
            raise ValueError("statistic_kind must be a StatisticKind")
        if self.outcome is not None and not isinstance(self.outcome, ShotOutcome):
            raise ValueError("outcome must be a ShotOutcome")
        if self.statistic_kind in SHOOTING_STATISTICS and self.outcome is None:
            raise ValueError("shooting statistics require an outcome")
        if self.statistic_kind not in SHOOTING_STATISTICS and self.outcome is not None:
            raise ValueError("non-shooting statistics must not have an outcome")

    @property
    def event_type(self) -> EventType:
        return EventType.STAT_RECORDED

    def to_dict(self) -> dict[str, object]:
        result = self._common_dict()
        result.update(
            {
                "team_id": self.team_id,
                "player_id": self.player_id,
                "statistic_kind": self.statistic_kind.value,
            }
        )
        if self.outcome is not None:
            result["outcome"] = self.outcome.value
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerParticipationMarkedEvent(EventBase):
    team_id: str
    player_id: str

    def __post_init__(self) -> None:
        super(PlayerParticipationMarkedEvent, self).__post_init__()
        _require_identifier(self.team_id, "team_id")
        _require_identifier(self.player_id, "player_id")

    @property
    def event_type(self) -> EventType:
        return EventType.PLAYER_PARTICIPATION_MARKED

    def to_dict(self) -> dict[str, object]:
        result = self._common_dict()
        result.update({"team_id": self.team_id, "player_id": self.player_id})
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class EventVoidedEvent(EventBase):
    target_event_id: str

    def __post_init__(self) -> None:
        super(EventVoidedEvent, self).__post_init__()
        _require_identifier(self.target_event_id, "target_event_id")

    @property
    def event_type(self) -> EventType:
        return EventType.EVENT_VOIDED

    def to_dict(self) -> dict[str, object]:
        result = self._common_dict()
        result["target_event_id"] = self.target_event_id
        return result


GameEvent: TypeAlias = (
    StatRecordedEvent
    | PlayerParticipationMarkedEvent
    | EventVoidedEvent
)


@dataclass(frozen=True, slots=True, kw_only=True)
class GameExport:
    schema_version: int
    export_revision: int
    exported_at: datetime
    game: GameMetadata
    events: tuple[GameEvent, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("only schema_version 1 is currently supported")
        if not isinstance(self.export_revision, int) or isinstance(self.export_revision, bool) or self.export_revision < 1:
            raise ValueError("export_revision must be a positive integer")
        _require_utc(self.exported_at, "exported_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "export_revision": self.export_revision,
            "exported_at": _timestamp_to_json(self.exported_at),
            "game": self.game.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }


def game_metadata_from_dict(data: Mapping[str, object]) -> GameMetadata:
    raw_date = data.get("game_date")
    if not isinstance(raw_date, str):
        raise ValueError("game_date must be an ISO 8601 date")
    try:
        game_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise ValueError("game_date must be an ISO 8601 date") from error

    return GameMetadata(
        game_id=_require_string(data, "game_id"),
        tournament_id=_require_string(data, "tournament_id"),
        configuration_version=_require_positive_int(data, "configuration_version"),
        home_team_id=_require_string(data, "home_team_id"),
        away_team_id=_require_string(data, "away_team_id"),
        game_date=game_date,
        overtime_periods=_require_nonnegative_int(data, "overtime_periods"),
        status=GameStatus(_require_string(data, "status")),
    )


def event_from_dict(data: Mapping[str, object]) -> GameEvent:
    event_type = EventType(_require_string(data, "event_type"))
    common = {
        "event_id": _require_string(data, "event_id"),
        "game_id": _require_string(data, "game_id"),
        "sequence": _require_positive_int(data, "sequence"),
        "recorded_at": _timestamp_from_json(data.get("recorded_at"), "recorded_at"),
        "actor_id": _optional_string(data, "actor_id"),
    }

    if event_type is EventType.STAT_RECORDED:
        raw_outcome = data.get("outcome")
        return StatRecordedEvent(
            **common,
            team_id=_require_string(data, "team_id"),
            player_id=_require_string(data, "player_id"),
            statistic_kind=StatisticKind(_require_string(data, "statistic_kind")),
            outcome=ShotOutcome(raw_outcome) if raw_outcome is not None else None,
        )
    if event_type is EventType.PLAYER_PARTICIPATION_MARKED:
        return PlayerParticipationMarkedEvent(
            **common,
            team_id=_require_string(data, "team_id"),
            player_id=_require_string(data, "player_id"),
        )
    if event_type is EventType.EVENT_VOIDED:
        return EventVoidedEvent(
            **common,
            target_event_id=_require_string(data, "target_event_id"),
        )
    raise AssertionError(f"unsupported event type: {event_type}")


def game_export_from_dict(data: Mapping[str, object]) -> GameExport:
    raw_game = data.get("game")
    raw_events = data.get("events")
    if not isinstance(raw_game, Mapping):
        raise ValueError("game must be an object")
    if not isinstance(raw_events, list):
        raise ValueError("events must be an array")

    events: list[GameEvent] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, Mapping):
            raise ValueError("every event must be an object")
        events.append(event_from_dict(raw_event))

    return GameExport(
        schema_version=_require_positive_int(data, "schema_version"),
        export_revision=_require_positive_int(data, "export_revision"),
        exported_at=_timestamp_from_json(data.get("exported_at"), "exported_at"),
        game=game_metadata_from_dict(raw_game),
        events=tuple(events),
    )


def _require_positive_int(mapping: Mapping[str, object], field_name: str) -> int:
    value = mapping.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_nonnegative_int(mapping: Mapping[str, object], field_name: str) -> int:
    value = mapping.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value
