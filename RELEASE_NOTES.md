# TG:BTC Game Assistant 7.0.3 — Windows Minimize Fix

- Fixes the custom-titlebar minimize button making the app disappear / appear to close on Windows.
- Removes the Win32 `ShowWindow(SW_MINIMIZE)` call against Tk's guessed parent HWND.
- Minimization now goes through Tk's normal `iconify()` path.
- Native window management is enabled only for the minimize transition, then the custom dark chrome is restored after remapping.
- Taskbar / Alt-Tab registration is re-applied after restore.
- Daily Assistant, Arena, Smart Dodge, Intelligence, Strategy, History and Diagnostics are otherwise unchanged.
