"""Typed tournament configuration and roster-context construction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .validation import TournamentValidationContext


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _optional_color(value: str | None, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not _HEX_COLOR.fullmatch(value)):
        raise ValueError(f"{field_name} must be a six-digit hex color such as #123456")


@dataclass(frozen=True, slots=True)
class PlayerConfiguration:
    player_id: str
    name: str
    jersey_number: str

    def __post_init__(self) -> None:
        _require_nonempty(self.player_id, "player_id")
        _require_nonempty(self.name, "player name")
        _require_nonempty(self.jersey_number, "jersey_number")
        if len(self.jersey_number) > 3:
            raise ValueError("jersey_number must contain at most three characters")

    def to_dict(self) -> dict[str, str]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "jersey_number": self.jersey_number,
        }


@dataclass(frozen=True, slots=True)
class TeamConfiguration:
    team_id: str
    name: str
    abbreviation: str
    players: tuple[PlayerConfiguration, ...]
    primary_color: str | None = None
    secondary_color: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.team_id, "team_id")
        _require_nonempty(self.name, "team name")
        _require_nonempty(self.abbreviation, "abbreviation")
        if len(self.abbreviation) > 8:
            raise ValueError("abbreviation must contain at most eight characters")
        if not self.players:
            raise ValueError("a team must have at least one player")
        player_ids = [player.player_id for player in self.players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("player_id values must be unique within a team")
        _optional_color(self.primary_color, "primary_color")
        _optional_color(self.secondary_color, "secondary_color")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "team_id": self.team_id,
            "name": self.name,
            "abbreviation": self.abbreviation,
            "players": [player.to_dict() for player in self.players],
        }
        if self.primary_color is not None:
            result["primary_color"] = self.primary_color
        if self.secondary_color is not None:
            result["secondary_color"] = self.secondary_color
        return result


@dataclass(frozen=True, slots=True)
class TournamentConfiguration:
    schema_version: int
    tournament_id: str
    name: str
    configuration_version: int
    teams: tuple[TeamConfiguration, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("only configuration schema_version 1 is currently supported")
        _require_nonempty(self.tournament_id, "tournament_id")
        _require_nonempty(self.name, "tournament name")
        if self.configuration_version < 1:
            raise ValueError("configuration_version must be at least 1")
        if len(self.teams) < 2:
            raise ValueError("a tournament configuration must contain at least two teams")

        team_ids = [team.team_id for team in self.teams]
        if len(team_ids) != len(set(team_ids)):
            raise ValueError("team_id values must be unique within a tournament")

        player_ids = [
            player.player_id for team in self.teams for player in team.players
        ]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("player_id values must be unique within a tournament")

    @property
    def rosters(self) -> dict[str, frozenset[str]]:
        return {
            team.team_id: frozenset(player.player_id for player in team.players)
            for team in self.teams
        }

    def to_validation_context(self) -> TournamentValidationContext:
        return TournamentValidationContext(
            tournament_id=self.tournament_id,
            configuration_version=self.configuration_version,
            rosters=self.rosters,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tournament_id": self.tournament_id,
            "name": self.name,
            "configuration_version": self.configuration_version,
            "teams": [team.to_dict() for team in self.teams],
        }


def tournament_configuration_from_dict(data: Mapping[str, object]) -> TournamentConfiguration:
    raw_teams = data.get("teams")
    if not isinstance(raw_teams, list):
        raise ValueError("teams must be an array")

    teams: list[TeamConfiguration] = []
    for raw_team in raw_teams:
        if not isinstance(raw_team, Mapping):
            raise ValueError("every team must be an object")
        raw_players = raw_team.get("players")
        if not isinstance(raw_players, list):
            raise ValueError("players must be an array")
        players: list[PlayerConfiguration] = []
        for raw_player in raw_players:
            if not isinstance(raw_player, Mapping):
                raise ValueError("every player must be an object")
            players.append(
                PlayerConfiguration(
                    player_id=_required_string(raw_player, "player_id"),
                    name=_required_string(raw_player, "name"),
                    jersey_number=_required_string(raw_player, "jersey_number"),
                )
            )
        teams.append(
            TeamConfiguration(
                team_id=_required_string(raw_team, "team_id"),
                name=_required_string(raw_team, "name"),
                abbreviation=_required_string(raw_team, "abbreviation"),
                players=tuple(players),
                primary_color=_optional_string(raw_team, "primary_color"),
                secondary_color=_optional_string(raw_team, "secondary_color"),
            )
        )

    return TournamentConfiguration(
        schema_version=_required_positive_int(data, "schema_version"),
        tournament_id=_required_string(data, "tournament_id"),
        name=_required_string(data, "name"),
        configuration_version=_required_positive_int(data, "configuration_version"),
        teams=tuple(teams),
    )


def load_tournament_configuration(path: str | Path) -> TournamentConfiguration:
    """Load a JSON configuration into typed models.

    Callers should first run the file through the companion JSON Schema;
    this parser enforces typed-model and cross-roster invariants.
    """

    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, Mapping):
        raise ValueError("tournament configuration must be a JSON object")
    return tournament_configuration_from_dict(data)


def _required_string(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    _require_nonempty(value, field_name)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


def _optional_string(data: Mapping[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    _require_nonempty(value, field_name)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


def _required_positive_int(data: Mapping[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value
