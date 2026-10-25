# External CoreMark port

Derived from cpu/sw/coremark and cpu/sw/platform.h. CoreMark algorithms and license remain in the pinned dependencies/coremark checkout. See provenance.json and scripts/prepare_coremark_port.py for exact source identity and transformations. Protocol v4 specifies atomic cycle/retirement boundaries. The simulation harness derives from ports/embench/sim_main.cpp and adds the existing UART G handshake and CoreMark status markers.

Protocol v6 adds optional console pacing through the shared MMIO timer. Board-bound builds use CONSOLE_DELAY_CYCLES=2700000 after an unpaced remote capture lost data. All pacing remains outside benchmark timing. Historical run snapshots retain their original port bytes.
