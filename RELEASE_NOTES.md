# TG:BTC Game Assistant 7.0.1 — Daily Assistant UI Fix

Hotfix for the blank Daily Assistant page introduced in 7.0.0.

## Fixed
- Daily Assistant cards now render correctly.
- Corrected misuse of `_make_card()`, which returns `(card, body)` rather than a single widget.
- Corrected `UI_MUTED2` typo to the existing `UI_MUTED_2` palette constant.
- Verified all seven Daily modules are created: Mail, Events, Shop, Recruit, Quest Pass, Idle Rewards, and Current Screen.

No daily-route logic or Arena/Intelligence/Strategy behavior was changed in this hotfix.
