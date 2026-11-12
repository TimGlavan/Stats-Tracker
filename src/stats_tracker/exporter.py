"""Portable, atomic exports of completed canonical game records."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .models import GameExport, GameStatus


class GameExportError(ValueError):
    """Raised when a game is not ready for portable export."""


def export_completed_game_json(game_export: GameExport, output_directory: str | Path) -> Path:
    """Write a completed game's canonical event record as portable JSON.

    The file is written to a temporary file in the destination directory
    and atomically replaced, so an interrupted export cannot leave a
    partially written final JSON file.
    """

    if game_export.game.status is not GameStatus.COMPLETED:
        raise GameExportError("only completed games may be exported")

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{_filename_component(game_export.game.tournament_id)}_"
        f"{_filename_component(game_export.game.game_id)}_"
        f"rev{game_export.export_revision}.json"
    )
    destination = output_directory / filename
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_directory,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(game_export.to_dict(), temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise GameExportError(f"could not export game JSON: {error}") from error

    return destination


def _filename_component(value: str) -> str:
    """Keep IDs recognisable while ensuring they cannot escape the export folder."""

    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "game"
