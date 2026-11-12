# Basketball Tournament Statistics System

## Design Plan

**Document purpose:** Preserve the current system design so
implementation can continue later, including in a separate ChatGPT
conversation or development environment.

**Status:** Design finalized for the MVP; implementation not yet complete.\
**Primary language:** Python\
**Target environment:** Windows computers used by tournament
scorekeepers and organizers.

------------------------------------------------------------------------

## 1. Project Overview

The system will replace manually maintained Excel box scores and
tournament-total spreadsheets with a lightweight, event-based basketball
statistics application.

Each game is entered on a dedicated computer. The scorer records
box-score statistics as they happen by incrementing a player's stat (for
example, a made two-point shot or a defensive rebound). The application
maintains the live score and player totals, saves the game locally, and
exports a portable game file.

After games are complete, an organizer imports the individual game files
into a tournament-management tool. The tool validates the data, combines
game results, calculates tournament totals, and generates reports.

The system is intended for **box-score statistics**, not full
play-by-play. It does not track the game clock or require a record of
every possession.

### Core goals

-   Make live stat entry fast and simple.
-   Reduce manual arithmetic and spreadsheet errors.
-   Track makes and attempts separately for all shooting categories.
-   Support multiple games being scored simultaneously on separate
    computers.
-   Keep each game's data in a separate portable file.
-   Allow a scorer to void any earlier active statistic during live game
    entry, with a visible event history.
-   Record player participation so tournament games-played totals are
    accurate, including for a player with no other recorded statistic.
-   Display a live scoreboard.
-   Produce consistent game and tournament reports.
-   Generate printable box scores for a physical wall and graphics
    suitable for social media.

### Non-goals

-   Full play-by-play descriptions.
-   Game-clock or shot-clock tracking.
-   Possession-by-possession analytics.
-   Live synchronization between scorer computers.
-   Requiring an internet connection during game entry.

------------------------------------------------------------------------

## 2. High-Level Architecture

The system has two primary applications that share calculation,
validation, and data-format code.

### A. Game Entry Application

Runs on a computer assigned to one game.

Responsibilities:

-   Load the tournament configuration and the two participating team
    rosters.
-   Allow a scorer to select a player and increment that player's
    statistics.
-   Update the live scoreboard and box-score totals immediately.
-   Record each stat adjustment as an event.
-   Support undo of the most recent or a selected earlier statistic.
-   Display event history.
-   Record the players who participated in the game.
-   Automatically save the game locally.
-   Export the game to a portable JSON file.

Each computer can score a different game independently. No central
server is required during the tournament.

### B. Tournament Management Application

Runs separately, typically on an organizer's computer.

Responsibilities:

-   Import game JSON files from all scorer computers.
-   Validate game identity, roster membership, events, and score
    calculations.
-   Detect duplicate games and duplicate event identifiers.
-   Preserve the immutable event/void audit history.
-   Recalculate player, team, and tournament totals from the underlying
    game events.
-   Export tournament summaries to Excel.
-   Generate printable PDF box scores and social media PNG graphics.
-   Allow reports to be regenerated from archived game data.

### C. Shared Python Package

Both applications use the same shared package for:

-   Data models and identifiers.
-   Stat definitions.
-   Box-score calculations.
-   Event application and reversal.
-   Validation rules.
-   JSON serialization and schema versioning.
-   Report data preparation.

The tournament-management application should independently recalculate totals
from the imported events. It should not blindly trust precomputed totals
included in a game export.

### Architecture diagram

``` text
             Tournament Configuration
              (teams, players, IDs)
                       |
          +------------+------------+
          |                         |
   Game Entry Computer 1      Game Entry Computer 2
       Game A                     Game B
          |                         |
     Local SQLite              Local SQLite
          |                         |
     Export JSON               Export JSON
          |                         |
          +------------+------------+
                       |
          Tournament Management App
                       |
              Import and Validate
                       |
              Validate / Audit
                       |
              Recalculate Totals
                       |
          +------------+-------------+
          |            |             |
       Excel         PDF           PNG
    Tournament    Printable     Social media
      workbook    box scores     graphics
```

------------------------------------------------------------------------

## 3. Technology Stack

  -----------------------------------------------------------------------
  Area                    Recommended technology  Purpose
  ----------------------- ----------------------- -----------------------
  Language                Python 3                Application and shared
                                                  logic

  Desktop GUI             Tkinter for initial     Game entry and
                          MVP; CustomTkinter if a tournament-management
                          more polished interface interfaces
                          is desired              

  Local game storage      SQLite                  Autosave and recovery
                                                  during game entry

  Portable game format    JSON                    Moving games between
                                                  computers

  Spreadsheet output      openpyxl                Excel tournament
                                                  workbook

  PDF output              ReportLab               Printable box scores

  Image output            Pillow                  Social media graphics

  Testing                 pytest                  Unit and integration
                                                  tests

  Windows packaging       PyInstaller             Distributable
                                                  executable applications
  -----------------------------------------------------------------------

