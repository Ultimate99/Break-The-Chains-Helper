# TG:BTC Game Assistant 7.0.7 — Daily Debug & Calibration

Field-debug release for the modular Daily Assistant.

## Added
- `DRY RUN` button on every Daily module. It never sends phone taps.
- Current Screen DRY RUN highlights any detected safe `CLAIM / CLAIM ALL / FREE` actions.
- Per-module `STOP` buttons.
- 120-second module watchdog so a Daily task cannot stay RUNNING forever.
- Live debug line showing physical phone resolution and reference-to-phone coordinate mapping.
- Route debugger: DRY RUN logs every stored route point as `reference -> physical phone` coordinates.
- Before/after screenshots for route taps and safe-action taps.
- `OPEN DEBUG FOLDER` shortcut. Captures are stored under `%APPDATA%\TG-BTC-Arena-Companion\daily_debug`.

## Preserved
- v7.0.6 physical tap-scaling fix.
- v7.0.5 Tk thread-safety and stale Wireless ADB fixes.
- Daily Assistant never sends Android BACK automatically.
- SAFE MODE still only automates explicit `CLAIM`, `CLAIM ALL`, and `FREE` actions; it does not intentionally spend premium currency or tickets.

This build is intentionally more verbose/slower during normal Daily runs because it captures evidence around each automated tap so remaining route or recognition issues can be diagnosed from actual frames instead of guessing.
