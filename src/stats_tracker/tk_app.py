"""Small Tkinter scorer prototype for exercising the Phase 1 backend."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .configuration import (
    PlayerConfiguration,
    TeamConfiguration,
    TournamentConfiguration,
    load_tournament_configuration,
)
from .exporter import GameExportError, export_completed_game_json
from .game_session import GameSession, GameSessionError, GameSessionState
from .models import (
    EventVoidedEvent,
    GameMetadata,
    GameStatus,
    PlayerParticipationMarkedEvent,
    ShotOutcome,
    StatisticKind,
    StatRecordedEvent,
)
from .persistence import SQLiteGameRepository


STAT_ACTIONS: tuple[tuple[str, StatisticKind, ShotOutcome | None], ...] = (
    ("2PT Made", StatisticKind.TWO_POINT_FIELD_GOAL, ShotOutcome.MADE),
    ("2PT Missed", StatisticKind.TWO_POINT_FIELD_GOAL, ShotOutcome.MISSED),
    ("3PT Made", StatisticKind.THREE_POINT_FIELD_GOAL, ShotOutcome.MADE),
    ("3PT Missed", StatisticKind.THREE_POINT_FIELD_GOAL, ShotOutcome.MISSED),
    ("FT Made", StatisticKind.FREE_THROW, ShotOutcome.MADE),
    ("FT Missed", StatisticKind.FREE_THROW, ShotOutcome.MISSED),
    ("Offensive Rebound", StatisticKind.OFFENSIVE_REBOUND, None),
    ("Defensive Rebound", StatisticKind.DEFENSIVE_REBOUND, None),
    ("Assist", StatisticKind.ASSIST, None),
    ("Steal", StatisticKind.STEAL, None),
    ("Turnover", StatisticKind.TURNOVER, None),
)


class GameEntryApp:
    """A deliberately small UI over GameSession for manual backend testing."""

    def __init__(
        self,
        root: tk.Tk,
        configuration: TournamentConfiguration,
        database_path: Path,
        export_directory: Path,
    ) -> None:
        self.root = root
        self.configuration = configuration
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository = SQLiteGameRepository(database_path)
        self.export_directory = export_directory
        self.session: GameSession | None = None
        self.team_ids: tuple[str, str] | None = None
        self.player_choices: dict[str, dict[str, str]] = {}
        self.player_variables: dict[str, tk.StringVar] = {}
        self.action_buttons: list[ttk.Button] = []
        self.export_button: ttk.Button | None = None

        self.root.title("Basketball Stats Tracker — Scorer Prototype")
        self.root.minsize(1000, 700)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.score_text = tk.StringVar(value="Create a game to begin")
        self.status_text = tk.StringVar(value=f"SQLite: {database_path}")
        self.game_id_text = tk.StringVar(
            value=f"demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        self.game_date_text = tk.StringVar(value=date.today().isoformat())
        team_labels = [self._team_label(team) for team in configuration.teams]
        self.team_label_to_id = {
            self._team_label(team): team.team_id for team in configuration.teams
        }
        self.home_team_text = tk.StringVar(value=team_labels[0])
        self.away_team_text = tk.StringVar(value=team_labels[1])

        self._build_setup()

    def _build_setup(self) -> None:
        self.setup_frame = ttk.Frame(self.root, padding=16)
        self.setup_frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        ttk.Label(
            self.setup_frame,
            text="Start a Test Game",
            font=("TkDefaultFont", 18, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(self.setup_frame, text="Game ID").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.setup_frame, textvariable=self.game_id_text, width=34).grid(
            row=1, column=1, sticky="ew", pady=4
        )
        ttk.Label(self.setup_frame, text="Game date (YYYY-MM-DD)").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(self.setup_frame, textvariable=self.game_date_text, width=34).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Label(self.setup_frame, text="Home team").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            self.setup_frame,
            textvariable=self.home_team_text,
            values=list(self.team_label_to_id),
            state="readonly",
            width=31,
        ).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(self.setup_frame, text="Away team").grid(row=4, column=0, sticky="w")
        ttk.Combobox(
            self.setup_frame,
            textvariable=self.away_team_text,
            values=list(self.team_label_to_id),
            state="readonly",
            width=31,
        ).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Button(self.setup_frame, text="Start Game", command=self._start_game).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        ttk.Label(self.setup_frame, textvariable=self.status_text, wraplength=600).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(16, 0)
        )
        self.setup_frame.columnconfigure(1, weight=1)

    def _start_game(self) -> None:
        try:
            home_team_id = self.team_label_to_id[self.home_team_text.get()]
            away_team_id = self.team_label_to_id[self.away_team_text.get()]
            if home_team_id == away_team_id:
                raise ValueError("home and away teams must be different")
            game = GameMetadata(
                game_id=self.game_id_text.get().strip(),
                tournament_id=self.configuration.tournament_id,
                configuration_version=self.configuration.configuration_version,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                game_date=date.fromisoformat(self.game_date_text.get().strip()),
                overtime_periods=0,
                status=GameStatus.IN_PROGRESS,
            )
            self.session = GameSession.new(
                game,
                self.configuration.to_validation_context(),
                actor_id="tkinter-scorer",
                repository=self.repository,
            )
            self.team_ids = (home_team_id, away_team_id)
        except (KeyError, ValueError, GameSessionError) as error:
            messagebox.showerror("Cannot start game", str(error), parent=self.root)
            return

        self.setup_frame.destroy()
        self._build_scoring_screen()
        self._refresh()

    def _build_scoring_screen(self) -> None:
        assert self.team_ids is not None
        self.scoring_frame = ttk.Frame(self.root, padding=12)
        self.scoring_frame.grid(sticky="nsew")
        self.scoring_frame.columnconfigure(0, weight=1)
        self.scoring_frame.columnconfigure(1, weight=1)
        self.scoring_frame.rowconfigure(2, weight=1)

        ttk.Label(
            self.scoring_frame,
            textvariable=self.score_text,
            font=("TkDefaultFont", 22, "bold"),
            anchor="center",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        for column, team_id in enumerate(self.team_ids):
            self._build_team_panel(team_id, column)

        lower_frame = ttk.Frame(self.scoring_frame)
        lower_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        lower_frame.columnconfigure(0, weight=1)
        lower_frame.columnconfigure(1, weight=1)
        lower_frame.rowconfigure(1, weight=1)

        ttk.Label(lower_frame, text="Live Box Score", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(lower_frame, text="Event History", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=1, sticky="w"
        )
        self.box_score_text = tk.Text(lower_frame, height=15, width=70, state="disabled")
        self.box_score_text.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.history = tk.Listbox(lower_frame, height=15)
        self.history.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        controls = ttk.Frame(self.scoring_frame)
        controls.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        undo_button = ttk.Button(controls, text="Undo Last Stat", command=self._undo)
        undo_button.pack(
            side="left", padx=(0, 8)
        )
        undo_selected_button = ttk.Button(
            controls, text="Undo Selected Event", command=self._undo_selected
        )
        undo_selected_button.pack(side="left", padx=(0, 8))
        complete_button = ttk.Button(controls, text="Complete Game", command=self._complete_game)
        complete_button.pack(side="left")
        self.action_buttons.extend([undo_button, undo_selected_button, complete_button])
        self.export_button = ttk.Button(
            controls,
            text="Export JSON",
            command=self._export_json,
            state="disabled",
        )
        self.export_button.pack(side="left", padx=(8, 0))
        ttk.Label(controls, textvariable=self.status_text).pack(side="right")

    def _build_team_panel(self, team_id: str, column: int) -> None:
        team = self._team_by_id(team_id)
        frame = ttk.LabelFrame(self.scoring_frame, text=self._team_label(team), padding=8)
        frame.grid(row=1, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
        self.scoring_frame.rowconfigure(1, weight=0)

        choices = {self._player_label(player): player.player_id for player in team.players}
        self.player_choices[team_id] = choices
        variable = tk.StringVar(value=next(iter(choices)))
        self.player_variables[team_id] = variable
        ttk.Combobox(
            frame,
            textvariable=variable,
            values=list(choices),
            state="readonly",
            width=28,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        participation_button = ttk.Button(
            frame,
            text="Mark Player as Participating",
            command=lambda selected_team=team_id: self._mark_participation(selected_team),
        )
        participation_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.action_buttons.append(participation_button)

        for index, (label, statistic_kind, outcome) in enumerate(STAT_ACTIONS):
            button = ttk.Button(
                frame,
                text=label,
                command=lambda selected_team=team_id, kind=statistic_kind, shot_outcome=outcome: self._record_stat(
                    selected_team, kind, shot_outcome
                ),
            )
            button.grid(row=2 + index // 2, column=index % 2, sticky="ew", padx=2, pady=2)
            self.action_buttons.append(button)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _record_stat(
        self, team_id: str, statistic_kind: StatisticKind, outcome: ShotOutcome | None
    ) -> None:
        assert self.session is not None
        player_id = self.player_choices[team_id][self.player_variables[team_id].get()]
        self._run_action(
            lambda: self.session.record_stat(team_id, player_id, statistic_kind, outcome)
        )

    def _mark_participation(self, team_id: str) -> None:
        assert self.session is not None
        player_id = self.player_choices[team_id][self.player_variables[team_id].get()]
        self._run_action(lambda: self.session.mark_participation(team_id, player_id))

    def _undo(self) -> None:
        assert self.session is not None
        self._run_action(self.session.undo_last_stat)

    def _undo_selected(self) -> None:
        assert self.session is not None
        selected_indexes = self.history.curselection()
        if not selected_indexes:
            messagebox.showinfo(
                "Select an event",
                "Select a statistic in Event History, then choose Undo Selected Event.",
                parent=self.root,
            )
            return
        event = self.session.game_export.events[selected_indexes[0]]
        if not isinstance(event, StatRecordedEvent):
            messagebox.showinfo(
                "Statistic required",
                "Only recorded statistic events can be undone. Participation and prior undo records remain in the audit history.",
                parent=self.root,
            )
            return
        self._run_action(lambda: self.session.undo_stat_event(event.event_id))

    def _complete_game(self) -> None:
        assert self.session is not None
        if not messagebox.askyesno(
            "Complete game",
            "Mark this game complete? Further scorer entry will be disabled.",
            parent=self.root,
        ):
            return
        self._run_action(self.session.complete_game)

    def _export_json(self) -> None:
        assert self.session is not None
        try:
            path = export_completed_game_json(
                self.session.game_export, self.export_directory
            )
        except GameExportError as error:
            messagebox.showerror("Export failed", str(error), parent=self.root)
            return
        self.status_text.set(f"Exported JSON: {path}")
        messagebox.showinfo("Game exported", f"Saved canonical game JSON to:\n{path}", parent=self.root)

    def _run_action(self, action: object) -> None:
        try:
            state = action()  # type: ignore[operator]
        except GameSessionError as error:
            messagebox.showerror("Action not recorded", str(error), parent=self.root)
            return
        assert isinstance(state, GameSessionState)
        self._refresh(state)

    def _refresh(self, state: GameSessionState | None = None) -> None:
        assert self.session is not None
        state = state or self.session.state
        assert self.team_ids is not None
        score = state.box_score.scoreboard
        home, away = (self._team_by_id(team_id) for team_id in self.team_ids)
        self.score_text.set(
            f"{home.name}  {score[home.team_id]}    —    {score[away.team_id]}  {away.name}"
        )
        self.status_text.set(
            f"Saved locally • {len(state.game_export.events)} events • "
            f"{state.game_export.game.status.value.replace('_', ' ').title()}"
        )
        self._write_box_score(state)
        self._write_history(state)
        if state.game_export.game.status is GameStatus.COMPLETED:
            for button in self.action_buttons:
                button.state(["disabled"])
            if self.export_button is not None:
                self.export_button.state(["!disabled"])

    def _write_box_score(self, state: GameSessionState) -> None:
        lines: list[str] = []
        for team_id in self.team_ids or ():
            team = self._team_by_id(team_id)
            lines.append(f"{team.name}")
            lines.append("Player                 GP  PTS  2PT   3PT   FT  ORB  DRB  TRB  AST  STL  TOV")
            for player_score in (
                box_score
                for box_score in state.box_score.player_box_scores
                if box_score.team_id == team_id
            ):
                player = self._player_by_id(team, player_score.player_id)
                totals = player_score.totals
                lines.append(
                    f"#{player.jersey_number:<3} {player.name:<19.19} "
                    f"{player_score.games_played:>2}  {totals.points:>3}  "
                    f"{totals.two_point_made}-{totals.two_point_attempted:<3} "
                    f"{totals.three_point_made}-{totals.three_point_attempted:<3} "
                    f"{totals.free_throw_made}-{totals.free_throw_attempted:<3} "
                    f"{totals.offensive_rebounds:>3}  {totals.defensive_rebounds:>3}  "
                    f"{totals.total_rebounds:>3}  {totals.assists:>3}  "
                    f"{totals.steals:>3}  {totals.turnovers:>3}"
                )
            lines.append("")
        self.box_score_text.configure(state="normal")
        self.box_score_text.delete("1.0", tk.END)
        self.box_score_text.insert("1.0", "\n".join(lines))
        self.box_score_text.configure(state="disabled")

    def _write_history(self, state: GameSessionState) -> None:
        self.history.delete(0, tk.END)
        for event in state.game_export.events:
            self.history.insert(tk.END, self._event_label(event))
        self.history.yview_moveto(1)

    def _event_label(self, event: object) -> str:
        if isinstance(event, StatRecordedEvent):
            player = self._player_name(event.team_id, event.player_id)
            outcome = f" {event.outcome.value}" if event.outcome is not None else ""
            return f"#{event.sequence}  {player} — {event.statistic_kind.value}{outcome}"
        if isinstance(event, PlayerParticipationMarkedEvent):
            return f"#{event.sequence}  {self._player_name(event.team_id, event.player_id)} — participated"
        if isinstance(event, EventVoidedEvent):
            return f"#{event.sequence}  Undid event — {event.target_event_id}"
        return f"#{event.sequence}  Unknown event"

    def _team_by_id(self, team_id: str) -> TeamConfiguration:
        return next(team for team in self.configuration.teams if team.team_id == team_id)

    @staticmethod
    def _player_by_id(team: TeamConfiguration, player_id: str):
        return next(player for player in team.players if player.player_id == player_id)

    def _player_name(self, team_id: str, player_id: str) -> str:
        team = self._team_by_id(team_id)
        player = self._player_by_id(team, player_id)
        return f"#{player.jersey_number} {player.name}"

    @staticmethod
    def _team_label(team: TeamConfiguration) -> str:
        return f"{team.name} ({team.abbreviation})"

    @staticmethod
    def _player_label(player: PlayerConfiguration) -> str:
        return f"#{player.jersey_number} — {player.name}"

    def _close(self) -> None:
        self.repository.close()
        self.root.destroy()


def main() -> None:
    project_root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description="Run the basketball scorer prototype")
    parser.add_argument(
        "--config",
        type=Path,
        default=project_root / "examples/tournament_configuration_v1.json",
        help="path to a tournament configuration JSON file",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=project_root / "data/scorer_demo.sqlite3",
        help="path to the local SQLite game database",
    )
    parser.add_argument(
        "--export-directory",
        type=Path,
        default=project_root / "data/exports",
        help="folder for completed portable game JSON exports",
    )
    args = parser.parse_args()

    configuration = load_tournament_configuration(args.config)
    root = tk.Tk()
    GameEntryApp(root, configuration, args.database, args.export_directory)
    root.mainloop()


if __name__ == "__main__":
    main()