The report-generation logic should be separate from the GUI so that
reports can be regenerated later without opening the game-entry
application.

------------------------------------------------------------------------

## 4. Tournament Configuration and Rosters

Each scorer computer must use the same tournament configuration version.
The version-1 configuration contract is defined in
`schemas/tournament_configuration_v1.schema.json`; a complete example
is `examples/tournament_configuration_v1.json`.

The configuration should include:

-   Tournament ID and name.
-   Separate configuration and schema versions.
-   Team IDs and team names.
-   Team abbreviations.
-   Optional primary and secondary team colors.
-   Player IDs.
-   Player names.
-   Jersey numbers.
-   Player-to-team relationships.

Tournament logos and player availability/roster-status settings are
deferred. In version 1, every player listed under a team is eligible for
that team's roster.

Use stable IDs rather than names as the underlying identifiers. Names
and jersey numbers can change or be duplicated; IDs should remain
unique.

A game should reference the tournament ID, configuration version, game
ID, and the two participating team IDs.

The locked version-1 structure is:

``` json
{
  "schema_version": 1,
  "tournament_id": "tournament-2026",
  "name": "Example Basketball Tournament 2026",
  "configuration_version": 1,
  "teams": [
    {
      "team_id": "team-001",
      "name": "Example Team",
      "abbreviation": "EXAMPLE",
      "primary_color": "#123456",
      "players": [
        {
          "player_id": "player-001",
          "name": "Example Player",
          "jersey_number": "12"
        }
      ]
    }
  ]
}
```

Jersey numbers are stored as strings so values such as `00` retain their
display form. The typed configuration loader validates globally unique
team and player IDs, then produces the roster-validation context used by
game entry and import validation.

------------------------------------------------------------------------

## 5. Game Entry Workflow

### Starting a game

1.  Select or create a game.
2.  Confirm the two teams.
3.  Load each team's roster from the tournament configuration.
4.  Confirm or later mark the players who participated. This is used to
    calculate games played and does not enforce an on-court lineup.
5.  Open the live scoring screen.

### Recording statistics

The scorer selects a team and player, then presses a stat button or uses
a keyboard shortcut.

A stat action creates an event. The application applies that event to
the running box score, updates the scoreboard if appropriate, and
appends the event to the event history.

The scorer should not need to calculate totals manually.

### Shooting statistics

Track makes and attempts separately:

  -----------------------------------------------------------------------
  Action                              Effect
  ----------------------------------- -----------------------------------
  2PT made                            2-point field goals made +1;
                                      2-point attempts +1; points +2

  2PT missed                          2-point attempts +1

  3PT made                            3-point field goals made +1;
                                      3-point attempts +1; points +3

  3PT missed                          3-point attempts +1

  FT made                             Free throws made +1; free throw
                                      attempts +1; points +1

  FT missed                           Free throw attempts +1
  -----------------------------------------------------------------------

Derived shooting percentages:

-   2PT percentage = 2PT made / 2PT attempts.
-   3PT percentage = 3PT made / 3PT attempts.
-   FT percentage = FT made / FT attempts.
-   Field goals made = 2PT made + 3PT made.
-   Field goal attempts = 2PT attempts + 3PT attempts.
-   Field goal percentage = field goals made / field goal attempts.

If attempts are zero, display the percentage as `—` or `0.0%`
consistently; do not divide by zero.

### Other player statistics

Track at minimum:

-   Offensive rebounds.
-   Defensive rebounds.
-   Total rebounds (derived).
-   Assists.
-   Steals.
-   Turnovers.
-   Points (derived from made shots).

Additional stats can be added later if tournament requirements change.
Avoid adding statistics that are not actually collected.

Blocks and personal fouls are deliberately out of scope for the MVP
because this tournament does not collect them. They must not appear as
hidden event types; adding either later requires a planned schema,
calculation, report, and test update.

### Game-rule scope

Overtime is supported: stat entry continues normally and all overtime
statistics are included in the same game totals. The game metadata
records the number of overtime periods for reporting.

The MVP does not support special score adjustments, own goals, team
rebounds, technical or bench fouls, forfeits, or other exceptional
rule-specific events. Those cases are explicitly out of scope rather
than being approximated with player statistics.

### Live scoreboard

