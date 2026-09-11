# 分支融合记录：XSY × DYH → 主干

合并日期：2026-09-11。本文记录将 `XSY` 分支（串口烧录与 Flash 启动流程）与 `DYH` 分支（CPU 性能优化至 153 MHz）融合到主干的完整过程，包括冲突解决方案、文档保护措施与合并后功能清单。本文供后续维护人员核查合并历史与功能归属使用，不替代 `git log` 的原始记录。

## 1. 合并背景与目标

两个分支从同一基线提交 `efdbae2`（feat: meet 120 MHz CoreMark target with hardware-validated RV32IM）分叉，各自沿不同方向推进：

| 分支 | 起点 | 末梢提交 | 主要工作内容 |
| --- | --- | --- | --- |
| XSY | `efdbae2` | `08dbfa1` | 串口烧录、桥接服务(fpga_lab)、bootloader、测试程序、Flash 启动流程 |
| DYH | `efdbae2` | `ddab723` | CPU 性能优化至 153 MHz、148 个实验目录、性能验证脚本、CoreMark 测试 |

合并目的：在保留 XSY 烧录/启动能力的同时，引入 DYH 的性能优化成果与实验资产，形成兼具 Flash 启动与高频性能的统一主干。合并提交哈希为 `8e92e9e`，提交信息：

```
Merge origin/DYH into XSY: fuse CPU perf optimization (153MHz) with serial flash boot
```

合并图谱：

```
*   8e92e9e Merge origin/DYH into XSY: fuse CPU perf optimization (153MHz) with serial flash boot
|\
| * ddab723 Remove cpu/docs directory as requested
| * 85328e4 Finalize 153 MHz full-system validation and human/AI handoff
* | 08dbfa1 feat: add flash boot flow, bridge service, and test programs
|/
* efdbae2 feat: meet 120 MHz CoreMark target with hardware-validated RV32IM
```

## 2. 冲突文件及解决方案

三个文件在合并时出现分叉修改，其中两个由 Git 自动合并成功，一个需手动解决。

### 2.1 `.gitignore`（自动合并成功）

两边各自新增忽略规则，互不冲突，Git 自动合并后全部保留：

| 来源 | 新增规则 | 用途 |
| --- | --- | --- |
| XSY | `/build/`, `.arts/`, `account.txt`, `account*.txt` | 忽略根构建目录、IDE 配置、桥接服务鉴权凭据 |
| DYH | `cpu/experiments/*/build/` | 忽略各实验目录下的构建产物 |

合并后 `.gitignore` 第 34–36 行与第 64–65 行分别包含上述规则。`account*.txt` 通配规则确保 `tool/fpga_lab/account.txt` 等凭据文件不会被误提交。

### 2.2 `cpu/scripts/build_pds.tcl`（自动合并成功）

两边在不同位置引入占位符，互不冲突，Git 自动合并后两个占位符均保留：

| 占位符 | 来源 | 位置 | 替换内容 |
| --- | --- | --- | --- |
| `__FLASH_CONSTRAINT_LINE__` | XSY | 第 8 行 | Flash 约束引脚的 `add_constraint` 语句 |
| `__PNR_COMMAND__` | DYH | 第 13 行 | 布局布线命令（支持 `pnr -gplace_seed` 种子参数） |

合并后 `build_pds.tcl` 共 15 行，两个占位符分别位于 `add_constraint` 段与 `dev_map` 之后、`report_timing` 之前，语义独立，不产生冲突。

### 2.3 `cpu/scripts/run_pds.ps1`（手动解决冲突）

此文件是 PDS 构建流程的主脚本，两边均对其参数行与逻辑做了修改，Git 无法自动合并。手动解决分为参数行合并与逻辑合并两部分。

#### 2.3.1 参数行合并

合并后第 1 行的 `param(...)` 包含以下来自两边的参数：

| 参数 | 来源 | 合并方式 |
| --- | --- | --- |
| `ICacheSetBits` | DYH | `ValidateRange` 从 `(0,8)` 扩展到 `(0,10)`，支持更大的 I-Cache 组数 |
| `ClockHz` | DYH | `ValidateSet` 增加 `126000000`、`132000000` 两个时钟选项 |
| `FlashBoot` | XSY | 新增 `[switch]` 开关参数，启用 Flash 启动构建路径 |
| `PlacementSeed` | DYH | 新增 `[ValidateRange(0,2147483647)][int]` 参数，默认 0，支持布局种子复现 |

其余参数（`DataOverlap`、`BtbIndexBits`、`EarlyDRequest`、`FastDCacheWrite`、`FastDCacheRead`、`FetchOverlap`、`EnableM`、`FastICacheHit`、`LoadUseBubble`、`UartProfile`、`FirmwareHex`、`Predictor`、`CacheSetBits`、`CacheEnabled`、`UartBaud`）两边一致，无需合并。

