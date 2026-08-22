# TG:BTC Game Assistant 7.1.1 — Fast Daily + Verified Home Retry

Daily Assistant responsiveness and return-to-Home reliability update.

## Faster Daily actions
- Daily Assistant now starts its own low-latency Fast Vision stream while Arena grinding is stopped.
- Uses a persistent ADB tap shell for Daily navigation/actions instead of launching a new adb process for each tap.
- Screen checks use the latest streamed frame when available instead of multi-second raw screencaps.
- Reduced fixed post-tap waits; route/screen verification still guards transitions.
- Automatically falls back to normal screencap/process taps if Fast Vision or the persistent shell is unavailable.
- Daily-only transport is stopped before Arena starts, so the Arena engine remains isolated.

## Home return reliability
- Returning Home now verifies that the Home screen is actually visible.
- If Home is not visible after the first Home tap, the assistant repeats the Home action automatically.
- Up to 4 verified attempts are made before reporting `HOME FAIL`.
- If Home is already visible, no extra Home tap is sent.
- Android Back is still never used by Daily Assistant.

## Preserved
- Safe-action policy: only explicit CLAIM / CLAIM ALL / FREE targets.
- V7.1 screen anchors, Run All Safe, summaries, route teaching, and debug captures.
- User AppData profile/history/calibrations remain untouched by updates.

This release uses a deterministic checksum-verified delta from the exact v7.1.0 full-source build.
