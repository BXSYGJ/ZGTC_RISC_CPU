# 快照 / 交接文档单一索引（SNAPSHOT_INDEX）

> 生效：2026-11-10。目的：从任意入口都能找到**唯一当前快照**，并知道其余快照为什么还在。
> 判定规则（用户 2026-11-10 裁定）：
> 1. 同名多份取 **mtime 最新** 者为真源；
> 2. 只有“**确认无引用 且 已被取代**”的才允许移动/合并；
> 3. 被引用或无法判定的一律**原地保留**，只在本表标注状态。
>
> 引用核查方式：`git grep` 全仓跟踪文件（排除 `build/`、`releases/`、`.codeartsdoer/temp/`）。

## 0. 当前快照（唯一）

**`instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md`**（2026-11-10，10,609 B）
一句话：48 kHz 原生前端 + `deploy/medley_48k` 已全链接入、数值 0 LSB；板级 `top1` 对 200 Hz 与 6 kHz 相同；诊断位流因 DDR3 自检在 `0x00300200` 失败暂不可用。
状态：**当前有效**。FPGA 集成链诊断（self_test → m3 共享接口 → DDR 控制器）正在进行，该文件正被并行会话读取。

## 1. 全部快照类文件

| # | 文件 | 文件日期 / mtime | 主题与覆盖范围 | 是否已被取代 | 取代者 | 引用者（已核实） | 处理 |
|---|---|---|---|---|---|---|---|
| 1 | `DEV_SNAPSHOT.md`（根） | 内容 2026-09-07 / mtime 2026-10-27 | 200H 时代全仓基线：环境、构建、烧录、已知坑 | 是 | `cpu/docs/PROJECT_HANDOVER_153MHZ.md`、`instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md` | AGENTS、CODEBUDDY、HANDOFF_DDR3、`cpu/docs/FLASH_BOOT.md`、`docs/COREMARK_TEST_REPORT.md`、`docs/MERGE_LOG.md`、`docs/开发快照交接说明_20261011.md`、`instrec_fpga/docs/CHANGELOG.md`、`reports/workspace-revert-20261027.diff` | 原地保留；已加“已归档”头 |
| 2 | `CODEBUDDY.md`（根） | 2026-09-13 | AI 入门：仓库结构、200H 主线、常用命令 | 是（AGENTS 明示过时） | `AGENTS.md` | AGENTS、HANDOFF_DDR3 | 原地保留；已加“已归档”头 |
| 3 | `HANDOFF_DDR3_AI_20260920.md`（根） | 2026-09-20 | DDR3 + AI 加速增量交接 | 是 | `instrec_fpga/docs/sdd/spec.md`、STATUS | `instrec_fpga/docs/sdd/spec.md`、`cpu/docs/AI_ACCEL_INSTREC_PLAN.md`、`cpu/docs/AI_ACCEL_PCB_100H_PLAN.md`、`docs/开发快照交接说明_20261011.md` | 原地保留（SDD 仍指向它） |
| 4 | `docs/开发快照交接说明_20261011.md` | 2026-10-11 | 100Pro PDS 全流程 / 串口 / CPU 上手指南 | 部分 | `docs/盘古100Pro+_PDS全流程与串口连接.md`、`docs/project_map.md` | `docs/盘古100Pro+_PDS全流程与串口连接.md` | 原地保留（板卡上手仍有用） |
| 5 | `cpu/docs/AI_HANDOFF_153MHZ.md` | 2026-09-11 | 200H 153 MHz AI 续接说明 | 是（100H 交付点已改） | `cpu/docs/MIGRATION_100H_20261025.md` | AGENTS、README、`cpu/README.md`、`cpu/docs/ACCEPTANCE.md`、`cpu/docs/PROJECT_HANDOVER_153MHZ.md`、`cpu/docs/evidence/**`、`cpu/experiments/**` 等 11 处 | 原地保留（历史可复现链） |
| 6 | `cpu/docs/PROJECT_HANDOVER_153MHZ.md` | 2026-09-11 | 153 MHz 人类可读交接（与 #5 成对） | 是 | 同上 | AGENTS、README、`cpu/README.md`、`cpu/docs/ACCEPTANCE.md`、`cpu/docs/AI_HANDOFF_153MHZ.md`、`cpu/experiments/**` 等 | 原地保留 |
| 7 | `instrec_fpga/docs/HANDOFF_SNAPSHOT_20261027.md` | 2026-10-27 / mtime 2026-11-01 | 资产清单、踩坑（含 UART 位序事故） | 是（4.1 节已被 STATUS 覆盖） | `HANDOFF_SNAPSHOT_20261031.md` → `20261101` → `DEV_SNAPSHOT_HANDOFF_20261110.md` | AGENTS（列为必读 2）、STATUS、CHANGELOG、`instrec_fpga/src/diag/diag_readback.v` 注释 | 原地保留（被代码注释与 AGENTS 引用） |
| 8 | `instrec_fpga/docs/HANDOFF_SNAPSHOT_20261031.md` | 2026-10-31 | 可用位流清单、板级实测原文、DDR3 排查 | 是 | `HANDOFF_SNAPSHOT_20261101.md` | STATUS（两处）、CHANGELOG、`HANDOFF_SNAPSHOT_20261101.md` | 原地保留 |
| 9 | `instrec_fpga/docs/HANDOFF_SNAPSHOT_20261101.md` | 2026-11-01 | 主线复核：`top_rv_core` / MMIO / 共享 UART | 是 | `DEV_SNAPSHOT_HANDOFF_20261110.md` | STATUS（两处） | 原地保留 |
| 10 | `instrec_fpga/docs/HANDOFF_FLASH_AND_GROUP5_20261102.md` | 2026-11-02 | Flash 启动 + Group5 两项工作的目标/资产/顺序 | 部分（目标已并入新规划） | `HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104.md` | STATUS、CHANGELOG | 原地保留 |
| 11 | `instrec_fpga/docs/HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104.md` | 2026-11-04 | **正式开发交接总规划**：优先级、性能取舍、并行分工 | **否，仍是规划权威** | — | `DUAL_MODE_HARDWARE_MODEL_DEVELOPMENT_PLAN_20261103.md`、`MODEL_TRAINING_SPEC_20261104.md`、`SOFTWARE_UI_BOOT_AND_MEMORY_ARCHITECTURE_20261103.md`、STATUS | 原地保留，不作废 |
| 12 | `instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md` | 2026-11-10 | **当前快照**：48 kHz 迁移、DDR3 自检失败、`top1` 恒定诊断 | — | — | STATUS 第 3 行、并行会话正在读 | **当前有效，禁止改动** |