-   Display each team's current score prominently.
-   Score is derived from made field goals and free throws.
-   Update immediately after a made-shot event.
-   Recalculate after every void.
-   The score shown on the entry screen must agree with the sum of
    player points and team scoring totals.

### Keyboard shortcuts

Provide shortcuts for common stat actions to speed up entry.

The exact key map should be configurable and displayed in the interface.
Avoid relying on a shortcut scheme that conflicts with normal text entry
or operating-system shortcuts.

The interface should make the currently selected player and team obvious
before a shortcut is applied.

### Event history and undo

Every stat adjustment is an event. The interface should show a concise
recent-event list, such as:

-   `#12 Player Name — 2PT made`
-   `#4 Player Name — Defensive rebound`
-   `#8 Player Name — Turnover`

The scorer can undo the most recent effective stat event. Undo must
append an `event_voided` event that identifies the original event and
the reason (`scorer_undo`); it must not delete or modify the original
event. The calculation layer excludes a voided event from effective
totals while retaining both records in the audit history.

If an action is re-entered after an undo, it is a new stat event with a
new identifier. The first release does not need a separate redo button.

The event history is an operational record of stat adjustments, not a
full play-by-play feed. No game clock is required.

### Player participation and lineups

The MVP does not track substitutions, active lineups, or minutes
played. It must make every rostered player easy to select for stat
entry; it must not restrict the scorer to five player buttons or enforce
five-player lineups.

At game setup or before completion, the scorer marks participating
players. A `player_participation_marked` event records the player and
team. A player's **games played** total is the number of accepted games
in which that player has an effective participation marker. This avoids
excluding players who played but did not record a box-score statistic.
Only one effective participation marker is allowed per player per game.

Before accepting a player's first stat event, the game-entry application
must create a participation marker for that player if no effective marker
already exists. The scorer manually marks only players who participated
but recorded no statistic.

The interface may visually group or pin commonly used players for speed,
but this is a presentation convenience, not substitution tracking.

------------------------------------------------------------------------

## 6. Event and Data Model

### Phase 1 contract: supported statistics and event types

The following vocabulary is locked for the MVP. A statistic is always
recorded as one event for one player; totals, points, total rebounds,
and percentages are derived and are never entered directly.

**Supported player statistic kinds**

| Statistic kind | Required outcome | Derived effect |
| --- | --- | --- |
| `two_point_field_goal` | `made` or `missed` | A made shot adds 2 points; either outcome adds one 2PT attempt. |
| `three_point_field_goal` | `made` or `missed` | A made shot adds 3 points; either outcome adds one 3PT attempt. |
| `free_throw` | `made` or `missed` | A made free throw adds 1 point; either outcome adds one FT attempt. |
| `offensive_rebound` | none | Adds one offensive rebound. |
| `defensive_rebound` | none | Adds one defensive rebound. |
| `assist` | none | Adds one assist. |
| `steal` | none | Adds one steal. |
| `turnover` | none | Adds one turnover. |

`made` and `missed` are valid only for the three shooting statistic
kinds. A non-shooting statistic must not carry an outcome. The MVP has
no direct score-adjustment or team-stat event; the scoreboard is always
derived from effective player shooting events.

**Supported event types**

| Event type | Purpose | Contributes to totals? |
| --- | --- | --- |
| `stat_recorded` | Records one supported player statistic. | Yes, unless later voided. |
| `player_participation_marked` | Records that one player participated in a game. | Only to games played, unless later voided. |
| `event_voided` | Makes one earlier statistic ineffective while preserving it for audit. | No. |

This list is intentionally closed for the MVP. Adding a new statistic
or event type later requires a schema version change, calculation tests,
and report updates.

### Append-only event model

The primary record of what happened in a game is an append-only ordered
sequence of events. Existing events are never edited or deleted. The
calculation layer derives the effective game state from the event list.

### Event field contract

Each event is a JSON object. Its common fields are:

| Field | JSON type | Required | Rule |
| --- | --- | --- | --- |
| `event_id` | string | Yes | Unique, opaque identifier for this event within the game. |
| `game_id` | string | Yes | Must equal the enclosing game's ID. |
| `sequence` | integer | Yes | Starts at 1, is unique, and increases without gaps in the exported event list. |
| `recorded_at` | string | Yes | ISO 8601 UTC timestamp ending in `Z`; audit metadata, not a game clock. |
| `event_type` | string | Yes | One of the three locked event types. |
| `actor_id` | string | No | Identifies the scorer when known. |

Type-specific fields are:

