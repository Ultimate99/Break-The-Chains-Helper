# TG:BTC Game Assistant 7.0.0 — Modular Daily Assistant

V7.0 begins the transition from Arena-only automation to a full-game assistant.

## Daily Assistant
- New first-class **Daily Assistant** page.
- Separate modules: **Mail, Events, Shop, Recruit, Quest Pass, Idle Rewards, Current Screen**.
- Each module has its own **START** button instead of one giant routine.
- Routes can be re-taught with **TEACH** if the game UI changes.

## Safe Collector Engine
- OCR-driven actions for literal **CLAIM ALL**, **CLAIM**, and **FREE** labels only.
- Module-specific allowlists: Recruit uses FREE only; Mail/Quest Pass use claims only.
- Rejects large marketing-title text such as FREE in a banner/title.
- Automatically dismisses **Rewards Obtained** overlays.
- Every automatic tap is written to the existing Activity log.

## Spending Guardrails
The Daily Assistant never blind-clicks BUY, EXCHANGE, USE, SWEEP, START, GO NOW, premium currency, tickets, or other cost-bearing actions. Unknown/unfinished actions are left for later gameplay modules.

## Recorded Tap Routes
The included default Home routes for Mail, Events, Shop, Recruit and Quest Pass are normalized from the user's recorded tap flows. Idle Rewards intentionally starts as **NEEDS ROUTE** until a clean route is taught.

## Compatibility
Existing Arena automation, Fast Vision, OCR, Smart Dodge, Opponent Intelligence, Strategy Engine, History, self-healing, custom dark chrome, AppData profile, and updater are preserved.
