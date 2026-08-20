# Break The Chains Helper

TG:BTC Arena Companion for Real-Time Arena automation, Fast Vision, OCR rank/points tracking, Smart Dodge, session analytics, and in-app updates.

## Stable update source

The desktop Companion checks GitHub Releases from:

`Ultimate99/Break-The-Chains-Helper`

## v5.5 — Figma Dashboard

v5.5 applies the approved Figma dashboard design to the Python/Tkinter app while preserving the existing grind engine.

Highlights:
- Dark TG-inspired desktop dashboard with compact sidebar navigation.
- Live Status, Rank, Session, Smart Dodge, Performance, and Activity cards.
- Master V progress visualization.
- Compact performance telemetry for matches/hour, points/hour, Vision FPS, frame age, dodges, time saved, Owl score, and reaction time.
- Dark History and Diagnostics panels.
- Top-right update indicator with an update-available badge.
- Existing Wireless ADB, Fast Vision, OCR, Smart Dodge, persistent tap shell, and updater behavior retained.

## Automated releases

`VERSION` is the release version source. The GitHub Actions release workflow builds the update ZIP from `release_payload/v5_5_parts/` and publishes or refreshes the matching GitHub Release automatically.

The installed Companion then detects the latest published Release and installs it from inside the app, so normal users do not need to manually download or replace program folders.

User calibration, Owl samples, Smart Dodge settings, session history, logs, and update settings live in `%APPDATA%\\TG-BTC-Arena-Companion` and are preserved across updates.
