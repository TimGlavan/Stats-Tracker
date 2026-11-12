import json
from dataclasses import replace
from pathlib import Path

import pytest

from stats_tracker.exporter import GameExportError, export_completed_game_json
from stats_tracker.models import GameStatus, game_export_from_dict


ROOT = Path(__file__).parents[1]


def completed_game_export():
    payload = json.loads((ROOT / "examples/valid_game_export_v1.json").read_text())
    return game_export_from_dict(payload)


def test_completed_game_export_is_portable_json(tmp_path) -> None:
    game_export = completed_game_export()

    path = export_completed_game_json(game_export, tmp_path)

    assert path == tmp_path / "tournament-2026_0e80e110-2b44-4ed0-9ad1-0030c86dad10_rev1.json"
    assert json.loads(path.read_text()) == game_export.to_dict()


def test_export_rewrites_same_revision_atomically(tmp_path) -> None:
    game_export = completed_game_export()
    first_path = export_completed_game_json(game_export, tmp_path)
    second_path = export_completed_game_json(game_export, tmp_path)

    assert first_path == second_path
    assert list(tmp_path.glob("*.tmp")) == []


def test_in_progress_game_cannot_be_exported(tmp_path) -> None:
    game_export = completed_game_export()
    in_progress = replace(
        game_export,
        game=replace(game_export.game, status=GameStatus.IN_PROGRESS),
    )

    with pytest.raises(GameExportError, match="completed"):
        export_completed_game_json(in_progress, tmp_path)
