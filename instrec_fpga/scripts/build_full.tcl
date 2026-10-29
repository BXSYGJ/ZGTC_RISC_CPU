# PDS batch flow for InstRec-FPGA (top module: instrec_top).
# Six stages: compile -> synthesize -> dev_map -> pnr -> report_timing ->
# gen_bit_stream (design doc section 12.2, REQ-BLD-001).
# Tokens expanded by run_pds_full.ps1:
#   __PROJECT_ROOT__  this project directory (instrec_fpga)
#   __BUILD_ROOT__    timestamped build directory (build/pds/<run>)
# Structure follows pds_cpu_100h/scripts/build_full.tcl.

# ---- Design sources: glob each src/ subdirectory; empty dirs are skipped
# ---- silently (-nocomplain), so partial milestone trees still build.
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src audio *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src ddr3 *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src mel *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src npu *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src ui *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src hdmi *.v]]] {
    # HDMI demo modules copied verbatim (T-M0-07, asset_trace.md); they are
    # only elaborated once hdmi_tx_if instantiates them.
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src ctrl *.v]]] {
    add_design $design
}
foreach design [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src ip *.v]]] {
    add_design $design
}

# ---- HDMI GPLL IP (copied from da_ad_HDMI demo, T-M0-07): pll.v wrapper is
# ---- instantiated by src/hdmi/hdmi_tx_if.v; attach its generated IP core.
add_design "__PROJECT_ROOT__/ipcore/pll/pll.idf"

# ---- Audio GPLL IP (T-M0-09 task 3): derived textually from the demo pll
# ---- core (RATIOM=2 / RATIOF=16.0 / RATIO0=4.0 -> VCO 864 MHz, clkout0
# ---- 216 MHz exact 8:1; GTP_GPLL instance name u_gpll kept for the fdc
# ---- generated-clock path); pll_audio.v wrapper is instantiated by
# ---- src/ip/audio_pll.v.
add_design "__PROJECT_ROOT__/ipcore/pll_audio/pll_audio.idf"

# ---- DDR3 IP core (enabled in T-M0-04): src/ddr3/ddr3_wrapper.v wraps it
# ---- with the hard-kept instance name I_ips_ddr_top. Since T-M0-09 the
# ---- top level instantiates the wrapper (instance name ddr3_wrapper), so
# ---- the IP is in the synthesized netlist.
set ddr3_idf "__PROJECT_ROOT__/ipcore/ddr3_test/ddr3_test.idf"
if {$ddr3_idf ne ""} {
    add_design $ddr3_idf
}

# ---- Mel hex tables (T-M1-06): PDS resolves $readmemh relative paths
# ---- against the -work_dir root, NOT the process working directory
# ---- (probe experiment: "src/mel/x.hex" from the project root and the
# ---- bare "x.hex" both fail with Verilog-3001 unless the file exists
# ---- under <work_dir>). Copy every table into <work_dir>/src/mel/ so
# ---- the "src/mel/..." prefix form resolves uniformly - the fft
# ---- twiddle ROMs hardcode that prefix inside fft2048_sdf.v and the
# ---- mel_engine HAN/COO/LUT parameters are overridden to the same
# ---- form at the instrec_top instantiation.
file mkdir [file join "__BUILD_ROOT__" src mel]
foreach melhex [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src mel *.hex]]] {
    file copy -force $melhex [file join "__BUILD_ROOT__" src mel]
}
# UI font ROM (M3) uses the same work_dir-relative $readmemh prefix.
file mkdir [file join "__BUILD_ROOT__" src ui]
foreach uihex [lsort [glob -nocomplain [file join "__PROJECT_ROOT__" src ui *.hex]]] {
    file copy -force $uihex [file join "__BUILD_ROOT__" src ui]
}

# ---- Constraints ----
add_constraint "__PROJECT_ROOT__/constraints/instrec_top.fdc"

# DDR3 pin/clock constraints: attached since T-M0-09 (the top level now
# instantiates ddr3_wrapper, so the hierarchy prefix
# ddr3_wrapper.I_ips_ddr_top and the top ports ref_clk_p/mem_* exist and
# the get_pins/get_ports calls in the copied fdc resolve).
set ddr3_fdc "__PROJECT_ROOT__/constraints/ddr3_100h.fdc"
if {$ddr3_fdc ne ""} {
    add_constraint $ddr3_fdc
}

# Cross-domain asynchronous groups: MUST be added after ddr3_100h.fdc so
# the DDR family clocks it creates exist when the group statements run
# (SDC-2027 ignores a set_clock_groups naming unknown clocks).
add_constraint "__PROJECT_ROOT__/constraints/clock_groups_async.fdc"

# ---- Architecture: Pango Logos2 PG2L100H (100Pro+ MES2L676-100HP board) ----
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676

# ---- Six-stage batch flow ----
compile -system_verilog -top_module instrec_top
# Parallelism: PDS 2022.2 on PG2L100H rejects BOTH thread switches
# (Flow-0182: -max_parallel_jobs and -number_of_router_thread are "not
# support for the device"). Synthesis and PnR therefore run single-threaded;
# multi-seed (-parallel/-route_parallel) is a different mechanism and is
# deliberately NOT enabled. Do not re-add the thread switches.
synthesize -ads -selected_syn_tool_opt 2
dev_map
# Router: default (no -fast_router). Measured 2026-10-29: fast_router needed
# 278 iterations to close, the default router 42, and BOTH produced the exact
# same placement/routing and the same timing table (ddrphy_sysclk -3.593 ns,
# 22-line diff between the two .rtr files is only the timestamp). Place and
# route are deterministic for this design, so -fast_router only saves runtime.
# The -3.593 ns path is not a router artefact; it was fixed in RTL by
# pipelining the conv MAC (DRM -> dout_q -> APM -> prod_q -> acc).
# Placement seed: PDS 2022.2 + PG2L100H is single-threaded but placement
# is deterministic for a given seed, and three consecutive builds with
# the default seed all stalled at the same unrouted count (~5-7k nets).
# -gplace_seed gives a reproducible alternative layout to try.
pnr -gplace_seed 7
report_timing
gen_bit_stream