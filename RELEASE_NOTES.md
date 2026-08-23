# TG:BTC Game Assistant 7.1.2 — Turbo Daily + Updater Fix

## Much faster Daily Assistant
- Safe-action OCR is now about 3–5x faster on the recorded TG:BTC screens by recognizing on a scaled frame and mapping taps back to the full reference canvas.
- Daily navigation reacts to the first changed Fast Vision frame instead of sitting through long fixed delays.
- Daily Fast Vision targets 24 FPS and keeps warming in the background if Android's encoder starts slowly.
- HOME and Idle Farming verification use visual fingerprints and no longer invoke unnecessary OCR.
- Duplicate route verification and normal-run debug PNG writes were removed from the hot path.
- Shop and Quest Pass tab traversal is frame-driven instead of repeatedly waiting on multi-second OCR loops.

## Verified Home retry
- Every automated return Home verifies that the Home screen is actually visible.
- If Home is not visible, the assistant repeats the Home action automatically, up to 4 verified attempts.
- Daily Assistant still never sends Android Back.

## Updater reliability
- Fixes the misleading `Installed v7.1.0 / Latest v7.1.0` state by publishing this build through the normal GitHub Release channel used by existing installations.
- From v7.1.2 onward, the built-in checker also compares GitHub Releases with `main/VERSION` so a delayed Release cannot hide a newer build.
- When main is newer than Releases, the app can reconstruct and SHA-validate the full source from a source manifest.

## Preserved
- Explicit `CLAIM / CLAIM ALL / FREE` safe-action policy.
- Run All Safe, individual Daily modules, DRY RUN, STOP, routes, summaries, Arena, Smart Dodge, Intelligence and Strategy.
- AppData profile/history/calibration data remains untouched.
