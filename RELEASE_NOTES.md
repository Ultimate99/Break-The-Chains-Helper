# TG:BTC Game Assistant 7.2.1 — HOME Vision Hotfix

## Fixed: Daily Assistant could reject the real Home screen
- Fixes a V7.2 issue where live Home animation/art differences could push the perceptual-hash distance outside the strict recorded threshold and block Daily Assistant with `vision=UNKNOWN`.
- HOME verification now has a **bounded HOME-only soft match** when HOME is still the nearest known screen.
- The soft HOME limit is `d <= 20.0`; the reported failing live frame at `d=17.0` is accepted.

## Safety unchanged
- The relaxed rule applies **only to HOME verification**.
- Mail, Shop, Quest, Events, Recruit, Chain Campaign, Idle popup and reward-overlay checks keep their original strict visual matching.
- Safe-action rules remain unchanged: only literal **CLAIM**, **CLAIM ALL** and **FREE** can become action targets.
- BUY, EXCHANGE, USE, SWEEP, START, GO NOW and spend actions remain blocked.
- Android Back is still never used to find Home.

## Update reliability
- Keeps the V7.2 GitHub Release updater and checksum-verified `current_source_manifest.json` fallback.
- AppData profile, history, calibration and user settings remain untouched.
