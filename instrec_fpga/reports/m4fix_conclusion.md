# m4fix 全量重建判读（m0_done 修复后）

**一句话：六阶段全 OK、布线布通、位流已产出，但时序未收敛（最差域 `ddrphy_sysclk` WNS −1.724 ns，非 m0_done 引入；`pix_clk` 由 +0.556 翻负 −0.255）；板级 `DDR3 ERR @00300000` 已消失，但 `DDROK` 未出现——症状由「确定性 abort」变为「静默挂死」，m0_done 是 `@00300000` 的根因，但不是拿不到 `DDROK` 的唯一根因。**

## 1. 本轮改动（唯一一处，团队长完成，本会话未再改源码）

`src/ctrl/instrec_top.v`：`wire m0_done;`（:133）+ **新增** `assign m0_done = ddr_done[0];`（:186）+ `.m0_done (m0_done)`（:320）。

根因链：`m0_done` 声明后从未驱动 → PDS 只报 `Verilog-2036 ... has no driver, tie it to 0` 并静默 tie 0
（上一轮 run `20261031-135808-f1cb68bd` 的 `compile/run.log:4204` 原文）；`audio_sink` 的命令是电平保持式
（`m0_cmd_valid` 一直保持到 `m0_done`），tie-0 使 m0 永久占住仲裁，固定优先级下 m3（`self_test`）被饿死，
4096 拍后 abort → 板级 `DDR3 ERR @00300000`。

**本轮实测该告警消失**：新 run 的 `compile/error_info.txt` 无该行、`compile/run.log` 无 `Verilog-2036`；
`flow.log` 的网表输入网列表出现 `Input nets: m0_done page_go`，说明 `m0_done` 已是真实被驱动的网。

## 2. 构建（唯一一次，纯 `pnr`，无任何 PNR 参数）

| 项 | 值 |
|---|---|
| run 目录 | `build/pds/20261031-162107-81c5a894` |
| 启动 / 位流写出（本地） | 2026-10-31 16:21:07 → 18:28:17 |
| **总耗时** | **127 min** |
| 详细布线 | **1151 iter / 4326.44 s（72 min）**，`Unrouted nets 0 @ iter 1151` |
| 保持违例修复 | 6 iter / 94.17 s |
| 位流 SHA-256 | **`B895FCACB9B037D421AE26885A7DBE2F04D5DEA1E5D3ECE385CC0B671707FBA2`** |
| 上一轮 SHA（对照） | `44E8F011D44E10254E33BCBE4622BEB3F53966894C00BD1962BE9420414D476C` |

### StageStatus（六项，manifest 原文）

| stage | status |
|---|---|
| compile | **OK** |
| synthesize | **OK** |
| dev_map | **OK** |
| pnr | **OK** |
| report_timing | **OK** |
| gen_bit_stream | **OK** |

### 布线判定：**布通**

- `flow.log:34339` → `Unrouted nets 0 at the end of iteration 1151.`
- `flow.log:34341-34342` → `Detailed routing takes 1151 iterations` / `4326.44 sec.`
- `pds.stdout.log` → `Executing : pnr successfully`，`flow.log` 出现 `placed and routed successfully`（18:19）

### 未布网络序列（采样 1269 点，全程单调下降，**非停滞**）

```
iter   1: 79341   iter 127: 5110   iter 308: 985   iter 526: 386   iter 1001:  90
iter  19: 28011   iter 202: 3176   iter 400: 669   iter 740: 352   iter 1046:  33
iter  45: 14464   iter 281: 1585   iter 642: 408   iter 1001 见上  iter 1104:   6
iter  77: 8885    iter 299: 1136   iter 911: 192   iter 1151:  0
iter 118: 5462
```
证据文件：`build/pnr_watch_m4fix.jsonl`（采样脚本 `build/pnr_watch_m4fix.py`，均在 gitignore 的 `build/` 内）。