| Event type | Required fields | Conditional and validation rules |
| --- | --- | --- |
| `stat_recorded` | `team_id`, `player_id`, `statistic_kind` | `statistic_kind` must be from the locked statistic list. `outcome` is required and is `made` or `missed` for shooting kinds; it is absent for all other kinds. |
| `player_participation_marked` | `team_id`, `player_id` | There may be only one effective marker for the same player in one game. |
| `event_voided` | `target_event_id` | Target must be an earlier active `stat_recorded` event in the same game. A target may be voided only once. |

While the game is in progress, the scorer may void the most recent or
any selected earlier active statistic. The scorer then records a new
statistic when a replacement is needed. Participation markers are not
selectively voidable in the MVP because an active statistic must always
retain a participation marker.

### Game-export envelope

Every portable game JSON file has this top-level structure:

| Field | JSON type | Required | Rule |
| --- | --- | --- | --- |
| `schema_version` | integer | Yes | `1` for this initial contract. |
| `export_revision` | integer | Yes | Positive integer, incremented for each export of the same game. |
| `exported_at` | string | Yes | ISO 8601 UTC timestamp ending in `Z`. |
| `game` | object | Yes | Game metadata described below. |
| `events` | array | Yes | Events sorted by ascending `sequence`. |

The `game` object contains `game_id`, `tournament_id`,
`configuration_version`, `home_team_id`, `away_team_id`, `game_date`
(`YYYY-MM-DD`), `overtime_periods` (a non-negative integer), and
`status` (`in_progress` or `completed`). Roster-snapshot and final
revision-ownership decisions remain intentionally deferred.

See `examples/valid_game_export_v1.json` for a complete valid example
containing participation, a most-recent undo, a selected earlier-stat
void, and overtime metadata.

The machine-readable structural contract is
`schemas/game_export_v1.schema.json`. JSON Schema validates the export's
shape, allowed fields, and event-specific field combinations. The shared
application validator additionally enforces rules that JSON Schema
cannot compare across array items, including unique IDs, contiguous
sequences, valid void targets, and roster membership.

`examples/invalid_game_export_v1_nonshooting_outcome.json` is an
intentionally invalid fixture: an assist incorrectly includes a shooting
outcome. Schema validation must reject it.

Only effective `stat_recorded` and
`player_participation_marked` events contribute to calculated totals.
An event may be voided only once, and a void event cannot itself be
voided in the MVP. A scorer corrects an accidental undo by recording a
replacement statistic rather than reactivating historical data.

The timestamp is metadata for audit and troubleshooting. It is **not** a
game clock and should not be presented as one.

### Why store events instead of only totals?

-   Undo can reverse the last action.
-   The event history is visible to the scorer.
-   Voided statistics remain auditable.
-   Totals can be recalculated if calculation logic changes.
-   The management tool can verify the game rather than trusting manually
    entered totals.

### Derived box-score totals

Player totals should be calculated from effective events. Do not treat
displayed totals as the authoritative source of truth.

### Calculation contract

Calculate a game's box score as follows:

1.  Validate the event list's structural rules, including sequence
    ordering and valid void targets.
2.  Collect the targets of all valid `event_voided` events.
3.  An event is **effective** only when it is a `stat_recorded` or
    `player_participation_marked` event and its ID is not a void target.
    `event_voided` events never directly add to box-score totals.
4.  Start every rostered player at zero. Process effective stat events
    using the mapping below; a rostered player with no events remains a
    zero-stat row.
5.  Mark a player as having played, and assign one game played for this
    game, when the player has an effective participation marker.
6.  Sum player stat lines by team to produce team totals. There are no
    direct team-stat events in the MVP.

| Effective `statistic_kind` | Calculation |
| --- | --- |
| `two_point_field_goal`, `made` | `2PTM +1`, `2PTA +1`, `points +2` |
| `two_point_field_goal`, `missed` | `2PTA +1` |
| `three_point_field_goal`, `made` | `3PTM +1`, `3PTA +1`, `points +3` |
| `three_point_field_goal`, `missed` | `3PTA +1` |
| `free_throw`, `made` | `FTM +1`, `FTA +1`, `points +1` |
| `free_throw`, `missed` | `FTA +1` |
| `offensive_rebound` | `ORB +1` |
| `defensive_rebound` | `DRB +1` |
| `assist` | `AST +1` |
| `steal` | `STL +1` |
| `turnover` | `TOV +1` |

Derived fields are `TRB = ORB + DRB`, `FGM = 2PTM + 3PTM`, and
`FGA = 2PTA + 3PTA`. The game score is the sum of effective player
points for each team. Percentages are calculated from aggregate makes
and attempts: `2PT% = 2PTM / 2PTA`, `3PT% = 3PTM / 3PTA`, `FT% = FTM /
FTA`, and `FG% = FGM / FGA`.

