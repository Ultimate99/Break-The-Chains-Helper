#!/usr/bin/env python3
"""Synthetic algorithm/persistence tests for the generated TG:BTC v7.3.0 source."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np


def load_generated(path: str):
    spec = importlib.util.spec_from_file_location("tgbtc_v73_tested", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load generated module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_bar(fill: float):
    img = np.zeros((24, 200, 3), dtype=np.uint8)
    img[:] = (12, 12, 12)
    px = max(0, min(200, int(round(200 * float(fill)))))
    if px:
        img[:, :px] = (0, 220, 40)
    return img


def run(source_path: str):
    mod = load_generated(source_path)
    results = {}

    # HP bar estimator: full / half / critical synthetic bars.
    r100 = mod._arena_bar_fill_ratio(synthetic_bar(1.0), (0, 0, 200, 24))
    r50 = mod._arena_bar_fill_ratio(synthetic_bar(0.5), (0, 0, 200, 24))
    r10 = mod._arena_bar_fill_ratio(synthetic_bar(0.1), (0, 0, 200, 24))
    results["hp_readings"] = [r100, r50, r10]
    assert r100 is not None and 0.90 <= r100 <= 1.0, r100
    assert r50 is not None and 0.42 <= r50 <= 0.60, r50
    assert r10 is not None and 0.05 <= r10 <= 0.18, r10

    # HP collapse is only an accelerator for an already-learned loss and needs
    # all six calibrated bars.
    original_hp = mod._arena_hp_snapshot
    try:
        mod._arena_hp_snapshot = lambda _ref: {
            "ally": [0.03, 0.05, 0.02],
            "enemy": [0.80, 0.70, 0.65],
            "ally_avg": 0.033,
            "enemy_avg": 0.716,
            "ally_alive": 0,
            "enemy_alive": 3,
        }
        assert mod._arena_catastrophic_state(None, 0.87)[0] is False
        assert mod._arena_catastrophic_state(None, 0.90)[0] is True
        mod._arena_hp_snapshot = lambda _ref: {
            "ally": [0.03, 0.05],
            "enemy": [0.80, 0.70, 0.65],
            "ally_avg": 0.04,
            "enemy_avg": 0.716,
            "ally_alive": 0,
            "enemy_alive": 3,
        }
        assert mod._arena_catastrophic_state(None, 0.99)[0] is False
    finally:
        mod._arena_hp_snapshot = original_hp
    results["catastrophic_guard"] = True

    # Learned loss probability should separate clear synthetic win/loss vectors.
    state = mod._arena_learning_default()
    state["settings"]["min_class_matches"] = 3
    state["buckets"]["0"] = {
        "WIN": {"matches": 4, "samples": 20, "centroid": [0.0, 0.0, 0.0]},
        "LOSS": {"matches": 4, "samples": 20, "centroid": [1.0, 1.0, 1.0]},
    }
    mod.arena_learning_state = state
    p_loss, detail_loss = mod.arena_predict_loss([0.9, 0.9, 0.9], 1.0, 0)
    p_win, detail_win = mod.arena_predict_loss([0.1, 0.1, 0.1], 1.0, 0)
    results["loss_probs"] = [p_loss, p_win]
    assert p_loss is not None and p_win is not None
    assert p_loss > 0.65, (p_loss, detail_loss)
    assert p_win < 0.35, (p_win, detail_win)

    # Pilot warm-up: 12 matches + 4W/4L + >=2 calibrated actions.
    mod.strategy_settings = lambda: {
        "action_points": {"Skill A": [100, 100], "Skill B": [200, 200]}
    }
    engine = mod.ArenaBotEngine()
    mod.arena_learning_state = mod._arena_learning_default()
    mod.arena_learning_state["stats"].update(
        {"trained_matches": 11, "wins": 5, "losses": 6}
    )
    ready, why = engine._pilot_ready()
    assert ready is False, why
    mod.arena_learning_state["stats"].update(
        {"trained_matches": 12, "wins": 4, "losses": 4}
    )
    ready, why = engine._pilot_ready()
    assert ready is True, why
    choice = engine._pilot_choose_action(
        "0|LOW|BOT|none", ["Skill A", "Skill B"]
    )
    assert choice in {"Skill A", "Skill B"}
    results["pilot_gate"] = why

    # Calibrated action filter must reject malformed/out-of-reference taps.
    mod.strategy_settings = lambda: {
        "action_points": {
            "Good": [100, 100],
            "Bad negative": [-1, 20],
            "Bad far": [99999, 20],
            "Bad shape": [10],
        }
    }
    valid_points = mod._arena_pilot_valid_points()
    assert valid_points == {"Good": [100.0, 100.0]}, valid_points
    results["pilot_coordinate_filter"] = valid_points

    # Event clustering: same signature -> same cluster, far signature -> new.
    # Outcome is counted once per cluster per battle and labels remain unknown.
    temp = Path(tempfile.mkdtemp(prefix="v73-events-"))
    mod.ARENA_EVENT_DIR = temp / "events"
    mod.ARENA_EVENT_DIR.mkdir(parents=True, exist_ok=True)
    mod.ARENA_LEARNING_FILE = temp / "model.json"
    mod.arena_learning_state = mod._arena_learning_default()
    mod.opponent_move_roi = lambda: (0, 0, 200, 100)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    c1, new1, _ = mod.arena_record_enemy_event(
        frame, 0x0000000000000000, 4.0, ["Hero A"]
    )
    c1b, new1b, _ = mod.arena_record_enemy_event(
        frame, 0x0000000000000000, 5.0, ["Hero A"]
    )
    c2, new2, _ = mod.arena_record_enemy_event(
        frame, 0xFFFFFFFFFFFFFFFF, 6.0, ["Hero B"]
    )
    assert c1 == "EVT-0001" and new1 is True
    assert c1b == c1 and new1b is False
    assert c2 == "EVT-0002" and new2 is True
    trace = {
        "events": [
            {"kind": "enemy_event", "cluster": c1},
            {"kind": "enemy_event", "cluster": c1},
            {"kind": "enemy_event", "cluster": c2},
        ]
    }
    mod.arena_apply_event_outcome(trace, "WIN")
    clusters = mod.arena_learning_state["event_clusters"]
    assert clusters[c1]["matches"] == 1 and clusters[c1]["wins"] == 1
    assert clusters[c2]["matches"] == 1 and clusters[c2]["wins"] == 1
    assert clusters[c1]["label"] is None and clusters[c2]["label"] is None
    results["event_clusters"] = [c1, c2]

    # DCT event signatures are deterministic for an unchanged frame.
    sig1 = mod._arena_event_signature(frame)
    sig2 = mod._arena_event_signature(frame.copy())
    assert sig1 is not None and sig1 == sig2
    assert mod._arena_event_hamming(sig1, sig2) == 0
    results["event_signature"] = f"{sig1:016x}"

    # Power parser handles separators and rejects implausibly short text.
    assert mod.extract_power_value("Power 123,456") == 123456
    assert mod.extract_power_value("CP: 98 765") == 98765
    assert mod.extract_power_value("12") is None
    assert mod.extract_power_value("nothing") is None
    results["power_parser"] = True

    # Adaptive Daily fingerprint persists, deduplicates, and is reused.
    adapt = temp / "vision_adaptive.json"
    mod.VISION_ADAPTIVE_FILE = adapt
    app = mod.App.__new__(mod.App)
    app._vision_adaptive_cache = None
    app.add_log = lambda _text: None
    rng = np.random.default_rng(73)
    live = rng.integers(
        0,
        256,
        size=(mod.REFERENCE_H, mod.REFERENCE_W, 3),
        dtype=np.uint8,
    )
    learned = app._vision_learn_screen("MAIL", live, evidence="TEST")
    duplicate = app._vision_learn_screen("MAIL", live.copy(), evidence="TEST")
    assert learned is True and duplicate is False
    assert adapt.exists()
    saved = json.loads(adapt.read_text(encoding="utf-8"))
    assert len(saved["screens"]["MAIL"]) == 1
    screen, conf, detail = app._vision_identify_screen(live)
    assert screen == "MAIL" and conf >= 99.0, (screen, conf, detail)
    results["daily_adaptive"] = [screen, conf, detail]

    # Only supported screen names may enter the adaptive visual database.
    assert app._vision_learn_screen("HOME", live, evidence="TEST") is False
    assert app._vision_learn_screen("IDLE_POPUP", live, evidence="TEST") is False
    results["daily_adaptive_scope"] = True

    return results


def main():
    source = os.environ.get("V73_SOURCE", "/tmp/v73.py")
    receipt = Path(
        os.environ.get(
            "V73_ALGORITHM_RECEIPT",
            "release_payload/V73_ALGORITHM_TESTS.json",
        )
    )
    results = run(source)
    payload = {
        "version": "7.3.0-dev-algorithms",
        "passed": True,
        "results": results,
    }
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