本轮比上一轮明显更难：**1151 iter vs 636 iter**。90 分钟节点（17:51）时 iter 311 / 1043 未布，
iter 500–950 区间长期震荡于 150–500（rip-up/reroute 正常抖动），iter 962 起才快速收敛（239→149→90→55→11→0），
**因此在 90 分钟处判「未停滞、继续等待」是正确判断，不是空等**。

## 3. 资源（post-PnR）

| 资源 | 本轮 | 上一轮 |
|---|---|---|
| LUT total | **34561/66600 (52%)** | 34407/66600 (52%) |
| FF total | 52450/133200 (39%) | 52193/133200 (39%) |
| **DRM** | **86/155 (56%)** | 86/155 (56%) |
| Distributed RAM | 1501/19900 (8%) | 1501/19900 (8%) |
| APM | 90/240 (38%) | 90/240 (38%) |
| USCM | 22/32 (69%) | 11/32 (35%) |
| HCKB | 46/96 (48%) | 32/96 (34%) |
| BKCL / CCS | 6/6 (100%) / 1/1 (100%) | 同 |

LUT +154、FF +257、USCM +11、HCKB +14 —— 一行 `assign` 引起的布线代价远大于逻辑代价（多出来的 USCM/HCKB 是布线资源）。

## 4. 逐域时序（`report_timing/instrec_top.rtr` 的 `Setup Summary(Slow Corner)`）

| Launch/Capture 域 | 本轮 WNS (ns) | failing endpoints | 上一轮 WNS (ns) | 上一轮 failing |
|---|---|---|---|---|
| clk_nco | **+1.202** | 0 | +0.523 | 0 |
| **pix_clk** | **−0.255** | 1 | +0.556 | 0 |
| cfg_clk | **+89.848** | 0 | +92.287 | 0 |
| rst_clk | +2.690 | 0 | +4.227 | 0 |
| **ddrphy_sysclk** | **−1.724**（TNS −337.801） | **1197** | −1.740（TNS −124.797） | 482 |

**判读要点**

- manifest 的 `Wns=1.202` 只是表格第一行（`clk_nco`），**不是最差域**；最差域是 `ddrphy_sysclk −1.724`。
- `ddrphy_sysclk` 负值**不是 m0_done 引入**：上一轮 `44E8F011` 已有 −1.740，是既有时序债。
  但本轮 failing endpoint 482→1197、TNS −124.8→−337.8，**该域恶化 2.7×**。
- `pix_clk` 由 +0.556 翻负到 −0.255（1 个 endpoint），也是本轮新增。
- 故「All Constraints Met」**本轮不成立**。这构成板级判读的混淆项：若 DDR3 自检仍失败，不能唯一归因于 m0_done。
- `Whs=0.248`（hold），`clk_nco/pix_clk/cfg_clk/rst_clk` 四域 setup 见上表。

## 5. 板级验证：**未拿到 `DDROK`（verdict FAIL / exit 5）**

命令（2026-10-31 18:30 本地）：
```
python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 25 \
    --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK" --json reports/board_m4fix_20261031T103000Z.json
```
脚本输出原文：
```
ftdi: present  jtagserver: [9040]  cdt_cfg: none  port65420: open
UART COM5 opened before programming
reusing the running jtagserver (PID 9040, not restarted)
cdt_cfg exit code: 0
program: True
status: 0x081ffca0 done=1 crc_err=0
jtagserver instances stable at [9040] (single UI, reused)
uart: 30 bytes (saved build/uart_last.bin)
  line: INSTREC BOOT  OK
  line: DDR3 SELFTEST...  OK
boot: FAIL (missing DDROK)
```
`build/uart_last.bin` 原始 30 字节（逐字节）：
```
b'INSTREC BOOT\nDDR3 SELFTEST...\n'
```
免重烧二次抓取 `python scripts/uart_capture.py --port COM5 --seconds 45` → **0 byte**（无第三行，无 `DDROK`、无 `DDR3 ERR`）。