When an attempt count is zero, the calculation result is `null` rather
than zero. Reports and the UI render `null` consistently as `—`; they
must not render it as `0.0%` or attempt division by zero.

The output must satisfy these invariants: makes never exceed attempts,
`TRB` equals `ORB + DRB`, team totals equal the sum of player totals,
and each team's score equals its players' points. The event order does
not otherwise affect totals after effective events are determined.

The expected calculation for
`examples/valid_game_export_v1.json` is recorded in
`examples/valid_game_export_v1_expected_box_score.json` and will become
a fixture for the Phase 1 calculation tests.

The shared implementation is `src/stats_tracker/calculations.py`. It
accepts a semantically valid game export and the configured rosters for
its two teams, returns immutable player and team box scores, and keeps
the calculation independent of the GUI and storage layers.

### Game metadata

A game record should include:

-   Unique game ID.
-   Tournament ID.
-   Configuration version.
-   Team IDs.
-   Game date.
-   Optional round, court, pool, or game number.
-   Number of overtime periods, defaulting to zero.
-   Game status (for example, in progress, completed, or exported).
-   Data/schema version.
-   Export revision number.

------------------------------------------------------------------------

## 7. Storage and File Management

### During game entry

Use a local SQLite database for the active game.

Benefits:

-   Frequent autosaving.
-   Better resilience than keeping all state only in memory.
-   Recovery after an application crash or computer restart.
-   Structured event storage.

The application should save after every event or use a very short,
reliable transaction interval.

The shared SQLite repository stores game metadata and each event in
separate tables. Every save runs in one transaction: an existing event
history is immutable, while only new events may be appended. A
game-session action validates first, writes the candidate state to SQLite,
and only then updates its in-memory state. Restart recovery reloads the
saved game export and resumes from its event list.

Do not use one hard-coded database filename for every game if multiple
games may be handled on the same computer over time. Each game should
have its own database or a clearly managed game-specific record.

### Export format

Export each completed game as an individual JSON file.

Suggested filename:

``` text
<TournamentID>_<GameID>_rev<Revision>.json
```

Example:

``` text
tournament-2026_game-014_rev1.json
```

The JSON file should include the game metadata, participating
team/roster references, event list, schema version, and export revision.

The scorer application exports only completed games. It writes the
canonical `GameExport` event record—not a derived box-score snapshot—to
an atomically replaced JSON file, so it can be imported, audited, and
recalculated on another computer. The current implementation is
`src/stats_tracker/exporter.py`.

### Import and duplicate handling

The tournament-management application should identify a game by its stable game ID, not
by filename.

-   First import: create the game record.
-   Same game and same revision: identify as already imported.
-   Same game with a newer revision: offer a controlled
    replacement/update workflow.
-   Same game with a conflicting revision: flag for organizer review.
-   Never silently add the same game twice to tournament totals.

Keep original imports or backups so that an organizer can recover
from an accidental replacement.

------------------------------------------------------------------------

## 8. Tournament Management and Validation

### Import validation

At minimum, validate:

-   JSON can be parsed.
-   Schema version is supported.
-   Tournament ID is expected.
-   Game ID is present and valid.
-   Both team IDs exist.
-   Players exist in the configured rosters.
-   Each player belongs to the team recorded on the event.
-   Event IDs are unique within the game.
-   Event sequence numbers are valid.
-   No player has more than one effective participation marker in the
    same game.
-   Stat/event types are supported.
-   Made shots also count as attempts.
-   Made shots and attempts are nonnegative.
-   Makes do not exceed attempts.
-   Team score reconciles with player points.
-   Game and revision identifiers are consistent.

### Semantic validation

After a JSON file passes the structural JSON Schema and is parsed into
typed models, the shared semantic validator checks rules that compare
events with each other or with the selected tournament configuration.
It receives the game export plus a context containing the expected
tournament ID, configuration version, team IDs, and player rosters.

The validator returns all detected issues in one result rather than
stopping at the first error. The importer accepts a game into official
totals only when that result contains no blocking errors.

The MVP semantic validator checks:

-   Tournament and configuration-version match.
-   Game teams, event teams, player roster membership, and player-team
    membership.
-   Unique event IDs, contiguous sequence numbers, and event/game ID
    match.
-   Void targets exist earlier in the game, are statistic events, and
    have not already been voided.
-   Each player has at most one effective participation marker per game.
-   Every effective statistic has an effective participation marker for
    its player.

### Errors versus warnings

Separate blocking errors from warnings.

**Blocking errors** should prevent the game from being accepted into
official tournament totals until resolved. Examples:

