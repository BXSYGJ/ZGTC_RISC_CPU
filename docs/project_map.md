# 仓库权威源地址簿（project_map）

> 生效：2026-11-10。目的：任何入口（人 / AI / 脚本）从这里能找到**唯一权威源**，不再靠翻目录猜。
> 本文件只做索引，不复制内容；内容变更以被指向的文件为准。
> 相关：快照与交接文档见 [SNAPSHOT_INDEX.md](SNAPSHOT_INDEX.md)。

---

## 1. 先读什么

| 场景 | 唯一入口 |
|---|---|
| 当前状态 / 阻塞 / 下一步 | `instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md`（当前快照，权威） |
| 状态变更史 | `instrec_fpga/docs/STATUS.md`（追加日志，只作历史） |
| 快照与交接文档总览 | `docs/SNAPSHOT_INDEX.md` |
| 工程规则 / 硬约束 / 命令 | `AGENTS.md` |
| 历史（200H / CPU 已交付线） | `cpu/docs/` 与 `docs/` 顶层的 200H/100H 历史报告 |

## 2. instrec_fpga（活跃主线）

| 资产 | 权威路径 | 说明 |
|---|---|---|
| 需求 / 设计 / 任务 | `instrec_fpga/docs/sdd/{spec,design,tasks}.md` | 权威；`.codeartsdoer/specs/instrec_fpga/` 是逐字节镜像副本，非权威 |
| 量化契约 | `instrec_fpga/scripts/outputs/layer_contract.json` | 唯一真源；不要用 `deploy/weights/*_bias_int32.npy` 反推 |
| 位级金标准 | `instrec_fpga/scripts/golden_pipeline.py` | 对拍只认它，不认 torch |
| 构建集 / 阶段 | `instrec_fpga/scripts/build_sets.json` | 改它等于改构建输入，需窗口期 |
| 构建产物（临时） | `instrec_fpga/build/pds/<时间戳>-<随机>/` | gitignored，不归档 |
| 构建产物（交付） | `instrec_fpga/build/instrec-latest.sbit` + `.json` | 成功构建的指针；`Wns` 必须人工读 |
| 位流里程碑 | `instrec_fpga/releases/<名字>/` | 证据，`-text` 逐字节保全；不要移动 |
| 构建/板级日志 | `instrec_fpga/reports/` | `*.log` 忽略、`*.json/*.md` 跟踪；失败构建不自动进这里 |
| 约束 | `instrec_fpga/constraints/` | 加载顺序是语义依赖（见 §5） |
| IP 源 | `instrec_fpga/ipcore/` | 由 `.gitignore` 例外纳管，不要改规则 |
| 测试 | `instrec_fpga/tests/` | 契约测试锁构建集/烧录纪律 |

## 3. 纯 CPU 线

| 资产 | 权威路径 | 说明 |
|---|---|---|
| CPU 核心 RTL | `cpu/rtl/` | `instrec_fpga` 的 `full` 构建集直接引用其中 6 个 `.sv`（见 §4） |
| CPU 板级工程 | `pds_cpu_100h/` | 独立工程；120 MHz / 383.0 CoreMark 是交付点 |
| 冻结实验 | `cpu/experiments/` | 148 个目录，`-text` 冻结；**不改名、不移动、不格式化** |
| 历史证据 | `cpu/docs/evidence/` | `-text` 冻结 |
| 153 MHz 历史交接 | `cpu/docs/AI_HANDOFF_153MHZ.md`、`cpu/docs/PROJECT_HANDOVER_153MHZ.md` | 仅用于理解 200H 历史 |

## 4. 两条线的边界与共用资产

| 项 | 现状 | 归属 / 处理 |
|---|---|---|
| CPU 核心 6 个 `.sv` | instrec 构建集写 `../cpu/rtl/*.sv` | CPU 独占；计划 P2 做固定版本快照（`instrec_fpga/src/cpu/vendor/`） |
| `ddr3_100h.fdc` | `instrec_fpga/constraints/` 与 `pds_cpu_100h/constraints/` 两份，字节相同 | 暂双份 + 哈希守卫测试；单源化需构建窗口 |
| `gen_ddr3_fdc.py` | 两份，字节相同，读 `../cpu/constraints/ddr3.fdc` | 同上 |
| DDR3 IP | 3 份、2 个 `.idf` 版本（74,193 B / 77,018 B） | **不可合并**；变体不同即硬件配置不同 |
| 板卡技能 | `docs/skills/` | 权威；`.skills/` 是旧镜像，非权威 |
| 板级纪律（`cdt_js` 复用） | 各工程各自实现 | 共享策略，改烧录脚本必须跑 `tests/test_board_flash_safety.py` |

## 5. 不能碰 / 容易踩的规则

1. **约束加载顺序**：`clock_groups_async.fdc` 必须在 `ddr3_100h.fdc` 之后，否则 clock group 被静默忽略。
2. **git 例外规则**：`ipcore/` 与 `releases/**/*.sbit` 是“全局忽略 + 精确捞回”，搬目录会同时丢入库与 `-text` 保护。
3. **冻结目录**：`cpu/experiments/**`、`cpu/docs/evidence/**`、两个 `releases/**` 均为 `-text`，逐字节保全。
4. **构建判定**：脚本“出位流即成功”，收敛必须读 `instrec-latest.json` 的 `Wns` 或 `report_timing/*.rtr`。
5. **JTAG**：`cdt_js` 只允许一个实例；禁强杀、禁新起第二个；TCL 以 `exit` 收尾。
6. **构建并发**：一次只能跑一个 `pds_shell.exe`。

## 6. 文档权威性判定

同名多份时按“**mtime 最新者为真源**”判定，判定证据见
`d:\0000\111\001\Pango\docs\ZGTC_RISC_CPU_restructure_proposal.md` 的“真源判定记录”一节。
当前结论：

- `docs/skills/` > `.skills/`（100H 版新 13 天，且新版把 CPU 内容拆到 `references/cpu_serial_flash.md`）；
- `instrec_fpga/docs/sdd/` > `.codeartsdoer/specs/`（字节相同，前者新约 14 小时）；
- 两份 `ddr3_100h.fdc` / `gen_ddr3_fdc.py` 字节相同，仅用守卫测试防漂移。
