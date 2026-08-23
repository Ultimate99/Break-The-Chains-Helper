#!/usr/bin/env python3
"""V7.3 Daily self-healing patch component."""

def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} expected one match, found {count}")
    return text.replace(old, new, 1)

def apply_daily_recovery_patch(text):
    old = '''                home_ok,home_detail=self._daily_anchor_check("HOME",start_ref)
                self.add_log(f"Daily {module}: HOME verification {'OK' if home_ok else 'FAILED'} • {home_detail}")
                if not home_ok:
                    self._daily_save_debug_frame(module,"00_not_home",start_ref)
                    self._daily_set_status(module,"OPEN HOME")
                    raise RuntimeError(f"Home screen could not be visually verified ({home_detail}). Open Home and retry.")
'''
    new = '''                home_ok,home_detail=self._daily_anchor_check("HOME",start_ref)
                self.add_log(f"Daily {module}: HOME verification {'OK' if home_ok else 'FAILED'} • {home_detail}")
                if not home_ok:
                    # V7.3: recover from a known in-app page via the visible Home
                    # control. Unknown screens are never navigated blindly.
                    current_screen,current_conf,current_detail=self._vision_identify_screen(start_ref)
                    if current_screen == "UNKNOWN":
                        ocr_screen,ocr_text=self._daily_ocr_recognize_screen(start_ref)
                        if ocr_screen in {"MAIL","SHOP","QUEST","EVENT","RECRUIT","CHAIN"}:
                            self._vision_learn_screen(ocr_screen,start_ref,evidence="OCR:start")
                            current_screen=ocr_screen
                            current_detail=f"OCR {ocr_screen} • {ocr_text[:80]}"
                    if current_screen in {"MAIL","SHOP","QUEST","EVENT","RECRUIT","CHAIN"}:
                        self.add_log(f"Daily {module}: start is {current_screen}; safely returning Home • {current_detail}")
                        if self._daily_return_home(module,max_attempts=4):
                            start_ref=self._phone_reference_screenshot()
                            home_ok,home_detail=self._daily_anchor_check("HOME",start_ref)
                    if not home_ok:
                        self._daily_save_debug_frame(module,"00_not_home",start_ref)
                        self._daily_save_failure_frame(module,"start_not_home",start_ref,home_detail)
                        self._daily_set_status(module,"OPEN HOME")
                        raise RuntimeError(
                            f"Home screen could not be safely verified ({home_detail}). "
                            "Daily will not navigate from an unknown screen."
                        )
'''
    text = _replace_once(text, old, new, "Daily safe start recovery")
    old = '''                        if not ok:
                            self._daily_save_debug_frame(module,f"route_{step:02d}_failed",last_after)
                            self._daily_set_status(module,f"ROUTE FAIL • {step}")
                            raise RuntimeError(f"Route verification failed at step {step}: expected {expected} ({detail})")
                        last_verified_anchor=expected
'''
    new = '''                        if not ok:
                            # V7.3 bounded route recovery. A navigation tap may be
                            # retried only from a page we have independently verified.
                            recovery_origin = None
                            if step == 1:
                                if self._daily_return_home(module,max_attempts=3):
                                    origin_ref=self._phone_reference_screenshot()
                                    origin_ok,origin_detail=self._daily_anchor_check("HOME",origin_ref)
                                    if origin_ok:
                                        recovery_origin=("HOME",origin_ref,origin_detail)
                            else:
                                previous_expected=(
                                    expectations[step-2]
                                    if step-2 < len(expectations) else last_verified_anchor
                                )
                                if previous_expected:
                                    origin_ok,origin_detail=self._daily_anchor_check(previous_expected,last_after)
                                    if origin_ok:
                                        recovery_origin=(previous_expected,last_after,origin_detail)

                            if recovery_origin is not None:
                                origin_name,origin_ref,origin_detail=recovery_origin
                                self.add_log(
                                    f"Daily {module}: route {step} recovery from verified {origin_name} • {origin_detail}"
                                )
                                retry_before=self._phone_reference_screenshot()
                                self._daily_tap_reference(float(x),float(y))
                                _,retry_after=self._daily_wait_frame_change(
                                    retry_before,timeout=max(0.95,DAILY_ROUTE_CHANGE_TIMEOUT),min_bits=4
                                )
                                retry_ref=retry_after if retry_after is not None else self._phone_reference_screenshot()
                                ok,detail,retry_ref=self._daily_wait_anchor(
                                    expected,timeout=3.20,initial_ref=retry_ref
                                )
                                last_after=retry_ref
                                self.add_log(
                                    f"Daily {module}: route {step} recovery expected {expected} • "
                                    f"{'OK' if ok else 'FAILED'} • {detail}"
                                )

                        if not ok:
                            if last_after is not None:
                                self._daily_save_debug_frame(module,f"route_{step:02d}_failed",last_after)
                                saved=self._daily_save_failure_frame(
                                    module,f"route_{step:02d}_{expected}",last_after,detail
                                )
                                if saved:
                                    self.add_log(f"Daily {module}: failure evidence saved {saved.name}")
                            self._daily_set_status(module,f"ROUTE FAIL • {step}")
                            raise RuntimeError(
                                f"Route verification failed at step {step}: expected {expected} ({detail}). "
                                "No unverified navigation was attempted."
                            )
                        last_verified_anchor=expected
'''
    text = _replace_once(text, old, new, "Daily bounded route recovery")
    old = '''                    if not ok:
                        if final_ref is not None:
                            self._daily_save_debug_frame(module,"destination_failed",final_ref)
                        self._daily_set_status(module,"DESTINATION FAIL")
                        raise RuntimeError(f"Could not verify {module} destination ({detail})")
'''
    new = '''                    if not ok:
                        if final_ref is not None:
                            self._daily_save_debug_frame(module,"destination_failed",final_ref)
                            saved=self._daily_save_failure_frame(
                                module,"destination_failed",final_ref,detail
                            )
                            if saved:
                                self.add_log(f"Daily {module}: destination failure evidence saved {saved.name}")
                        self._daily_set_status(module,"DESTINATION FAIL")
                        raise RuntimeError(f"Could not safely verify {module} destination ({detail})")
'''
    text = _replace_once(text, old, new, "Daily destination failure evidence")
    marker = chr(10) + "# V7.3 Daily Self-Healing Vision — OCR-verified adaptive fingerprints + bounded recovery build marker" + chr(10)
    if marker.strip() not in text:
        text += marker
    return text