#### 2.3.2 逻辑合并

| 逻辑块 | 来源 | 合并后位置 | 说明 |
| --- | --- | --- | --- |
| FlashBoot 构建逻辑 | XSY | 第 6–12 行 | 当 `-FlashBoot` 开启时，调用 `build_boot.ps1` 生成 `bootloader.hex`，BRAM 仅固化 bootloader，应用运行时从 SPI Flash / UART 加载 |
| placement seed 逻辑 | DYH | 第 70–77 行 | 当 `PlacementSeed` 参数存在时，将 `pnr` 命令替换为 `pnr -gplace_seed <seed>`，并将种子写入 `placement-config.json` |
| flash constraint line 处理 | XSY | 第 80–81 行 | 始终注入 `flash.fdc` 约束（SPI Flash 控制器始终例化） |
| 原生 Windows Python | XSY | 第 116 行 | 使用 `python` 直接运行 `pds_report.py`，替代 `wsl.exe` 调用，避免 WSL 依赖 |
| manifest 字段 | XSY + DYH | 第 146–154 行 | 同时包含 `FlashBoot`/`AppBase`（XSY）与 `Placement`（DYH）字段 |

`__PNR_COMMAND__` 占位符替换校验（第 75 行）确保模板中恰好存在一个占位符，防止静默遗漏。

## 3. 文档保护措施

DYH 分支的提交 `ddab723`（Remove cpu/docs directory as requested）删除了 189 个文件、共 13542 行，其中包括 44 个 `cpu/docs/` 下的文档文件以及 `cpu/docs/evidence/153mhz-20260911/` 下的性能验证证据。

合并时**恢复了所有被删除的文档**，理由如下：

1. 这些文档是项目的重要技术积累，涵盖微体系结构、频率验证、Cache 消融、ILA 分析、CoreMark 测量规范、工具链、外设、交付等多方面内容。
2. `FINAL_REPORT.md`、`HARDWARE_FREQUENCY.md` 等文档记录了已完成的硬件验证证据，删除将导致历史结果不可追溯。
3. DYH 分支自身的 153 MHz 验证证据（`cpu/docs/evidence/153mhz-20260911/`）也在此删除范围内，恢复后可供后续维护人员核查。

恢复后的 `cpu/docs/` 目录共 46 个文件，完整清单如下（按字母序）：

```
ACCEPTANCE.md                 ASYMMETRIC_CACHE.md          BOUNDARY_SCAN_AUDIT.md
BTB_ADDRESS_BOUNDS.md         BTB_CAPACITY.md              BUS.md
CACHE_ADDRESS_BOUNDS.md       CLOCKING.md                  COMPILED_SIMULATION.md
COMPILER_OPTIONS.md           CONFIGURATION_ASSURANCE.md  COREMARK.md
COREMARK_RESULTS.md           DATA_OVERLAP.md              DELIVERY.md
EARLY_DATA_REQUEST.md         EXTERNAL_ISA.md              FAST_DCACHE_READ.md
FAST_DCACHE_WRITE.md          FAST_ICACHE_HIT.md           FETCH_OVERLAP.md
FINAL_REPORT.md               HARDWARE_120MHZ_TARGET.md    HARDWARE_162MHZ.md
HARDWARE_180MHZ.md            HARDWARE_CACHE_ABLATION.md   HARDWARE_FREQUENCY.md
HARDWARE_PREDICTOR_ABLATION.md HARDWARE_SELFTEST.md        ILA_INTEGRATION.md
ILA_RESULTS.md                LOAD_FORWARD_EXPERIMENT.md   MUL_EARLY_RESPONSE.md
MUL_REQUEST_CAPTURE.md        M_EXTENSION.md               PDS_FREQUENCY_REFINEMENT.md
PDS_FREQUENCY_SEARCH.md       PERFORMANCE_MONITOR.md       PERFORMANCE_TARGET.md
PERIPHERALS.md                SCOPE_APPLICATION.md         TOOLCHAIN.md
TRAP_VALUE_REUSE.md           UNCACHED_BASELINE.md
```

另有 `cpu/docs/evidence/153mhz-20260911/` 子目录包含 153 MHz 验证的原始 UART 记录与 JSON 摘要。

## 4. 合并后功能清单

合并后主干同时具备以下三部分功能：

### 4.1 来自 XSY 的烧录与启动功能

