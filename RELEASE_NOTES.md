# TG:BTC Arena Companion 6.0.0 — Arena Intelligence Suite

V6.0 combines the planned 5.9 Opponent Intelligence upgrade with the first Battle Strategy Engine.

## Opponent Scanner
- Add samples for any enemy hero from the new **Intelligence** page.
- Existing Owl Smart Dodge samples are reused automatically.
- Multi-sample hero recognition with configurable threat weights.
- Separate opponent username OCR calibration.

## Decision Engine + Threat Score
- Fuses Organization Bot/Real detection with queue-model confidence.
- LOW / MEDIUM / HIGH / NIGHTMARE threat rating.
- Uses opponent identity, detected heroes, queue class, repeated-opponent memory and historical matchup results.
- Presets: **Safe Climb**, **Maximum Matches**, **Master Push**, **No Dodge**.
- Custom DODGE/PLAY rules can require identity, hero combinations and minimum threat.

## Opponent Memory + Live Battle HUD
- Remembers repeated usernames and their W/L/dodge history.
- Dashboard now shows identity confidence, username, recognized heroes, threat and current decision during battle.

## Replay / Result Analysis
- Stores up to 100 opening battle snapshots in AppData.
- Double-click a History row to open its snapshot.
- History now records opponent username, hero composition, threat, decision, profile and battle strategy.
- Learns worst-performing heroes and enemy combinations from played results.

## Profiles, Goals + Notifications
- Strategy page can switch decision profiles instantly.
- Session goals: target Points, Matches or Net Points.
- Windows notifications for Master V, goal completion, Arena closing soon and critical system-health issues.

## Battle Strategy Engine V1
- Disabled by default until explicitly enabled.
- Calibrate named in-battle action coordinates.
- Build timed steps with optional REAL/BOT, required-hero and minimum-threat conditions.
- Can run alongside game AUTO or with AUTO suppressed.
- Missing/unrecognized action coordinates are skipped and logged — never guessed.

## Diagnostics integration
- Diagnostics now also reports Opponent Intelligence and Strategy readiness.

Existing Fast Vision, Wireless ADB, OCR, Smart Dodge, custom dark chrome, persistent history/profile data, self-healing and GitHub updater are preserved.
