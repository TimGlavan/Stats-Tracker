"""SQLite persistence for locally recoverable game-entry sessions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import GameEvent, GameExport, game_export_from_dict


class GameNotFoundError(KeyError):
    """Raised when a requested game is not stored in this database."""


class PersistenceConflictError(ValueError):
    """Raised when a save would rewrite or delete persisted event history."""


class SQLiteGameRepository:
    """Persists game exports while preserving an append-only event history.

    Each successful save runs in one SQLite transaction. Existing events
    must be an unchanged prefix of the candidate event list; only new
    events may be added. Game metadata is updated independently so that a
    completed status can be saved without altering the event history.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteGameRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save(self, game_export: GameExport) -> None:
        """Atomically store a new game or append to an existing one."""

        game_id = game_export.game.game_id
        candidate_events = tuple(_canonical_event_json(event) for event in game_export.events)
        game_json = _canonical_json(game_export.game.to_dict())

        with self._connection:
            row = self._connection.execute(
                "SELECT game_id FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO games (
                        game_id, schema_version, export_revision, exported_at, game_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        game_id,
                        game_export.schema_version,
                        game_export.export_revision,
                        _timestamp_to_json(game_export),
                        game_json,
                    ),
                )
                self._insert_events(game_id, candidate_events)
                return

            stored_events = tuple(
                row["event_json"]
                for row in self._connection.execute(
                    """
                    SELECT event_json FROM events
                    WHERE game_id = ?
                    ORDER BY sequence
                    """,
                    (game_id,),
                )
            )
            _ensure_append_only(stored_events, candidate_events)

            self._connection.execute(
                """
                UPDATE games
                SET schema_version = ?, export_revision = ?, exported_at = ?, game_json = ?
                WHERE game_id = ?
                """,
                (
                    game_export.schema_version,
                    game_export.export_revision,
                    _timestamp_to_json(game_export),
                    game_json,
                    game_id,
                ),
            )
            self._insert_events(game_id, candidate_events[len(stored_events) :])

    def load(self, game_id: str) -> GameExport:
        row = self._connection.execute(
            """
            SELECT schema_version, export_revision, exported_at, game_json
            FROM games WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
        if row is None:
            raise GameNotFoundError(game_id)

        events = [
            json.loads(event_row["event_json"])
            for event_row in self._connection.execute(
                """
                SELECT event_json FROM events
                WHERE game_id = ?
                ORDER BY sequence
                """,
                (game_id,),
            )
        ]
        return game_export_from_dict(
            {
                "schema_version": row["schema_version"],
                "export_revision": row["export_revision"],
                "exported_at": row["exported_at"],
                "game": json.loads(row["game_json"]),
                "events": events,
            }
        )

    def list_game_ids(self) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT game_id FROM games ORDER BY game_id"
        ).fetchall()
        return tuple(row["game_id"] for row in rows)

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    export_revision INTEGER NOT NULL,
                    exported_at TEXT NOT NULL,
                    game_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    game_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (game_id, sequence),
                    UNIQUE (game_id, event_id),
                    FOREIGN KEY (game_id) REFERENCES games (game_id)
                )
                """
            )

    def _insert_events(self, game_id: str, event_jsons: tuple[str, ...]) -> None:
        if not event_jsons:
            return
        rows = []
        for event_json in event_jsons:
            event = json.loads(event_json)
            rows.append(
                (game_id, event["sequence"], event["event_id"], event_json)
            )
        self._connection.executemany(
            """
            INSERT INTO events (game_id, sequence, event_id, event_json)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )


def _canonical_event_json(event: GameEvent) -> str:
    return _canonical_json(event.to_dict())


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _timestamp_to_json(game_export: GameExport) -> str:
    return game_export.exported_at.isoformat().replace("+00:00", "Z")


def _ensure_append_only(stored_events: tuple[str, ...], candidate_events: tuple[str, ...]) -> None:
    if len(candidate_events) < len(stored_events):
        raise PersistenceConflictError("a save cannot delete persisted events")
    if candidate_events[: len(stored_events)] != stored_events:
        raise PersistenceConflictError("a save cannot rewrite persisted events")