**与上一轮的关键差异**：上一轮同命令抓到 **49 字节**（= 30 字节 + `DDR3 ERR @00300000\n`），
即「确定性 abort」；本轮 **不再出现 `DDR3 ERR @00300000`**，但也没有 `DDROK` —— 症状由
「报错退出」变成「**静默挂死**」（`st_done`/`st_fail` 均未置起，sys_ctrl 的 100 ms 整测 watchdog 也没有打印结论行）。

`WOK`：**未测试**（按顺序 `DDROK` 未出现即不进入 `weight_upload`，避免把未就绪的 DDR3 写坏）。

纪律遵守：`cdt_js` PID 9040 **复用**（脚本原文 `reusing the running jtagserver (PID 9040, not restarted)`），
未新起、未 terminate；`cdt_cfg` 退出码 0；`status 0x081ffca0 done=1 crc_err=0` 说明位流烧写成功、FPGA 起振。

## 6. m0_done 是否即 `@00300000` 的根因

**判定：m0_done 是 `@00300000` 的根因（已由「告警消失 + 该行消失」双重证实），但它不是「拿不到 `DDROK`」的唯一根因。**

证据闭环：

1. 修复前：`Verilog-2036 ... m0_done ... has no driver, tie it to 0`（上一轮 `compile/run.log:4204`）→ 网表里 tie 0。
2. 修复后：该告警消失，`flow.log` 出现 `Input nets: m0_done page_go`（真实被驱动网）。
3. 修复前板级：**确定性** `DDR3 ERR @00300000`（两次逐字节相同，49 字节）。
4. 修复后板级：**该行彻底消失**（30 字节，且 45 s 二次抓取 0 字节）⇒ 原 abort 通路已被切断，
   **`@00300000` 这条具体失败正是 m0_done tie-0 造成的**。
5. 但 `DDROK` 仍未出现，症状升级为**静默挂死**：`self_test` 的 F1~F7 里 `st_done`/`st_fail` 均未置起，
   而它只有在拿到仲裁授权、真正发出命令后才会启动 AXI watchdog；静默等待意味着
   **m3 从「被 m0 饿死并 abort」变成「等不到授权或等不到 `ddr_done[3]`，且没有任何超时兜底」**。

因此下一步要查的是（按优先级）：

- **a) 其余 masters 是否顶替了 m0 的位置**：`m1`（NPU 权重）/ `m2`（mel_engine）在无上位机上传、无 I2S 输入时
  是否仍长期拉高 `cmd_valid`（电平保持式命令）；`audio_sink` 在修复后 `cmd_valid` 是否真的会撤。
- **b) `ddr_done[3]` 是否被控制器/仲裁器正确回送**（`self_test` 等的是 m3 的完成脉冲）。
- **c) `ddrphy_sysclk` WNS −1.724 ns（1197 failing）**：这是**修复前就存在**的时序债（上一轮 −1.740），
  但它会让 DDR PHY 采样边界不可靠；即使仲裁修好，也可能因 PHY 时序拿不到 `DDROK`。
  **任何「DDR3 硬件已坏」的结论都必须先排除这一条**（建议用 `top_ddr3_diag` 的 20 min 小位流对照）。

## 7. 其他发现（已上报，团队长已修）

`src/ui/demo_wave_source.v:62/66` 用 `tri` 作标识符（Verilog 保留字）→ compile 报
`Verilog-4005 ... Syntax error near tri`（本轮与上一轮 `compile/error_info.txt` 都含这两行；compile 仍报
`sdm2adm successfully`，故全量不受影响，`instrec_top` 不例化该模块）。T9 的 `top_ui_demo` 会例化它，
`ui_demo` 构建会被挡住。团队长已改为 `tri_val`。`check_rtl.py` 只做词法检查，查不出 `Verilog-4005`。