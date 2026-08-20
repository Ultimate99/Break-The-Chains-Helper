# Break The Chains Helper

TG:BTC Arena Companion for automating Real-Time Arena navigation, Fast Vision, OCR rank/points tracking, and optional Smart Dodge rules.

## Update source

The desktop app uses this repository as its built-in update source.

Current configured source:

`Ultimate99/Break-The-Chains-Helper`

## Publishing an update

1. Build the new Companion ZIP.
2. Create a GitHub Release tagged with the app version, for example `v5.3.1`.
3. Attach the Companion `.zip` file to the Release.
4. The installed app can then detect it through **CHECK UPDATE** and install it while preserving the permanent profile in `%APPDATA%\TG-BTC-Arena-Companion`.

User settings, Owl samples, Smart Dodge calibration, logs, and session history are intentionally stored outside the version folder.
