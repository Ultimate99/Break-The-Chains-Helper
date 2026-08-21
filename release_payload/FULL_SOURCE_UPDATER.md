V7.1+ release payloads are self-contained full-source builds.

GitHub Actions concatenates release_payload/full_source_parts/part*.txt, base64-decodes the data, bz2-decompresses it into tg_arena_bot.py, compiles it, verifies APP_VERSION, and publishes that real full source in the update ZIP.

This intentionally replaces the old context-sensitive patch/bootstrap chain so updates no longer depend on exact previous backup source text.
