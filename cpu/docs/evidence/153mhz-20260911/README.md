# Portable 153 MHz evidence

This is a compact text-only archive, not a new hardware measurement. Read ../../PROJECT_HANDOVER_153MHZ.md and ../../AI_HANDOFF_153MHZ.md. Run `python cpu/scripts/verify_153mhz_handoff.py` from repository root.

The hardware qualification was independently checked against local source hashes, complete bitstreams, PDS receipts and original UART packet/session records. Private raw sessions and generated build products remain on the original workstation. Published qualification hashes referring to those original records retain their original meaning; `manifest.json` hashes the published copies, whose line endings may differ from native reports. The manifest establishes consistency, not third-party authentication.

Performance and validation UART logs are actual board output. The three algorithm CSVs and SVGs are local RTL captures, not physical ILA acquisition. Physical summary is a compact extract from source-bound PDS receipts, not a replacement for the native timing reports. Scope smoke is a partial hardware console record, not a waveform dump; its help line is visibly truncated. Electrical review remains open.
