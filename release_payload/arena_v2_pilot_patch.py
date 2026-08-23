#!/usr/bin/env python3
"""Readable V7.3 Arena V2 Pilot build-time source patch."""


def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} expected one match, found {count}")
    return text.replace(old, new, 1)


def apply_arena_v2_pilot_patch(text):
    old = '''            "max_trace_matches": 250,
        },
        "stats": {
            "trained_matches": 0,
            "wins": 0,
            "losses": 0,
            "dodges": 0,
        },
        "buckets": {},
    }
'''
    new = '''            "max_trace_matches": 250,
            "pilot_enabled": True,
            "pilot_min_trained_matches": 12,
            "pilot_min_wins": 4,
            "pilot_min_losses": 4,
            "pilot_min_actions": 2,
            "pilot_action_interval_s": 0.90,
            "pilot_eval_delay_s": 0.55,
            "pilot_max_actions_per_match": 50,
            "pilot_explore_every": 5,
            "pilot_no_effect_fallback": 3,
        },
        "stats": {
            "trained_matches": 0,
            "wins": 0,
            "losses": 0,
            "dodges": 0,
        },
        "buckets": {},
        "pilot_actions": {
            "global": {},
            "contexts": {},
        },
    }
'''
    text = _replace_once(text, old, new, "Pilot learning defaults")

    old = '''                if isinstance(saved.get("buckets"), dict):
                    base["buckets"] = saved["buckets"]
    except Exception:
'''
    new = '''                if isinstance(saved.get("buckets"), dict):
                    base["buckets"] = saved["buckets"]
                if isinstance(saved.get("pilot_actions"), dict):
                    base["pilot_actions"] = saved["pilot_actions"]
    except Exception:
'''
    text = _replace_once(text, old, new, "Pilot state load")

    old = '''def arena_adaptive_quit_ready():
    settings = (get_arena_learning_state().get("settings") or {})
'''
    new = '''def _arena_pilot_context(elapsed_s, loss_probability=None, identity=None, heroes=None):
    phase = _arena_time_bucket(elapsed_s)
    if loss_probability is None:
        danger = "UNK"
    elif float(loss_probability) >= 0.80:
        danger = "CRIT"
    elif float(loss_probability) >= 0.60:
        danger = "HIGH"
    elif float(loss_probability) >= 0.40:
        danger = "MID"
    else:
        danger = "LOW"
    ident = str(identity or "UNK").upper()
    hero_key = "+".join(sorted(str(x).strip().lower() for x in (heroes or []) if str(x).strip())[:3]) or "none"
    return f"{phase}|{danger}|{ident}|{hero_key}"


def _arena_pilot_valid_points():
    strat = strategy_settings()
    out = {}
    for name, point in (strat.get("action_points") or {}).items():
        try:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x = float(point[0]); y = float(point[1])
            if not (0.0 <= x <= float(REFERENCE_W) and 0.0 <= y <= float(REFERENCE_H)):
                continue
            clean = str(name or "").strip()
            if not clean:
                continue
            out[clean] = [x, y]
        except Exception:
            continue
    return out


def _arena_pilot_node(store, action):
    return store.setdefault(str(action), {
        "tries": 0,
        "reward_sum": 0.0,
        "outcome_sum": 0.0,
        "wins": 0,
        "losses": 0,
        "no_effect": 0,
        "last_used": None,
    })


def _arena_pilot_score(node):
    tries = max(0, int(node.get("tries") or 0))
    if tries <= 0:
        return 0.20
    reward = float(node.get("reward_sum") or 0.0) / float(tries)
    outcome = float(node.get("outcome_sum") or 0.0) / float(tries)
    uncertainty = 0.12 / float((tries + 1) ** 0.5)
    no_effect = min(0.20, 0.02 * float(node.get("no_effect") or 0))
    return reward + outcome + uncertainty - no_effect


def _arena_pilot_update(action, context, reward=0.0, outcome=None, no_effect=False):
    action = str(action or "").strip()
    if not action:
        return
    with ARENA_LEARNING_LOCK:
        model = arena_learning_state.setdefault("pilot_actions", {})
        global_store = model.setdefault("global", {})
        context_store = model.setdefault("contexts", {}).setdefault(str(context or "UNK"), {})
        for store in (global_store, context_store):
            node = _arena_pilot_node(store, action)
            node["reward_sum"] = round(float(node.get("reward_sum") or 0.0) + float(reward or 0.0), 6)
            if no_effect:
                node["no_effect"] = int(node.get("no_effect") or 0) + 1
            if outcome == "WIN":
                node["wins"] = int(node.get("wins") or 0) + 1
                node["outcome_sum"] = round(float(node.get("outcome_sum") or 0.0) + 0.18, 6)
            elif outcome == "LOSS":
                node["losses"] = int(node.get("losses") or 0) + 1
                node["outcome_sum"] = round(float(node.get("outcome_sum") or 0.0) - 0.18, 6)


def arena_adaptive_quit_ready():
    settings = (get_arena_learning_state().get("settings") or {})
'''
    text = _replace_once(text, old, new, "Pilot model helpers")

    old = '''        self._learning_quit_hits = 0
        self._learning_last_report = None

        # V5.8 health telemetry / watchdog.
'''
    new = '''        self._learning_quit_hits = 0
        self._learning_last_report = None

        # V7.3 Arena V2 Pilot state. Pilot only owns a match after its
        # warm-up and calibrated-action gates pass.
        self._pilot_pending = None
        self._pilot_actions_this_match = []
        self._pilot_last_action_at = 0.0
        self._pilot_last_action = None
        self._pilot_no_effect_streak = 0
        self._pilot_disabled_for_match = False
        self._pilot_auto_toggle_at = 0.0
        self._pilot_action_count = 0

        # V5.8 health telemetry / watchdog.
'''
    text = _replace_once(text, old, new, "Pilot engine init")

    old = '''            "strategy": ("OFF", "Battle script engine disabled"),
            "learning": ("LEARNING", "Arena V2 battle model warming up"),
        }
'''
    new = '''            "strategy": ("OFF", "Battle script engine disabled"),
            "learning": ("LEARNING", "Arena V2 battle model warming up"),
            "pilot": ("LEARNING", "Waiting for learned battles + calibrated actions"),
        }
'''
    text = _replace_once(text, old, new, "Pilot health default")

    old = '''                self._validate_dodge_health()
                self._validate_intelligence_health()

                # Persistent shell health is cheap to inspect locally.
'''
    new = '''                self._validate_dodge_health()
                self._validate_intelligence_health()
                self._validate_pilot_health()

                # Persistent shell health is cheap to inspect locally.
'''
    text = _replace_once(text, old, new, "Pilot watchdog hook")

    old = '''    def _recover_tap_shell(self, reason="tap shell stopped"):
'''
    new = '''    def _validate_pilot_health(self):
        state = get_arena_learning_state()
        settings = state.get("settings") or {}
        stats = state.get("stats") or {}
        points = _arena_pilot_valid_points()
        if not settings.get("pilot_enabled", True):
            self._health_set("pilot", "OFF", "Pilot disabled")
            return
        need_matches = max(1, int(settings.get("pilot_min_trained_matches") or 12))
        need_wins = max(1, int(settings.get("pilot_min_wins") or 4))
        need_losses = max(1, int(settings.get("pilot_min_losses") or 4))
        need_actions = max(1, int(settings.get("pilot_min_actions") or 2))
        trained = int(stats.get("trained_matches") or 0)
        wins = int(stats.get("wins") or 0)
        losses = int(stats.get("losses") or 0)
        if len(points) < need_actions:
            self._health_set("pilot", "NOT READY", f"Calibrate {need_actions} actions • have {len(points)}")
            return
        if trained < need_matches or wins < need_wins or losses < need_losses:
            self._health_set(
                "pilot", "LEARNING",
                f"Shadow training {trained}/{need_matches} • {wins}W/{losses}L • need {need_wins}W/{need_losses}L"
            )
            return
        if self._pilot_disabled_for_match:
            self._health_set("pilot", "DEGRADED", "Fallback to AUTO for current match")
            return
        self._health_set("pilot", "READY", f"{len(points)} calibrated actions • learned {trained} matches")

    def _recover_tap_shell(self, reason="tap shell stopped"):
'''
    text = _replace_once(text, old, new, "Pilot health method")

    old = '''    # --------------------------
    # BACKGROUND OCR
    # --------------------------
'''
    new = '''    # --------------------------
    # V7.3 ARENA V2 — PILOT CONTROLLER
    # --------------------------
    def _pilot_reset(self):
        self._pilot_pending = None
        self._pilot_actions_this_match = []
        self._pilot_last_action_at = 0.0
        self._pilot_last_action = None
        self._pilot_no_effect_streak = 0
        self._pilot_disabled_for_match = False
        self._pilot_auto_toggle_at = 0.0
        self._pilot_action_count = 0
        with session_lock:
            session["current_pilot_status"] = "SHADOW / AUTO"
            session["current_pilot_action"] = None

    def _pilot_ready(self):
        if self._pilot_disabled_for_match:
            return False, "fallback locked for this match"
        state = get_arena_learning_state()
        settings = state.get("settings") or {}
        stats = state.get("stats") or {}
        if not settings.get("pilot_enabled", True):
            return False, "disabled"
        points = _arena_pilot_valid_points()
        need_actions = max(1, int(settings.get("pilot_min_actions") or 2))
        if len(points) < need_actions:
            return False, f"need {need_actions} calibrated actions"
        need_matches = max(1, int(settings.get("pilot_min_trained_matches") or 12))
        need_wins = max(1, int(settings.get("pilot_min_wins") or 4))
        need_losses = max(1, int(settings.get("pilot_min_losses") or 4))
        trained = int(stats.get("trained_matches") or 0)
        wins = int(stats.get("wins") or 0)
        losses = int(stats.get("losses") or 0)
        if trained < need_matches or wins < need_wins or losses < need_losses:
            return False, f"shadow {trained}/{need_matches} • {wins}W/{losses}L"
        return True, f"ready • {trained} learned matches • {len(points)} actions"

    def _pilot_choose_action(self, context, action_names):
        names = [str(x) for x in action_names if str(x)]
        if not names:
            return None
        state = get_arena_learning_state()
        model = state.get("pilot_actions") or {}
        global_store = model.get("global") or {}
        context_store = (model.get("contexts") or {}).get(str(context or "UNK")) or {}
        explore_every = max(2, int((state.get("settings") or {}).get("pilot_explore_every") or 5))
        if (self._pilot_action_count + 1) % explore_every == 0:
            ranked = []
            for name in names:
                local = context_store.get(name) or {}
                global_node = global_store.get(name) or {}
                tries = int(local.get("tries") or 0) + int(global_node.get("tries") or 0)
                ranked.append((tries, name == self._pilot_last_action, name))
            ranked.sort(key=lambda row: (row[0], row[1], row[2].lower()))
            return ranked[0][2]
        ranked = []
        for name in names:
            local = context_store.get(name) or {}
            global_node = global_store.get(name) or {}
            local_score = _arena_pilot_score(local) if local else 0.0
            global_score = _arena_pilot_score(global_node) if global_node else 0.0
            score = local_score * 0.72 + global_score * 0.28
            if name == self._pilot_last_action and len(names) > 1:
                score -= 0.08
            ranked.append((score, name))
        ranked.sort(key=lambda row: (-row[0], row[1].lower()))
        return ranked[0][1]

    def _pilot_update_pending(self, ref_screen, loss_probability):
        pending = self._pilot_pending
        if not isinstance(pending, dict):
            return
        age = time.monotonic() - float(pending.get("at") or 0.0)
        state = get_arena_learning_state()
        settings = state.get("settings") or {}
        eval_delay = max(0.35, float(settings.get("pilot_eval_delay_s") or 0.55))
        if age < eval_delay:
            return
        before_p = pending.get("loss_p")
        now_sig = _arena_frame_signature(ref_screen)
        before_sig = pending.get("signature")
        distance = _arena_signature_distance(before_sig, now_sig)
        visual_changed = distance >= 5
        reward = 0.0
        if before_p is not None and loss_probability is not None:
            reward += max(-0.20, min(0.20, float(before_p) - float(loss_probability)))
        reward += 0.025 if visual_changed else -0.035
        no_effect = not visual_changed
        _arena_pilot_update(
            pending.get("action"),
            pending.get("context"),
            reward=reward,
            no_effect=no_effect,
        )
        save_arena_learning_state()
        if no_effect:
            self._pilot_no_effect_streak += 1
        else:
            self._pilot_no_effect_streak = 0
        limit = max(2, int(settings.get("pilot_no_effect_fallback") or 3))
        if self._pilot_no_effect_streak >= limit:
            self._pilot_disabled_for_match = True
            self.emit_log(
                f"ARENA PILOT: {self._pilot_no_effect_streak} no-effect actions — fallback AUTO for this match"
            )
            with session_lock:
                session["current_pilot_status"] = "FALLBACK AUTO"
            self._health_set("pilot", "DEGRADED", "No-effect fail-safe -> AUTO")
        self._pilot_pending = None

    def _pilot_step(self, ref_screen, loss_probability, auto_state, auto_x, auto_y, actual_w, actual_h):
        ready, reason = self._pilot_ready()
        if not ready:
            with session_lock:
                session["current_pilot_status"] = "SHADOW / AUTO • " + reason
            return False
        if auto_state == "ON":
            now_mono = time.monotonic()
            if auto_x is not None and auto_y is not None and now_mono - self._pilot_auto_toggle_at >= 0.80:
                self._tap_reference(float(auto_x), float(auto_y), actual_w, actual_h)
                self._pilot_auto_toggle_at = now_mono
                self._learning_note_action("DISABLE_AUTO", "pilot")
                self.emit_log("ARENA PILOT: disabled game AUTO — Pilot taking control")
            with session_lock:
                session["auto"] = "PILOT"
                session["current_battle_strategy"] = "PILOT"
                session["current_pilot_status"] = "TAKING CONTROL"
            return True
        if auto_state != "OFF":
            return True
        self._pilot_update_pending(ref_screen, loss_probability)
        if self._pilot_disabled_for_match:
            return False
        state = get_arena_learning_state()
        settings = state.get("settings") or {}
        interval = max(0.45, float(settings.get("pilot_action_interval_s") or 0.90))
        now_mono = time.monotonic()
        if self._pilot_pending is not None or now_mono - self._pilot_last_action_at < interval:
            with session_lock:
                session["auto"] = "PILOT"
                session["current_battle_strategy"] = "PILOT"
                session["current_pilot_status"] = "PILOT OBSERVING"
            return True
        max_actions = max(5, int(settings.get("pilot_max_actions_per_match") or 50))
        if self._pilot_action_count >= max_actions:
            self._pilot_disabled_for_match = True
            self.emit_log("ARENA PILOT: action safety cap reached — fallback AUTO")
            return False
        points = _arena_pilot_valid_points()
        if not points:
            self._pilot_disabled_for_match = True
            return False
        with session_lock:
            identity = session.get("current_opponent_type")
            heroes = list(session.get("current_detected_heroes") or [])
        elapsed = max(0.0, now_mono - self.match_started_at) if self.match_started_at else 0.0
        context = _arena_pilot_context(elapsed, loss_probability, identity, heroes)
        action = self._pilot_choose_action(context, list(points.keys()))
        point = points.get(action)
        if not action or not point:
            self._pilot_disabled_for_match = True
            return False
        with ARENA_LEARNING_LOCK:
            model = arena_learning_state.setdefault("pilot_actions", {})
            for store in (
                model.setdefault("global", {}),
                model.setdefault("contexts", {}).setdefault(context, {}),
            ):
                node = _arena_pilot_node(store, action)
                node["tries"] = int(node.get("tries") or 0) + 1
                node["last_used"] = datetime.now().isoformat(timespec="seconds")
        signature = _arena_frame_signature(ref_screen)
        try:
            self._tap_reference(float(point[0]), float(point[1]), actual_w, actual_h)
        except Exception as exc:
            _arena_pilot_update(action, context, reward=-0.10, no_effect=True)
            save_arena_learning_state()
            self.emit_log(f"ARENA PILOT: action {action!r} tap failed: {exc}")
            self._pilot_no_effect_streak += 1
            return True
        self._pilot_action_count += 1
        self._pilot_last_action_at = now_mono
        self._pilot_last_action = action
        self._pilot_actions_this_match.append({"action": action, "context": context})
        self._pilot_pending = {
            "action": action,
            "context": context,
            "at": now_mono,
            "loss_p": float(loss_probability) if loss_probability is not None else None,
            "signature": signature,
        }
        self._learning_note_action(action, "pilot")
        with session_lock:
            session["auto"] = "PILOT"
            session["last_action"] = f"PILOT:{action}"
            session["current_battle_strategy"] = "PILOT"
            session["current_pilot_action"] = action
            session["current_pilot_status"] = f"PILOT • {context}"
        if loss_probability is not None:
            self.emit_log(f"ARENA PILOT: {action} • {context} • loss={loss_probability * 100.0:.0f}%")
        else:
            self.emit_log(f"ARENA PILOT: {action} • {context} • loss=learning")
        return True

    def _pilot_finish(self, result):
        result = str(result or "").upper()
        actions = list(self._pilot_actions_this_match or [])
        if actions and result in ("WIN", "LOSS"):
            credit = (0.22 if result == "WIN" else -0.22) / float(max(1.0, len(actions) ** 0.5))
            for row in actions:
                _arena_pilot_update(
                    row.get("action"),
                    row.get("context"),
                    reward=credit,
                    outcome=result,
                )
            save_arena_learning_state()
            self.emit_log(f"ARENA PILOT: learned {result} from {len(actions)} action(s)")
        self._pilot_pending = None
        self._pilot_actions_this_match = []
        self._pilot_no_effect_streak = 0
        self._pilot_action_count = 0

    # --------------------------
    # BACKGROUND OCR
    # --------------------------
'''
    text = _replace_once(text, old, new, "Pilot methods insertion")

    old = '''                    if not result_screen_counted:
                        # Finalize the Arena V2 trace before register_result clears
                        # the live opponent fields used by the learner.
                        self._learning_finish(
'''
    new = '''                    if not result_screen_counted:
                        self._pilot_finish(
                            "DODGE" if was_dodge else ("WIN" if is_win else "LOSS")
                        )
                        # Finalize the Arena V2 trace before register_result clears
                        # the live opponent fields used by the learner.
                        self._learning_finish(
'''
    text = _replace_once(text, old, new, "Pilot result hook")

    old = '''                if start:
                    self.dodge_in_progress = False
                    dodge_checked = False
'''
    new = '''                if start:
                    self.dodge_in_progress = False
                    self._pilot_reset()
                    dodge_checked = False
'''
    text = _replace_once(text, old, new, "Pilot queue reset")

    old = '''                    if self.dodge_in_progress:
                        # Let the quit/result UI take over; never enable AUTO.
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    self._run_strategy_steps(now, actual_w, actual_h)
                    strategy_cfg = strategy_settings()
'''
    new = '''                    if self.dodge_in_progress:
                        # Let the quit/result UI take over; never enable AUTO.
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    with session_lock:
                        current_loss_pct = session.get("current_loss_probability")
                    current_loss_p = (
                        float(current_loss_pct) / 100.0
                        if current_loss_pct is not None else None
                    )
                    if self._pilot_step(
                        ref, current_loss_p, auto_state, x, y, actual_w, actual_h
                    ):
                        self.last_loop_ms = int((time.perf_counter() - loop_started) * 1000)
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    self._run_strategy_steps(now, actual_w, actual_h)
                    strategy_cfg = strategy_settings()
'''
    text = _replace_once(text, old, new, "Pilot battle hook")

    marker = "\n# V7.3 Arena V2 Pilot — calibrated-action reinforcement controller build marker\n"
    if marker.strip() not in text:
        text += marker
    return text