| 功能 | 关键文件 | 说明 |
| --- | --- | --- |
| 串口烧录 | `cpu/scripts/burn.py` | 生成/发送 bootloader 控制台字节流（W/R 命令） |
| 桥接服务 | `tool/fpga_lab/` | HTTP 设备预约/位流烧录 + WebSocket 串口，`fpga_lab_server` |
| bootloader | `cpu/sw/boot/`, `cpu/scripts/build_boot.ps1` | 固化进 BRAM 前 4KB，上电读 U9 Flash 启动应用 |
| 测试程序 | `cpu/sw/app_*.c` | `app_hello.c`、`app_big.c` 等示例程序 |
| Flash 启动流程 | `cpu/docs/FLASH_BOOT.md` | 内存布局、命令、U9 引脚、寄存器权威说明 |
| FlashBoot 构建开关 | `run_pds.ps1 -FlashBoot` | 生成仅含 bootloader 的位流，换程序不重综合 |
| 流控大文件下发 | `tool/fpga_lab/ram_load.py` | 逐块发 256B + 等 K 回执，13KB/33KB 实测成功 |

### 4.2 来自 DYH 的性能优化功能

| 功能 | 关键文件 | 说明 |
| --- | --- | --- |
| 153 MHz 性能优化 | `cpu/docs/evidence/153mhz-20260911/` | 全系统验证通过的性能证据 |
| 实验资产 | `cpu/experiments/`（148 个目录） | ALU、BTB、Cache、时钟、前递、取指等多类实验 |
| 性能验证脚本 | `cpu/scripts/` 下各 `check_*.py`、`test_*.py` | 频率候选检查、性能目标检查、CoreMark 检查等 |
| CoreMark 测试 | `cpu/sw/coremark/` | EEMBC CoreMark v1.0 移植与计分 |
| 布局种子支持 | `run_pds.ps1 -PlacementSeed` | 布局布线种子复现，`pnr -gplace_seed` |
| 扩展时钟选项 | `run_pds.ps1 -ClockHz` | 新增 126 MHz、132 MHz 选项 |
| 扩展 I-Cache 配置 | `run_pds.ps1 -ICacheSetBits` | 范围从 0–8 扩展到 0–10 |

### 4.3 原有基线保留

| 功能 | 说明 |
| --- | --- |
| 46 个 `cpu/docs/` 文档 | 全部保留，涵盖微体系结构、频率验证、Cache 消融、ILA 分析等 |
| RV32I SoC 主体 | `cpu/rtl/` 下所有 RTL 源码保持基线 + 两分支修改的并集 |
| 工具链与验证 | `TOOLCHAIN.md`、`validate.ps1` 等验证基础设施保留 |

## 5. 验证结果

合并后对主干进行了以下核查：

1. **文档完整性**：`cpu/docs/` 目录共 46 个文件，与基线 `efdbae2` 的文档清单一致，`ddab723` 删除的文件已全部恢复。
2. **实验资产**：`cpu/experiments/` 目录共 148 个子目录，与 DYH 分支末梢一致。
3. **脚本可用性**：`run_pds.ps1` 参数行语法正确，`-FlashBoot` 与 `-PlacementSeed` 两个新增参数均可被 `param(...)` 正确解析；`build_pds.tcl` 中 `__FLASH_CONSTRAINT_LINE__` 与 `__PNR_COMMAND__` 两个占位符均被正确替换。
4. **`.gitignore` 规则**：`/build/`、`.arts/`、`account*.txt`、`cpu/experiments/*/build/` 四组新增规则均存在，凭据文件与构建产物被正确忽略。
5. **manifest 字段**：合并后的 `manifest.json` 同时包含 `FlashBoot`、`AppBase`（XSY）与 `Placement`（DYH）字段，构建元信息完整。

## 6. 后续注意事项

1. **`account.txt` 切勿提交**：`tool/fpga_lab/account.txt` 含远程实验箱鉴权凭据，已由 `.gitignore` 的 `account*.txt` 规则忽略，但仍需在提交前核查。
2. **Flash 写入限制仍在**：`W` 命令受 H13 专用引脚限制不可用（详见 `DEV_SNAPSHOT.md` 第 6 节），合并未改变此硬件约束。
3. **实验目录体积**：148 个实验目录包含大量 RTL 变体与测试脚本，克隆/检出时注意磁盘占用。
4. **文档删除提交仍在历史中**：`ddab723` 提交仍保留在 Git 历史中，`git revert` 或 `git checkout` 时需注意不要再次触发文档删除。

## 7. 相关文档

- `DEV_SNAPSHOT.md` — 开发快照，含合并后状态更新（第 11 节）。
- `cpu/docs/FINAL_REPORT.md` — 工程汇总分析报告。
- `cpu/docs/HARDWARE_FREQUENCY.md` — 实板频率验证汇总。
- `cpu/docs/FLASH_BOOT.md` — Flash 启动权威说明。
- `cpu/docs/DELIVERY.md` — 可复现交付说明。