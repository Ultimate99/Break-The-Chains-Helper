# TG:BTC Arena Companion 5.8.0 — Diagnostics + Self-Healing

V5.8 hardens unattended Arena grinding with a live health system and safe automatic recovery.

## New
- Dark in-app **System Diagnostics** page.
- Dashboard **SYSTEM HEALTHY / NEEDS ATTENTION / SYSTEM ISSUE** indicator.
- Automatic ADB health probes and reconnect after repeated failures.
- Fast Vision stale-frame watchdog with automatic stream restart.
- Persistent ADB tap-shell monitoring and restart.
- OCR worker health + stale-worker gate recovery.
- Low-frequency template diagnostics when MATCHING / LOADING stays unresolved too long.
- Annotated low-confidence debug frames saved to `%APPDATA%\TG-BTC-Arena-Companion\health_debug` (capped at 20).
- Persistent health/recovery log in `%APPDATA%\TG-BTC-Arena-Companion\health_events.jsonl`.
- Smart Dodge readiness now validates Owl samples + Quit/Confirm calibration. Missing calibration safely blocks surrender logic.
- Manual safe recovery actions: Reconnect ADB, Restart Vision, Restart Tap Shell.
- Automatic recovery counter and last-recovery summary.

V5.8 repairs transport/stream/worker failures automatically, but deliberately **does not make blind game taps** when recognition is uncertain. Existing Fast Vision, Smart Dodge, Bot/Real detection, History/Opponent Intelligence, OCR, custom dark chrome, permanent profile and updater are preserved.