相关但非快照：`instrec_fpga/docs/STATUS.md`（追加式历史日志）、`instrec_fpga/docs/CHANGELOG.md`（变更史）。

## 2. 本次核查结论

1. **可移动/合并的快照：0 份。** 12 份全部被引用（或本身是当前/规划权威），没有一份同时满足“无引用 + 已被取代”。
2. 因此本次**没有移动或删除任何快照文件**；只在 #1、#2 加了归档头，其余仅在本表登记状态。
3. 快照“到处都是”的根因不是文件数量，而是**入口没有索引**：此前 AGENTS 只指 `STATUS.md`，而 STATUS 第 3 行才指向当前快照，且 STATUS 是 60 KB+ 追加日志。现在入口固定为：
   `AGENTS.md` → `docs/SNAPSHOT_INDEX.md` → `instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md`。
4. 并行会话（FPGA 集成链诊断）只读 #12；本次未改 #12，也未改 `STATUS.md`。

## 3. 以后新增快照的规矩

1. 文件名统一 `SNAPSHOT_<主题>_<YYYYMMDD>.md`，放 `instrec_fpga/docs/`。
2. 在本表新增一行，必须填“取代谁 / 被谁取代 / 引用者”。
3. 旧快照不删除；确认无引用后，才可移到 `instrec_fpga/docs/archive/` 并在本表改路径。
