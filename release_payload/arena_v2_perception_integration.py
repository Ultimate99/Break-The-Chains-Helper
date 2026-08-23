#!/usr/bin/env python3
"""V7.3 Arena structured-perception integration patch."""


def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} expected one match, found {count}")
    return text.replace(old, new, 1)


def apply_arena_perception_integration_patch(text):
    old = '''        "current_opponent_username": None,\n        "current_identity_confidence": None,\n        "current_detected_heroes": [],\n'''
    new = '''        "current_opponent_username": None,\n        "current_identity_confidence": None,\n        "current_opponent_power": None,\n        "current_opponent_power_confidence": None,\n        "current_detected_heroes": [],\n'''
    text = _replace_once(text, old, new, "perception new-session fields")

    old = '''                base["current_opponent_username"] = None\n                base["current_identity_confidence"] = None\n                base["current_detected_heroes"] = []\n'''
    new = '''                base["current_opponent_username"] = None\n                base["current_identity_confidence"] = None\n                base["current_opponent_power"] = None\n                base["current_opponent_power_confidence"] = None\n                base["current_detected_heroes"] = []\n'''
    text = _replace_once(text, old, new, "perception persistent reset")

    old = '''    opponent_username = session.get("current_opponent_username")\n    identity_confidence = session.get("current_identity_confidence")\n    detected_heroes = list(session.get("current_detected_heroes") or [])\n'''
    new = '''    opponent_username = session.get("current_opponent_username")\n    identity_confidence = session.get("current_identity_confidence")\n    opponent_power = session.get("current_opponent_power")\n    opponent_power_confidence = session.get("current_opponent_power_confidence")\n    detected_heroes = list(session.get("current_detected_heroes") or [])\n'''
    text = _replace_once(text, old, new, "perception result capture")

    old = '''        "opponent_username": opponent_username,\n        "identity_confidence": identity_confidence,\n        "detected_heroes": detected_heroes,\n'''
    new = '''        "opponent_username": opponent_username,\n        "identity_confidence": identity_confidence,\n        "opponent_power": opponent_power,\n        "opponent_power_confidence": opponent_power_confidence,\n        "detected_heroes": detected_heroes,\n'''
    text = _replace_once(text, old, new, "perception history fields")

    old = '''    session["current_opponent_username"] = None\n    session["current_identity_confidence"] = None\n    session["current_detected_heroes"] = []\n'''
    new = '''    session["current_opponent_username"] = None\n    session["current_identity_confidence"] = None\n    session["current_opponent_power"] = None\n    session["current_opponent_power_confidence"] = None\n    session["current_detected_heroes"] = []\n'''
    # One occurrence is register_result reset. Queue reset is patched separately below.
    text = _replace_once(text, old, new, "perception result reset")

    old = '''    username, username_conf = read_opponent_username(ref_screen)\n    heroes, hero_scores = scan_enemy_heroes(ref_screen)\n    identity, identity_conf, fused_source = fused_identity(direct_type, direct_source, predicted)\n'''
    new = '''    username, username_conf = read_opponent_username(ref_screen)\n    power, power_conf, power_raw = read_opponent_power(ref_screen)\n    heroes, hero_scores = scan_enemy_heroes(ref_screen)\n    identity, identity_conf, fused_source = fused_identity(direct_type, direct_source, predicted)\n'''
    text = _replace_once(text, old, new, "perception collect Power")

    old = '''        "username": username,\n        "username_confidence": username_conf,\n        "heroes": heroes,\n'''
    new = '''        "username": username,\n        "username_confidence": username_conf,\n        "power": power,\n        "power_confidence": power_conf,\n        "power_raw": power_raw,\n        "heroes": heroes,\n'''
    text = _replace_once(text, old, new, "perception intelligence return")

    old = '''                    session["current_opponent_username"] = intel.get("username")\n                    session["current_identity_confidence"] = intel.get("identity_confidence")\n                    session["current_detected_heroes"] = list(intel.get("heroes") or [])\n'''
    new = '''                    session["current_opponent_username"] = intel.get("username")\n                    session["current_identity_confidence"] = intel.get("identity_confidence")\n                    session["current_opponent_power"] = intel.get("power")\n                    session["current_opponent_power_confidence"] = intel.get("power_confidence")\n                    session["current_detected_heroes"] = list(intel.get("heroes") or [])\n'''
    text = _replace_once(text, old, new, "perception engine session fields")

    old = '''                self.emit_log(\n                    f"OPPONENT INTEL: {intel.get('identity')} {intel.get('identity_confidence')}% | "\n                    f"{user_text}{mem_text} | heroes={hero_text} | "\n                    f"threat={intel.get('threat_label')} {intel.get('threat')} | "\n                    f"decision={intel.get('decision')}"\n                )\n'''
    new = '''                power_text = (\n                    f"{int(intel.get('power')):,}"\n                    if intel.get("power") is not None else "?"\n                )\n                self.emit_log(\n                    f"OPPONENT INTEL: {intel.get('identity')} {intel.get('identity_confidence')}% | "\n                    f"{user_text}{mem_text} | power={power_text} | heroes={hero_text} | "\n                    f"threat={intel.get('threat_label')} {intel.get('threat')} | "\n                    f"decision={intel.get('decision')}"\n                )\n'''
    text = _replace_once(text, old, new, "perception intel log")

    old = '''                        session["current_opponent_username"] = None\n                        session["current_identity_confidence"] = None\n                        session["current_detected_heroes"] = []\n'''
    new = '''                        session["current_opponent_username"] = None\n                        session["current_identity_confidence"] = None\n                        session["current_opponent_power"] = None\n                        session["current_opponent_power_confidence"] = None\n                        session["current_detected_heroes"] = []\n'''
    text = _replace_once(text, old, new, "perception queue reset")

    old = '''                "opponent_power": session.get("current_opponent_power"),\n                "threat_score": session.get("current_threat_score"),\n'''
    new = '''                "opponent_power": session.get("current_opponent_power"),\n                "opponent_power_confidence": session.get("current_opponent_power_confidence"),\n                "threat_score": session.get("current_threat_score"),\n'''
    text = _replace_once(text, old, new, "perception learning trace power confidence")

    marker = "\n# V7.3 Arena Perception Integration — Power persisted in intel/history/trace build marker\n"
    if marker.strip() not in text:
        text += marker
    return text
