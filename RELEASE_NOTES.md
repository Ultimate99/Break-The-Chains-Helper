# TG:BTC Game Assistant 7.0.6 — Daily Tap Scaling Fix

Fixes Daily Assistant modules appearing to run while not actually pressing the intended game controls.

## Fixed
- Daily Assistant now synchronizes the phone's real screen size before its first navigation tap.
- Normalized 1536x709 route and OCR coordinates are correctly mapped back to the physical phone resolution (for example 2340x1080).
- Phone screenshot capture now refreshes `actual_w` / `actual_h`, keeping later OCR taps correctly scaled too.
- Empty Daily scans now stop after two confirmed empty frames instead of seven, removing the ~30+ second apparent hang when no safe action exists.
- Existing v7.0.5 thread-safety, stale-ADB, route-teaching and page-reopen fixes are preserved.

Safe-action policy remains unchanged: only explicit CLAIM / CLAIM ALL / FREE actions are automated by the Daily collector.
