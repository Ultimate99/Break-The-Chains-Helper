# TG:BTC Game Assistant 7.1.0 — Daily Assistant V1

V7.1 turns the V7 Daily test harness into a usable modular daily collector.

## New
- **RUN ALL SAFE** chains the supported daily modules in a conservative order.
- **Screen verification** before route chaining: Home, Mail, Shop, Recruit, Event, Quest Pass, Chain Campaign, and Idle Farming popup.
- **Verified Home return** uses the game's visible Home icon. Daily Assistant still never sends Android Back.
- **Mail** — CLAIM / CLAIM ALL inbox rewards.
- **Shop** — opens Daily Deal and inspects known Shop tabs; content clicks remain limited to explicit FREE / CLAIM actions.
- **Recruit** — enters Regular Recruit and only uses an explicit FREE pull. Recruit runs last in RUN ALL so summon/result flow is never guessed through.
- **Quest Pass** — checks Pass Quest, Daily, Weekly, and Pass Reward pages for claimable rewards.
- **Events** — collects visible CLAIM / FREE actions from the Event screen.
- **Idle Rewards** — opens Chain Campaign Idle Farming and claims it. Includes a visual-popup fallback because TG:BTC's stylized Idle Claim label is unreliable in OCR.
- **Login / Sign-in** — separate teachable module for rotating seasonal sign-in pages.
- **Run summary + audit log** — records claim actions, free actions, skipped modules, issues, elapsed time, and writes `%APPDATA%\TG-BTC-Arena-Companion\daily_runs.jsonl`.

## Safety
- Content targets remain restricted to literal `CLAIM`, `CLAIM ALL`, and `FREE`.
- Known navigation/tab taps only continue after the expected screen is verified.
- `BUY`, `EXCHANGE`, `USE`, `SWEEP`, `START`, `GO NOW`, premium-currency purchases, and ticket-cost actions are not content targets.
- If a route or Home return cannot be verified, RUN ALL SAFE stops instead of guessing.

## Updater
- V7.1 returns to a **self-contained full-source update payload**. It no longer depends on finding an exact previous-version backup before installing.

Existing Arena, Smart Dodge, Opponent Intelligence, Strategy, History, Diagnostics, updater profile, and V7.0.7 Daily debug screenshots are preserved.