-   Unknown player ID.
-   Player assigned to the wrong team.
-   Duplicate event ID.
-   Invalid stat type.
-   Negative stat count.
-   Makes greater than attempts.
-   Score does not reconcile.
-   A void event targets an unknown event, a non-statistic event, or an
    event that is already voided.

**Warnings** should allow organizer review without necessarily
blocking import. Examples:

-   Unusually high value for a counted statistic.
-   Missing optional game metadata.
-   Unexpected but mathematically valid stat totals.

### Live-event voiding

There are no user roles or approval workflows in the MVP. During live
entry, any scorer can select an earlier active statistic and void it.
The application appends an `event_voided` record, recalculates totals,
and keeps the original statistic visible in history. After a game is
completed, its event list remains immutable in the MVP.

### Recalculation

The tournament-management tool should recalculate official totals from
the accepted effective event history. It should not simply add together
totals supplied by the scorer application.

------------------------------------------------------------------------

## 9. Tournament Totals and Excel Output

The tournament-management application should be able to combine all accepted games into
tournament-wide player and team statistics.

### Suggested workbook sheets

1.  **Tournament Summary**
    -   Tournament name.
    -   Games imported.
    -   Team standings or summary if standings are in scope.
    -   Overall tournament totals.
2.  **Player Tournament Totals**
    -   Player name and jersey number.
    -   Team.
    -   Games played, calculated from effective participation markers.
    -   Points.
    -   2PT, 3PT, and FT makes/attempts/percentages.
    -   Offensive, defensive, and total rebounds; assists, steals, and
        turnovers.
3.  **Team Tournament Totals**
    -   Team totals for the same applicable statistics.
    -   Shooting totals and percentages.
4.  **Game Results**
    -   Game ID/number.
    -   Teams.
    -   Final score.
    -   Date and other available game metadata.
5.  **Player Game Stats**
    -   One row per player per game.
6.  **Validation Report**
    -   Imported files.
    -   Import status.
    -   Errors and warnings.
    -   Revision information.

Use real numeric values in Excel cells and apply formatting separately.
Percentages should be calculated from total makes divided by total
attempts, not by averaging game percentages.

------------------------------------------------------------------------

## 10. Box Score Reports and Publishing

Box score reporting is a core feature, not an optional later add-on.
Reports must be generated from the same validated game data used for
tournament totals.

The tournament-management application should have a **Game Reports** area where
an organizer can select a game and generate one or more output
formats.

### A. Printable PDF box score

**Purpose:** Physical box score wall and print distribution.

Recommended format:

-   US Letter, 8.5 × 11 inches.
-   Landscape orientation is likely best for fitting both teams side by
    side.
-   Clear tournament and game heading.
-   Team names and final score.
-   Both team rosters.
-   Player jersey number and name.
-   Shooting makes, attempts, and percentages.
-   Points; offensive, defensive, and total rebounds; assists, steals,
    and turnovers.
-   Team totals.
-   Legible typography and strong table alignment.
-   Optional tournament logo and team branding.

The PDF must remain readable when printed. Avoid squeezing a full roster
into tiny text.

### B. Social media graphics

Generate PNG files suitable for posting.

**Game result graphic**

-   Recommended size: 1080 × 1350 pixels (4:5 portrait).
-   Tournament branding.
-   Team names/logos.
-   Final score.
-   Winner visually distinguished.
-   A small selection of leading performers or game highlights.
-   Clear visual hierarchy.

**Full box score graphic**

-   Recommended size: 1080 × 1080 pixels (square).
-   Detailed player statistics.
-   Team shooting totals.
-   Clear, readable tables.

If both full rosters cannot fit legibly in one square image, generate
multiple slides or separate graphics for each team. Do not reduce text
to an unreadable size simply to force everything into one image.

### C. Excel game box score

Provide an editable game-level box score in addition to the tournament
workbook. It should use the same statistics and layout conventions as
the PDF where practical.

### D. Branding configuration

Support configurable:

-   Tournament name.
-   Tournament logo.
-   Team names and optional logos.
-   Team colors.
-   Fonts or approved font choices.
-   Header/footer text.
-   Report title and displayed fields.

### E. Report regeneration

Reports should be reproducible from archived game data. The generator
should not depend on the original game-entry computer or a live GUI
session.

------------------------------------------------------------------------

## 11. User Interface Outline

### Game Entry Screen

Suggested layout:

