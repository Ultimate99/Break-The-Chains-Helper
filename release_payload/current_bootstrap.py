# TG:BTC Game Assistant v7.0.1 Daily Assistant UI hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.1"
OLD_VERSION = 'APP_VERSION = "7.0.0"'
NEW_VERSION = 'APP_VERSION = "7.0.1"'

OLD_SAFE = '''        safe = self._make_card(page)\n        safe.pack(fill="x", padx=26, pady=(0, 12))\n        safe_inner = tk.Frame(safe, bg=UI_CARD)\n        safe_inner.pack(fill="x", padx=16, pady=14)\n'''
NEW_SAFE = '''        safe, safe_inner = self._make_card(page, padx=16, pady=14)\n        safe.pack(fill="x", padx=26, pady=(0, 12))\n'''

OLD_CARD = '''            card=self._make_card(body)\n            card.grid(row=i//2, column=i%2, sticky="nsew", padx=(0,7) if i%2==0 else (7,0), pady=7)\n            top=tk.Frame(card,bg=UI_CARD); top.pack(fill="x", padx=14, pady=(12,5))\n            self._label(top,name,bg=UI_CARD,size=11,weight="bold").pack(side="left")\n            self._label(top,textvariable=self._daily_var(name,"READY" if name!="Idle Rewards" else "NEEDS ROUTE"),bg=UI_CARD,fg=UI_GREEN if name!="Idle Rewards" else UI_AMBER,size=8,weight="bold").pack(side="right")\n            self._label(card,desc,bg=UI_CARD,fg=UI_MUTED,size=8).pack(anchor="w",padx=14)\n            self._label(card,rule,bg=UI_CARD,fg=UI_MUTED2,size=8).pack(anchor="w",padx=14,pady=(2,8))\n            actions=tk.Frame(card,bg=UI_CARD); actions.pack(fill="x",padx=14,pady=(0,12))\n'''
NEW_CARD = '''            card, card_body = self._make_card(body, padx=14, pady=12)\n            card.grid(row=i//2, column=i%2, sticky="nsew", padx=(0,7) if i%2==0 else (7,0), pady=7)\n            top=tk.Frame(card_body,bg=UI_CARD); top.pack(fill="x", pady=(0,5))\n            self._label(top,name,bg=UI_CARD,size=11,weight="bold").pack(side="left")\n            self._label(top,textvariable=self._daily_var(name,"READY" if name!="Idle Rewards" else "NEEDS ROUTE"),bg=UI_CARD,fg=UI_GREEN if name!="Idle Rewards" else UI_AMBER,size=8,weight="bold").pack(side="right")\n            self._label(card_body,desc,bg=UI_CARD,fg=UI_MUTED,size=8).pack(anchor="w")\n            self._label(card_body,rule,bg=UI_CARD,fg=UI_MUTED_2,size=8).pack(anchor="w",pady=(2,8))\n            actions=tk.Frame(card_body,bg=UI_CARD); actions.pack(fill="x")\n'''

def find_base(target):
    appdata = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates = []
    if appdata.exists():
        for p in appdata.glob("before_7.0.0_*/tg_arena_bot.py"):
            candidates.append(p)
        for p in appdata.glob("**/tg_arena_bot.py"):
            if p not in candidates:
                candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s = p.read_text(encoding="utf-8")
            if OLD_VERSION in s and "def open_daily_assistant" in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate the backed-up v7.0.0 source. Use the 7.0.1 standalone package instead.")


def main():
    target = Path(__file__).resolve()
    s = find_base(target)
    if OLD_SAFE not in s or OLD_CARD not in s:
        raise RuntimeError("v7.0.1 patch markers not found in the v7.0.0 source")
    s = s.replace(OLD_VERSION, NEW_VERSION, 1)
    s = s.replace(OLD_SAFE, NEW_SAFE, 1)
    s = s.replace(OLD_CARD, NEW_CARD, 1)
    s = s.replace("UI_MUTED2", "UI_MUTED_2")
    tmp = target.with_suffix(target.suffix + ".v701.tmp")
    tmp.write_text(s, encoding="utf-8")
    os.replace(tmp, target)
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent), creationflags=flags)

if __name__ == "__main__":
    main()
