# TG:BTC Game Assistant 7.0.2 — Daily Home Guard

Hotfix for Daily Assistant modules attempting to leave TG:BTC while trying to locate the Home screen.

## Fixed
- Removed every automatic Android BACK press from Daily module Home verification.
- Daily Assistant now checks the current screen read-only; it never navigates backward to find Home.
- If a module is started away from Home, it stops safely and asks the user to open Home manually.
- Current Screen collector remains navigation-free.
- Existing Mail, Events, Shop, Recruit, Quest Pass, Idle Rewards, Arena, Intelligence, Strategy, History and Diagnostics behavior is preserved.

This fixes the case where pressing START on a Daily module could send `KEYCODE_BACK` repeatedly and reach the game's exit action.
