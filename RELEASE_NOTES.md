# TG:BTC Game Assistant 7.0.4 — Daily Home OCR Fix

Fixes Daily Assistant modules incorrectly showing ERROR even when started from the game Home screen.

## Fixed
- Removed the unreliable OCR-based Home verification gate. TG:BTC's stylized Home labels are not consistently readable by Tesseract.
- Daily modules now follow the explicit contract: start them from Home; the assistant does not try to prove Home first.
- Daily Assistant still never sends Android Back automatically.
- Module cards now show useful failure states such as `NO ADB`, `OCR MISSING`, and `NEEDS ROUTE` instead of a generic `ERROR`.
- Other failures display a shortened reason directly on the module card.
- Daily startup initializes the engine device from the connected ADB device when available.

Existing safe-action rules remain unchanged: only explicit CLAIM / CLAIM ALL / FREE actions are automated by the Daily collector.
