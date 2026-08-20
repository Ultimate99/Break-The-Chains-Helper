# TG:BTC Game Assistant 7.0.5 — Stability Audit

Proactive stability pass after the first V7 Daily Assistant field tests.

## Fixed
- Daily worker threads no longer update Tk `StringVar` objects directly; status updates are marshalled back to the UI thread.
- Reopening Daily Assistant no longer replaces live module status variables.
- Daily route teaching no longer blocks/freezes the GUI for one second between route taps.
- Daily modules refresh the active ADB device every run instead of potentially retaining a stale Wireless ADB serial/session.
- Safe Daily scanning now waits longer through slow page transitions before concluding that no claimable action exists.
- Added a final navigation settle delay before Daily OCR starts.

## Verified
- Python compile check.
- Headless GUI smoke test for Dashboard/Daily/Intelligence/History/Strategy page switching.
- Daily status update tested from a background thread while Tk's event loop was active.

Existing Home Guard behavior remains: Daily Assistant never sends Android BACK automatically.
