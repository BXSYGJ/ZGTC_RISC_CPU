# Fetch PC precomputation

Two isolated cores preserve the sequential PC result before prediction selection. The kept variant retains a full increment; grouped uses explicit carry boundaries without assuming alignment. All other core text and implementation inputs remain unchanged from the MMIO-ready-payload I9 baseline.

See ../../docs/FETCH_PC_PRECOMPUTE.md for measured timing motivation, source-bound tests and pending implementation evidence. These are not production or board-qualified configurations.
