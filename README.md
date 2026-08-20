# TG:BTC Game Assistant

Current release: 7.0.6

The project has evolved from an Arena Companion into a broader TG:BTC Game Assistant with Arena automation, opponent intelligence, diagnostics/self-healing, strategy tooling, and modular Daily Assistant collectors.

## Daily Assistant safety
- Start each module from the game Home screen.
- Only explicit `CLAIM`, `CLAIM ALL`, and `FREE` actions are automated by safe collectors.
- Daily Assistant never presses Android Back automatically.
- Spending actions such as BUY, EXCHANGE, USE, SWEEP, START, GO NOW, premium currency, and ticket costs are not blindly clicked.

See `RELEASE_NOTES.md` for the latest changes.
