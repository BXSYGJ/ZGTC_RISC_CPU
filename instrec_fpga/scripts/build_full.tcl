# PDS batch flow for InstRec-FPGA.
# Six stages: compile -> synthesize -> dev_map -> pnr -> report_timing ->
# gen_bit_stream (design doc section 12.2, REQ-BLD-001).
# The same template drives every build line: the top module, the design/IP/
# constraint file lists and the $readmemh table copies are all injected by
# run_pds_full.ps1 from scripts/build_sets.json (-BuildSet full|ddr3_diag|
# ui_demo), so a small diagnostic or demo build does not have to carry the
# 1.5 h full-design place-and-route.
# PDS project name (also passed on the pds_shell command line): __PROJECT_NAME__
# Tokens (double-underscore delimited; run_pds_full.ps1 substitutes all eight
# of them and refuses to run when one is missing from this file).  The token
# names are written here without their delimiters so that this comment is not
# rewritten by the substitution itself:
#   PROJECT_ROOT      this project directory (instrec_fpga)
#   BUILD_ROOT        timestamped build directory (build/pds/<run>)
#   PROJECT_NAME      PDS -project_name (<top module>_pds)
#   TOP_MODULE        top module handed to compile (instrec_top / top_*)
#   DESIGN_FILES      one add_design line per design source
#   IP_FILES          one add_design line per .idf IP core
#   CONSTRAINT_FILES  one add_constraint line; order is semantic
#   HEX_COPY_BLOCK    file mkdir + file copy -force for $readmemh tables
# Structure follows pds_cpu_100h/scripts/build_full.tcl.

# ---- Design sources: one explicit add_design line per file, generated from
# ---- the build set's sources (PowerShell expands the globs per pattern, sorts
# ---- each pattern and drops duplicates). PDS never sees a directory glob, so
# ---- the build.tcl of a finished run is the literal file set of that run.
# ---- Empty or not-yet-created directories simply contribute no line, so a
# ---- partial milestone tree still builds.
__DESIGN_FILES__

# ---- IP cores: the generated .idf files the source tree instantiates.
# ---- full attaches the HDMI GPLL (ipcore/pll/pll.idf: the pll.v wrapper is
# ---- instantiated by src/hdmi/hdmi_tx_if.v), the audio GPLL
# ---- (ipcore/pll_audio/pll_audio.idf: derived textually from the demo pll
# ---- core, RATIOM=2 / RATIOF=16.0 / RATIO0=4.0 -> VCO 864 MHz, clkout0
# ---- 216 MHz exact 8:1, GTP_GPLL instance name u_gpll kept for the fdc
# ---- generated-clock path; the pll_audio.v wrapper is instantiated by
# ---- src/ip/audio_pll.v) and the DDR3 core (ipcore/ddr3_test/ddr3_test.idf:
# ---- src/ddr3/ddr3_wrapper.v wraps it with the hard-kept instance name
# ---- I_ips_ddr_top). The diagnostic and demo sets attach only the cores they
# ---- instantiate, which is a large part of why they place and route fast.
__IP_FILES__

# ---- $readmemh tables: PDS resolves $readmemh relative paths against the
# ---- -work_dir root, NOT the process working directory (probe experiment:
# ---- "src/mel/x.hex" from the project root and the bare "x.hex" both fail
# ---- with Verilog-3001 unless the file exists under <work_dir>). Every table
# ---- of the set's hex_dirs is copied into <work_dir>/<hex_dir>/ so the
# ---- "src/mel/..." and "src/ui/..." prefixes resolve uniformly: the fft
# ---- twiddle ROMs hardcode that prefix inside fft2048_sdf.v, the mel_engine
# ---- HAN/COO/LUT parameters are overridden to the same form at the
# ---- instrec_top instantiation, and font_rom reads src/ui/font8x16.hex.
__HEX_COPY_BLOCK__

# ---- Constraints: order is semantic, PDS executes each constraint file in
# ---- load order. full requires
# ----   instrec_top.fdc -> ddr3_100h.fdc -> clock_groups_async.fdc
# ---- because the cross-domain asynchronous groups MUST be added after
# ---- ddr3_100h.fdc so the DDR family clocks they name already exist
# ---- (SDC-2027 ignores a set_clock_groups that names unknown clocks), and
# ---- ddr3_100h.fdc needs the hierarchy prefix ddr3_wrapper.I_ips_ddr_top
# ---- plus the top ref_clk_p / mem_* ports that instrec_top.fdc declares.
# ---- ddr3_diag uses ddr3_100h.fdc -> top_ddr3_diag.fdc (same reason: the pin
# ---- and clock constraints come first, the top-level wrapper after them);
# ---- ui_demo uses top_ui_demo.fdc alone.
__CONSTRAINT_FILES__

# ---- Flow anchors (substituted by run_pds_full.ps1): the project directory
# ---- that holds src/ + ipcore/ + constraints/, and this run's work directory
# ---- (the -work_dir pds_shell was started with). Echoing them keeps the
# ---- generated build.tcl self-describing in the PDS log.
set instrec_project_root "__PROJECT_ROOT__"
set instrec_build_root "__BUILD_ROOT__"
puts "instrec build: project_root=$instrec_project_root build_root=$instrec_build_root"

# ---- Architecture: Pango Logos2 PG2L100H (100Pro+ MES2L676-100HP board) ----
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676

# ---- Six-stage batch flow ----
compile -system_verilog -top_module __TOP_MODULE__
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
# Multi-seed placement: PDS runs the placer for several seeds in parallel
# (this is the only parallelism the device allows -- -number_of_router_thread
# is rejected).  Two single-seed runs both stalled (default seed ~5-7k nets,
# seed 7 ~2.4k nets), so run four seeds and let PDS keep the best.
# Multi-seed placement is the only parallelism this device allows and it is
# what finally closed the routing (Unrouted 0 at iteration 15, versus
# several thousand nets for every single-seed run).  Four seeds took over
# five hours, so keep two seeds and let PDS pick the better layout.
# Multi-seed placement closes the routing early (seed 1 reached Unrouted 0 at
# iteration 15) but PDS then keeps routing the second seed for hours.  Cap
# the action so the finished run is taken: 45 minutes is ~3x the time the
# first seed needed.
# -plc_decongestion: extra placement effort spent on spreading congested
#   regions (free in area, costs placement time).
# -dc_duplication TRUE: duplicate high-fanout cells so long nets become
#   short ones -- this trades AREA for routability, and the design has
#   FF 37% / LUT 54% to spare.
# Measured on this design:
#   -plc_decongestion 2 -dc_duplication TRUE made the route START worse
#   (47559 unrouted, 82 s/iteration) than plain placement (33302, 19 s) --
#   duplicating cells scattered the logic further, so drop both.
#   -timeout has no effect on a non-multi-seed run (log shows no abort).
# Four placement candidates in parallel, then one route pass.
# Reproduce the only configuration that ever closed on this RTL: plain pnr,
# no seed override and no multi-seed.  m2c (20261029-172919) closed at
# iteration 981 with exactly this source set.
pnr
report_timing
gen_bit_stream
