# PDS stage resume review, 2026-11-01

The full narrow resource gate `build/resource_gate/native-20261101-224112-909881` completed compile/synthesis/dev_map successfully at 22:54:50 and exited 0. Its mapped resource result is 32,076 LUT / 33,300 FF / 120.5 DRM / 90 APM. Reports, frozen-source manifest and original log hashes are tracked under `reports/npu_narrow_full_gate_20261101/`. This does not establish routing, timing or board behavior.

## Failed resume attempts and cause

- `stage-20261101-225549-8490240c.log`: the former `run_pds_stage.ps1` launched `-file` with the original project name. PDS initialized that name before executing the script and overwrote stage state. The script restored its saved project afterwards. The pre-parser also reported `open_project` unavailable before execution.
- `project-pnr-20261101-225742.log`: the reviewer's native `-project ... -run pnr` probe unexpectedly ran Compile first. This invocation removed downstream ADF databases. The exact compile child was stopped, but **the original mapped ADF had already been removed by this probe**. This was a reviewer action, not spontaneous tool data loss. The project backup and mapped reports remain intact; project backup alone cannot restore an ADF. No bitstream was produced.
- `pnr-project-script.log`: combining `-project` and `-file` is explicitly rejected by PDS.
- `pnr-direct-action.log`: a direct internal `-action` command without parent IPC arguments is rejected.
- `pnr-independent-driver.log`: a distinct driver project name plus conditional `open_project` successfully reached `Process "Place & Route" started`, proving the safe loading approach; it then rejected the ADF missing after the earlier native-run probe. No routing completed.

The failed logs and project backups remain under the gate directory. Neither JTAG process nor downloader was touched.

## Production script repair

Only `scripts/run_pds_stage.ps1` was changed for the resume repair. It now rejects any occupied PDS slot before preparation, requires the actual predecessor ADF (synthesis for dev_map, mapped for pnr, routed `_pnr.adf` for timing/bitstream), backs up that ADF and the project, and uses a unique `resume_driver_<stamp>` project name. Its conditional `open_project` is skipped during the restricted pre-parse pass and executes when the command is available. It never uses native `-run`, which reruns earlier stages. Existing Wait/Hidden launch, post-launch single-instance check, exit/error checks, project recovery and fresh-bitstream checks remain.

Verification: Windows PowerShell 5.1 parser PASS. Invoking the repaired script on the affected gate fails before any PDS starts with `required input database missing`; no process was launched. The independent-driver PDS log supplies tool evidence that the repaired loading pattern reaches Place & Route. End-to-end resumed routing and bitstream success are **not yet verified**.

## Replacement flow

A new exact frozen single flow at `build/resource_gate/native-20261101-230237-445245` was launched at 23:03:25 to keep compile through bitstream within one process. It was stopped after a real Mel/NPU frame/mel layout mismatch was discovered. Compile had already finished; only exact synthesis child PID 42004 of parent 33872 was stopped after command-line identity and evidence capture. The original requested compile PID 6588 was no longer active. This run has no PNR result and no bitstream. Snapshot, manifest, process evidence and stop-time logs remain in its `interrupted-layout-evidence/` directory. A corrected-layout frozen flow is required next.
