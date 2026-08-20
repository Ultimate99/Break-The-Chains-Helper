# Break The Chains Helper

TG:BTC Arena Companion helper project.

This repository is the GitHub Releases update source for the desktop Arena Companion.

## In-app updater

The Companion checks this repository for the latest published GitHub Release.

Starting with the cleaned update UI:
- A compact update icon lives in the top-right app bar.
- Normal / up-to-date state stays neutral.
- When a newer release exists, the icon changes to the update state and shows a small `1` badge.
- Clicking the icon opens the available release and Update action.
- Update source/debug controls are kept out of the main action row to keep the UI clean.

User calibration, Owl samples, Smart Dodge settings, and session history live in `%APPDATA%\\TG-BTC-Arena-Companion` and are preserved across updates.