``` text
+---------------------------------------------------------------+
| Tournament / Game Information                                |
+-------------------------------+-------------------------------+
| TEAM A                        | TEAM B                        |
| Score: 42                     | Score: 38                     |
|                               |                               |
| Player selector               | Player selector               |
| [Selected player]             | [Selected player]             |
|                               |                               |
| 2PT Made   2PT Missed          | 2PT Made   2PT Missed          |
| 3PT Made   3PT Missed          | 3PT Made   3PT Missed          |
| FT Made    FT Missed           | FT Made    FT Missed           |
|                               |                               |
| Offensive / Defensive Rebound  | Offensive / Defensive Rebound  |
| Assist / Steal / Turnover      | Assist / Steal / Turnover      |
+-------------------------------+-------------------------------+
| Recent Events                 | Participation Controls         |
| ...                           | Mark players who played        |
+-------------------------------+-------------------------------+
| Undo Last Event | Save Status | Export Game                    |
+---------------------------------------------------------------+
```

The actual interface should prioritize speed, large clickable controls,
and clear selected-player feedback.

### Tournament Management Screen

Suggested sections:

-   Import Games.
-   Imported Games / Game List.
-   Validation Issues.
-   Tournament Totals.
-   Game Reports.
-   Export Excel.
-   Configuration / Branding.

------------------------------------------------------------------------

## 12. Reliability, Backups, and Deployment

### Reliability

-   Autosave every event.
-   Recover unfinished games after a crash.
-   Show an obvious save/export status.
-   Prevent accidental game switching without saving.
-   Confirm before destructive actions.
-   Keep a backup before replacing an imported game revision.
-   Make exports repeatable and deterministic where possible.

### Multiple computers

-   Each scorer computer has the same tournament configuration.
-   Each computer can work independently and offline.
-   Each computer exports separate game JSON files.
-   The organizer collects the files later, for example using a USB
    drive or shared folder.
-   No simultaneous editing of the same game is expected.

### Deployment

Package the game-entry and tournament-management applications as Windows
executables using PyInstaller.

Provide:

-   A versioned application build.
-   A tournament configuration file.
-   A clear folder structure for active games, exports, backups, and
    reports.
-   A short scorer instruction sheet.
-   A tournament-management instruction sheet.

------------------------------------------------------------------------

## 13. Testing Plan

Use pytest for unit and integration tests.

### Calculation tests

-   Made 2PT shot adds two points and one attempt.
-   Missed 2PT shot adds one attempt and no points.
-   Made 3PT shot adds three points and one attempt.
-   Missed 3PT shot adds one attempt and no points.
-   Made FT adds one point and one attempt.
-   Missed FT adds one attempt and no points.
-   Rebounds and other counting stats increment correctly.
-   Total rebounds equal offensive plus defensive rebounds.
-   Shooting percentages handle zero attempts.
-   Team totals equal the sum of player totals.
-   Team score equals player points.

### Event tests

-   Events apply in the correct sequence.
-   Undo reverses the most recent event.
-   Undo does not corrupt earlier events.
-   Event IDs are unique.
-   Invalid events are rejected.
-   Undo appends a void event and leaves the original event unchanged.
-   Effective totals exclude voided events.
-   A selected earlier statistic appends a void event and recalculates
    totals correctly.
-   A participation marker contributes one game played, including for a
    player with no other recorded statistic.

### Storage and import tests

-   Game state survives application restart.
-   JSON export/import round trip preserves game data.
-   Duplicate game import is detected.
-   Duplicate event IDs are rejected.
-   Newer revisions are handled correctly.
-   Unknown players and wrong-team players are detected.
-   Invalid shooting totals are detected.
-   Invalid or duplicate void targets are rejected.

### Reporting tests

-   PDF can be generated for a valid game.
-   PNG result graphic can be generated.
-   Full box score graphic remains legible or splits into multiple
    slides.
-   Excel report contains correct values.
-   Reports update after a selected-stat void.
-   Reports can be regenerated from archived JSON data.

### End-to-end test

Create a sample game, mark participating players, enter events for both
teams, void one earlier selected statistic, export the game, import it
into the tournament-management application, validate it, generate
tournament totals, and generate PDF/PNG/Excel reports. Compare the
outputs with independently calculated expected values.

------------------------------------------------------------------------

## 14. Implementation Roadmap

Build in small, testable phases.

### Phase 1 --- Shared data model and calculations

-   Define tournament, team, player, game, and event models.
-   Define the append-only event types, effective-event calculation
    rules, and selected-stat voiding contract.
-   Define and document the versioned JSON schema before persisting game
    data; include stable IDs, sequence ordering, UTC timestamp format,
    and representative valid/invalid sample files.
-   Maintain the machine-readable JSON Schema alongside the written
    contract and validate sample exports against it.
