"""Box-score calculation from validated, effective game events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import (
    EventVoidedEvent,
    GameExport,
    PlayerParticipationMarkedEvent,
    ShotOutcome,
    StatisticKind,
    StatRecordedEvent,
)


def _percentage(made: int, attempted: int) -> float | None:
    return made / attempted if attempted else None


@dataclass(frozen=True, slots=True)
class StatTotals:
    two_point_made: int = 0
    two_point_attempted: int = 0
    three_point_made: int = 0
    three_point_attempted: int = 0
    free_throw_made: int = 0
    free_throw_attempted: int = 0
    offensive_rebounds: int = 0
    defensive_rebounds: int = 0
    assists: int = 0
    steals: int = 0
    turnovers: int = 0
    points: int = 0

    @property
    def total_rebounds(self) -> int:
        return self.offensive_rebounds + self.defensive_rebounds

    @property
    def field_goal_made(self) -> int:
        return self.two_point_made + self.three_point_made

    @property
    def field_goal_attempted(self) -> int:
        return self.two_point_attempted + self.three_point_attempted

    @property
    def two_point_percentage(self) -> float | None:
        return _percentage(self.two_point_made, self.two_point_attempted)

    @property
    def three_point_percentage(self) -> float | None:
        return _percentage(self.three_point_made, self.three_point_attempted)

    @property
    def free_throw_percentage(self) -> float | None:
        return _percentage(self.free_throw_made, self.free_throw_attempted)

    @property
    def field_goal_percentage(self) -> float | None:
        return _percentage(self.field_goal_made, self.field_goal_attempted)

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "two_point_made": self.two_point_made,
            "two_point_attempted": self.two_point_attempted,
            "two_point_percentage": self.two_point_percentage,
            "three_point_made": self.three_point_made,
            "three_point_attempted": self.three_point_attempted,
            "three_point_percentage": self.three_point_percentage,
            "free_throw_made": self.free_throw_made,
            "free_throw_attempted": self.free_throw_attempted,
            "free_throw_percentage": self.free_throw_percentage,
            "field_goal_made": self.field_goal_made,
            "field_goal_attempted": self.field_goal_attempted,
            "field_goal_percentage": self.field_goal_percentage,
            "offensive_rebounds": self.offensive_rebounds,
            "defensive_rebounds": self.defensive_rebounds,
            "total_rebounds": self.total_rebounds,
            "assists": self.assists,
            "steals": self.steals,
            "turnovers": self.turnovers,
            "points": self.points,
        }


@dataclass(frozen=True, slots=True)
class PlayerBoxScore:
    team_id: str
    player_id: str
    participated: bool
    totals: StatTotals

    @property
    def games_played(self) -> int:
        return int(self.participated)

    def to_dict(self) -> dict[str, object]:
        return {
            "team_id": self.team_id,
            "player_id": self.player_id,
            "participated": self.participated,
            "games_played": self.games_played,
            **self.totals.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TeamBoxScore:
    team_id: str
    totals: StatTotals

    def to_dict(self) -> dict[str, object]:
        return {"team_id": self.team_id, **self.totals.to_dict()}


@dataclass(frozen=True, slots=True)
class GameBoxScore:
    voided_event_ids: tuple[str, ...]
    effective_stat_event_ids: tuple[str, ...]
    player_box_scores: tuple[PlayerBoxScore, ...]
    team_box_scores: tuple[TeamBoxScore, ...]

    @property
    def scoreboard(self) -> dict[str, int]:
        return {
            team_box_score.team_id: team_box_score.totals.points
            for team_box_score in self.team_box_scores
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "voided_event_ids": list(self.voided_event_ids),
            "effective_stat_event_ids": list(self.effective_stat_event_ids),
            "player_box_scores": [
                player_box_score.to_dict() for player_box_score in self.player_box_scores
            ],
            "team_box_scores": [
                team_box_score.to_dict() for team_box_score in self.team_box_scores
            ],
            "scoreboard": self.scoreboard,
        }


@dataclass(slots=True)
class _MutableStatTotals:
    two_point_made: int = 0
    two_point_attempted: int = 0
    three_point_made: int = 0
    three_point_attempted: int = 0
    free_throw_made: int = 0
    free_throw_attempted: int = 0
    offensive_rebounds: int = 0
    defensive_rebounds: int = 0
    assists: int = 0
    steals: int = 0
    turnovers: int = 0
    points: int = 0

    def record(self, event: StatRecordedEvent) -> None:
        kind = event.statistic_kind
        if kind is StatisticKind.TWO_POINT_FIELD_GOAL:
            self.two_point_attempted += 1
            if event.outcome is ShotOutcome.MADE:
                self.two_point_made += 1
                self.points += 2
        elif kind is StatisticKind.THREE_POINT_FIELD_GOAL:
            self.three_point_attempted += 1
            if event.outcome is ShotOutcome.MADE:
                self.three_point_made += 1
                self.points += 3
        elif kind is StatisticKind.FREE_THROW:
            self.free_throw_attempted += 1
            if event.outcome is ShotOutcome.MADE:
                self.free_throw_made += 1
                self.points += 1
        elif kind is StatisticKind.OFFENSIVE_REBOUND:
            self.offensive_rebounds += 1
        elif kind is StatisticKind.DEFENSIVE_REBOUND:
            self.defensive_rebounds += 1
        elif kind is StatisticKind.ASSIST:
            self.assists += 1
        elif kind is StatisticKind.STEAL:
            self.steals += 1
        elif kind is StatisticKind.TURNOVER:
            self.turnovers += 1
        else:  # Defensive guard for a future StatisticKind without a calculation rule.
            raise ValueError(f"unsupported statistic_kind: {kind}")

    def freeze(self) -> StatTotals:
        return StatTotals(
            two_point_made=self.two_point_made,
            two_point_attempted=self.two_point_attempted,
            three_point_made=self.three_point_made,
            three_point_attempted=self.three_point_attempted,
            free_throw_made=self.free_throw_made,
            free_throw_attempted=self.free_throw_attempted,
            offensive_rebounds=self.offensive_rebounds,
            defensive_rebounds=self.defensive_rebounds,
            assists=self.assists,
            steals=self.steals,
            turnovers=self.turnovers,
            points=self.points,
        )


def calculate_box_score(
    game_export: GameExport, rosters: Mapping[str, Iterable[str]]
) -> GameBoxScore:
    """Calculate a box score from a semantically valid game export.

    The roster mapping must contain both game teams. Call the semantic
    validator before this function; it owns rejecting malformed imports.
    """

    team_ids = (game_export.game.home_team_id, game_export.game.away_team_id)
    roster_player_ids: dict[str, tuple[str, ...]] = {}
    player_totals: dict[tuple[str, str], _MutableStatTotals] = {}
    for team_id in team_ids:
        if team_id not in rosters:
            raise ValueError(f"missing roster for game team {team_id!r}")
        roster_player_ids[team_id] = tuple(sorted(set(rosters[team_id])))
        for player_id in roster_player_ids[team_id]:
            player_totals[(team_id, player_id)] = _MutableStatTotals()

    voided_event_ids = tuple(
        event.target_event_id
        for event in game_export.events
        if isinstance(event, EventVoidedEvent)
    )
    voided_event_id_set = set(voided_event_ids)
    participated_players: set[tuple[str, str]] = set()
    effective_stat_event_ids: list[str] = []

    for event in game_export.events:
        if event.event_id in voided_event_id_set:
            continue
        if isinstance(event, PlayerParticipationMarkedEvent):
            _require_rostered_player(player_totals, event.team_id, event.player_id)
            participated_players.add((event.team_id, event.player_id))
        elif isinstance(event, StatRecordedEvent):
            _require_rostered_player(player_totals, event.team_id, event.player_id)
            player_totals[(event.team_id, event.player_id)].record(event)
            effective_stat_event_ids.append(event.event_id)

    player_box_scores = tuple(
        PlayerBoxScore(
            team_id=team_id,
            player_id=player_id,
            participated=(team_id, player_id) in participated_players,
            totals=player_totals[(team_id, player_id)].freeze(),
        )
        for team_id in team_ids
        for player_id in roster_player_ids[team_id]
    )

    team_box_scores = tuple(
        TeamBoxScore(
            team_id=team_id,
            totals=_sum_totals(
                player_box_score.totals
                for player_box_score in player_box_scores
                if player_box_score.team_id == team_id
            ),
        )
        for team_id in team_ids
    )

    return GameBoxScore(
        voided_event_ids=voided_event_ids,
        effective_stat_event_ids=tuple(effective_stat_event_ids),
        player_box_scores=player_box_scores,
        team_box_scores=team_box_scores,
    )


def _require_rostered_player(
    player_totals: Mapping[tuple[str, str], _MutableStatTotals],
    team_id: str,
    player_id: str,
) -> None:
    if (team_id, player_id) not in player_totals:
        raise ValueError(
            f"event references player_id {player_id!r} outside the supplied roster for team_id {team_id!r}"
        )


def _sum_totals(stat_lines: Iterable[StatTotals]) -> StatTotals:
    total = _MutableStatTotals()
    for line in stat_lines:
        total.two_point_made += line.two_point_made
        total.two_point_attempted += line.two_point_attempted
        total.three_point_made += line.three_point_made
        total.three_point_attempted += line.three_point_attempted
        total.free_throw_made += line.free_throw_made
        total.free_throw_attempted += line.free_throw_attempted
        total.offensive_rebounds += line.offensive_rebounds
        total.defensive_rebounds += line.defensive_rebounds
        total.assists += line.assists
        total.steals += line.steals
        total.turnovers += line.turnovers
        total.points += line.points
    return total.freeze()