-   Define the player-participation rule used for games-played totals.
-   Define the overtime metadata rule: statistics accumulate normally
    across regulation and overtime, while the game records its number of
    overtime periods. No game clock is introduced.
-   Implement calculations for player and team box scores.
-   Implement score and percentage calculations.
-   Add unit tests and schema-validation tests.

### Phase 2 --- Basic game entry

-   Load tournament configuration.
-   Create/select a game.
-   Route all scorer actions through a GUI-independent game-session
    service. The service appends canonical events, automatically records
    first participation, validates the updated game, and returns the
    recalculated box score; the GUI must not mutate totals or event lists
    directly.
-   Build the scorer interface.
-   Add stat buttons and keyboard shortcuts.
-   Add live scoreboard.
-   Add event history and undo.
-   Add SQLite autosave and recovery.

### Phase 3 --- Game completion and export

-   Add game completion and export workflow.
-   Test export/import round trips.

### Phase 4 --- Tournament management and validation

-   Build game import interface.
-   Detect duplicates and revisions.
-   Validate events and score reconciliation.
-   Build game list and validation report.
-   Preserve and display the event/void audit trail.

### Phase 5 --- Tournament totals and Excel

-   Aggregate accepted games.
-   Calculate tournament-wide player and team totals.
-   Generate formatted Excel workbook.
-   Test totals against known sample data.

### Phase 6 --- Game reports and publishing

-   Build PDF box score generation.
-   Build social media result graphic.
-   Build full box score graphic and multi-slide fallback.
-   Add branding configuration.
-   Add editable game-level Excel report.
-   Verify all reports use the same validated source data.

### Phase 7 --- Packaging and tournament testing

-   Package scorer and tournament-management applications for Windows.
-   Prepare tournament configuration workflow.
-   Test on multiple computers.
-   Test offline operation and file collection.
-   Test crash recovery, backups, and voided-event exports.
-   Prepare scorer/tournament-management instructions.

------------------------------------------------------------------------

## 15. Important Design Decisions to Preserve

These decisions are currently established and should not be changed
accidentally during implementation:

1.  **The system records box-score statistics, not full play-by-play.**
2.  **Stat entry is event-based:** each button press creates a stat
    event that updates the running box score.
3.  **There is no game-clock tracking.**
4.  **Shooting makes and attempts are tracked separately** for 2PT, 3PT,
    and FT.
5.  **Each game is handled independently** on its own scorer computer.
6.  **Game files are exported separately** and imported later by the
    tournament-management application.
7.  **Scorers can void an earlier active statistic during live entry**,
    with an immutable audit trail.
8.  **The scorer interface includes** keyboard shortcuts, a live
    scoreboard, undo last event, event history, and player
    participation markers. It does not track substitutions, lineups, or
    minutes played in the MVP.
9.  **Reports are a core requirement:** printable PDF box scores, social
    media PNG graphics, and Excel outputs.
10. **All reports and tournament totals must derive from the same
    validated game data.**

------------------------------------------------------------------------

## 16. Open Questions for Implementation

These are intentionally left open so they can be decided with the
implementation details:

-   Should the scorer be able to select a game from a list, or should
    each installation be configured for one game at a time?
-   Which exact keyboard shortcuts are most comfortable for the
    scorekeepers?
-   Should the game entry screen show all players at once or use a
    player selector?
-   What tournament branding assets (logos, colors, fonts) will be
    supplied?
-   Should social media output default to one result graphic plus a
    multi-slide full box score?
-   What exact fields and sorting should appear in the official printed
    box score?
-   Should tournament standings/win-loss records be included, or should
    the first version focus strictly on statistical totals?
-   The plan intentionally defers the immutable roster/configuration
    snapshot strategy and the final ownership rules for conflicting
    scorer and management-tool revisions. These must be decided before
    multi-tournament archival workflows are implemented.

------------------------------------------------------------------------

## 17. Handoff Instructions for a Future Implementation Session

When continuing this project in another conversation or development
environment:

1.  Treat this document as the current source of truth for product
    requirements and architecture.
2.  Preserve the decisions in Section 15 unless the project owner
    explicitly changes them.
3.  Start by reviewing any existing source code or starter project
    before rewriting it.
4.  Implement in the phases in Section 14 rather than attempting the
    entire application at once.
5.  Keep calculations and data validation independent from the GUI.
6.  Add automated tests for each new feature.
7.  Do not describe a feature as complete until it is implemented and
    tested.
8.  Keep the game JSON format versioned and document schema changes.
9.  Make report generation independent of the entry application.
10. At the end of each phase, provide a concise summary of completed
    work, tests run, known limitations, and the next implementation
    step.

**End of design plan.**
