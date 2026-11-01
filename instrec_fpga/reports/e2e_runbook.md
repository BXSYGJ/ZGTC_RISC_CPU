# T11 板级端到端（E2E）运行手册 —— 全量位流出来后的照抄执行清单

> 本文件由 **T17（T11 预检，纯只读）** 产出，依据为 2026-10-31 现场源码与磁盘状态。
> 所有命令均在 `instrec_fpga/` 下执行；所有判据 token 均带**源码行号出处**，未臆造。
> 本文件不构成"位流已产出"或"E2E 已通过"的证据。

---

## 0. 前提（不满足就不要开始，否则会污染证据）

T11 必须**在 T10 全量构建完全结束之后**执行，四条硬前提逐条确认：

| # | 前提 | 判据 | 不满足时 |
|---|---|---|---|
| P1 | 构建进程已全部退出 | `Get-Process pds_shell` **返回空**（构建期间非空属正常，见 §1） | 等待，**禁止** kill，禁止并发起第二个 `pds_shell` |
| P2 | 位流新鲜 | `build/instrec-latest.sbit` 的 `LastWriteTime` **晚于** T10 启动时刻 | 说明构建未收尾或产物未复制，回 T10 |
| P3 | 六阶段全 OK | `build/instrec-latest.json` 的 `StageStatus` 恰为 compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream 六项且全部 `"OK"` | 任一项非 OK ⇒ 无可用位流，T11 不启动 |
| P4 | 位流与 manifest 一致 | `.sbit` 的 sha256 大写 == `json.BitstreamSha256` | 不一致 ⇒ 拷贝/归档串了，回 T10 重取 |

> 现场快照（只读取证，写于 2026-10-31 14:4x）：`build/instrec-latest.sbit` 3,791,112 B、`build/instrec-latest.json` 2,393 B，
> 两者 mtime 均为 **2026-10-31 10:46**（T10 之前的上一轮全量位流）；同时 `pds_shell` 有 **2 个进程**
> （PID 45664 起 13:58、37376 起 14:28，属同一轮构建的父/子进程）。
> **因此该 sbit 不是 T10 产物，P2 当前为"未满足"。**

---

## 1. 前置检查（只读，不碰硬件、不启停任何进程）

```powershell
cd D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga

# P1：构建是否已结束（空 = 已结束）
Get-Process pds_shell -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime

# JTAG 常驻实例：必须恰好 1 个（当前预期 PID 9040），只复用、绝不 terminate
Get-Process cdt_js -ErrorAction SilentlyContinue | Select-Object Id,StartTime

# P2/P3/P4：位流新鲜度 + 六阶段 + sha
Get-Item build\instrec-latest.sbit, build\instrec-latest.json | Select-Object Name,Length,LastWriteTime
python -c "import json;d=json.load(open('build/instrec-latest.json',encoding='utf-8'));print('stages',[(s['Stage'],s['Status']) for s in d['StageStatus']]);print('wns',d['Wns'],'sha',d['BitstreamSha256'])"
python -c "import hashlib;print('sbit sha256',hashlib.sha256(open('build/instrec-latest.sbit','rb').read()).hexdigest().upper())"
```

**关于 `pds_shell` 非空**：这与本任务无关，是 T10 正在跑（脚本本身不查并发，一次只允许一个构建）。
T11 **不得**在构建期间启动烧录——烧录虽不占构建槽，但会占用板子与串口，且位流还是旧的。

**关于 `cdt_js`**：只允许一个常驻实例（它持有 FT2232H 的 D2XX 句柄）。
强关它或再起第二个 ⇒ 下载器从 PnP 消失（`CM_PROB_PHANTOM`），只能物理重插。
`board_check.py` 会自动复用（`ensure_server()`，`scripts/board_check.py:178-199`），**任何脚本都不要 `Stop-Process` / `terminate`**。

---

## 2. 一键命令序列（按序粘贴）

时间戳变量 `$ts`：先在 PowerShell 里执行 `$ts = Get-Date -Format yyyyMMddTHHmmssZ`（例：`20261031T150230Z`），
下文命令直接引用 `$ts`，无需手工替换。

### Step 0 —— 离线预检与证据保护（无硬件，仍建议执行）

```powershell
cd D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga
$ts = Get-Date -Format yyyyMMddTHHmmssZ
New-Item -ItemType Directory -Force reports\board_e2e | Out-Null

# 0.1 权重镜像帧预算（纯离线，不打开串口；--dry-run 分支在 import serial 之前返回）
python scripts\weight_upload.py --image scripts\outputs\weights_image.bin --dry-run
```
**预期输出/判据**：`image scripts\outputs\weights_image.bin: 691040 bytes, sha256 19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a`，
随后 `frames: 2701 (including end frame)`；退出码 0。（2700 个数据帧 + 1 个 end 帧，每帧 256 B）

```powershell
# 0.2 golden 对拍链路自检（纯离线，把 golden 参考回灌 compare_layers，必须 100% 一致）
python -m pytest tests\test_compare_layers_selfcheck.py -q
```
**预期输出/判据**：`4 passed`（已实测 0.62 s）。若 skip ⇒ `reports/golden_ref/sine_440_full/` 缺失。

```powershell
# 0.3 备份上一轮板级原始字节（build/uart_last.bin 会被下一个板级脚本覆盖，单副本）
Copy-Item build\uart_last.bin reports\board_e2e\prior_uart_last_$ts.bin -Force
```
**预期输出/判据**：文件存在，1183 B（当前内容为 T8 第二轮 DDR3 诊断证据；不要丢弃）。

### Step 1 —— 烧录 + boot 判读（唯一判 DDR3 阻塞是否解除的一步）

```powershell
python scripts\board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 20 `
  --json reports/board_e2e_$ts.json `
  --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"
echo "exit=$LASTEXITCODE"
```
**预期输出/判据**：
- `ftdi: present  jtagserver: [9040]  cdt_cfg: none  port65420: open`
- `reusing the running jtagserver (PID 9040, not restarted)`
- `program: True`、`status: 0x081ffca0 done=1 crc_err=0`
- `boot: PASS (all 3 expected lines seen)`，**退出码 0**
- `--json` 落盘 12 键（`EVIDENCE_KEYS`，`scripts/board_check.py:75-88`），`verdict` 为 `PASS`

> `--expect` 是 `nargs='*'`（`board_check.py:469`），**必须放在命令最后**，否则会吞掉后续参数。

### Step 2 —— 权重上传（拿 `WOK`）

```powershell
python scripts\weight_upload.py --port COM5 --image scripts\outputs\weights_image.bin
echo "exit=$LASTEXITCODE"
```
**预期输出/判据**：
- `image ...: 691040 bytes, sha256 19a74dbe...`
- 进度行 `  64/2700 frames` … `  2700/2700 frames`
- `board reply: WOK <8hex>` 且 `UPLOAD OK`，**退出码 0**
- **预算**：2700 帧 × (256 B @115200 ≈ 22 ms + ack 往返)，**估算**量级 **1.5~3 min**（本预检未实测烧板）；若给超时，设 **8 min**

### Step 3 —— 抓原始串口（可选，补充证据；不烧录）

```powershell
python scripts\uart_capture.py --port COM5 --seconds 20 --out reports\board_e2e\uart_after_wok_$ts.txt
```
**预期输出/判据**：文本 dump + `[captured N byte(s)]`；N>0。此步用于证明板子在 WOK 后仍存活、无新增错误行。

### Step 4 —— 逐层对拍（只有同时满足两个前置才可执行，否则记 DEFERRED）

前置：① I2S 有**与 golden 同源**的真实音频输入；② 位流内含 design.md 9.2 逐层 UART 导出。

```powershell
python scripts\uart_capture.py --port COM5 --seconds 30 --frames --out-dir reports\layers_sine_440_full
python scripts\compare_layers.py reports\layers_sine_440_full `
  --golden-feat reports\golden_ref\sine_440_full\feat.npy --probs-encoding percent
echo "exit=$LASTEXITCODE"
```
**预期输出/判据**：
- capture：`[frames N, bytes M]` 且每个 `layer 0xXX NAME: bytes` ≥ 契约字节数；否则 `[frames 0, bytes M]`
- compare：`8 layer(s) compared, 0 failed`，逐层 `exact`/`within1` = 100%，`max_abs_delta = 0`；退出码 0
- **必须用 `--golden-feat` 显式指向 `reports/golden_ref/sine_440_full/feat.npy`**（理由见 §6 坑 K-3）

> ⚠️ 截至本预检，**当前 RTL 不存在 9.2 逐层导出**（见 §7 D-1），故本步预期结果为
> `no layer_*.npy in reports\layers_sine_440_full` ⇒ **退出码 1 ⇒ 记 DEFERRED（不是 PASS）**。

### Step 5 —— 一键链路（仅参考；本任务不推荐主用）

```powershell
python scripts\board_e2e.py --sbit build/instrec-latest.sbit --port COM5 --stage boot
python scripts\board_e2e.py --stage weights
python scripts\board_e2e.py --stage layers --seconds 30 --stem sine_440_full
```
**预期输出/判据**：每阶段末行 `--- <stage>: PASS (rc=0)`，最后 `=== summary ===`。
不推荐主用的原因：`boot` 阶段把 `--seconds` 硬编码为 `8`（`scripts/board_e2e.py:77`），
且**不传 `--json`**，无法产出 `C-BOARD-CHECK@1` 证据文件；`layers` 阶段只传 `--stem`
（会命中全零静音 golden，见 K-3）。

### Step 6 —— 收尾

```powershell
# 确认 JTAG 实例集合未变（应与 Step 1 前完全相同，仍只有一个 PID）
Get-Process cdt_js -ErrorAction SilentlyContinue | Select-Object Id
# 证据清单
Get-ChildItem reports\board_e2e, "reports\board_e2e_$ts.json", build\uart_last.bin | Select-Object Name,Length,LastWriteTime
```
**预期输出/判据**：`cdt_js` 仍为 **1 个**（PID 9040）；`--json` 里 `jtagserver_pids` 与收尾实测一致。

---

## 3. 依赖文件核查表（2026-10-31 现场 `Path.exists()` + 大小实测）

| 用途 | 文件 | 状态 | 实测大小 / 备注 |
|---|---|---|---|
| 烧录位流 | `build/instrec-latest.sbit` | **存在（但非 T10 产物）** | 3,791,112 B，mtime 2026-10-31 10:46 |
| 位流 manifest | `build/instrec-latest.json` | **存在（但非 T10 产物）** | 2,393 B，六阶段 OK，`Wns=1.347`，sha `0B2BE8D4…7357` |
| 权重镜像 | `scripts/outputs/weights_image.bin` | **齐备** | 691,040 B，sha256 `19a74dbe…5d7a`，2700+1 帧 |
| 数值契约 | `scripts/outputs/layer_contract.json` | **齐备** | 65,102 B（UTF-8） |
| Mel 表 | `scripts/outputs/mel_tables.json` | **齐备** | 115,045 B |
| golden feat（默认目录） | `scripts/outputs/golden/sine_440_full_feat.npy` | **存在但内容为全零静音** | 16,640 B，`int8`，min=0 max=0 ⚠️ 见 K-3 |
| golden feat（正确参考） | `reports/golden_ref/sine_440_full/feat.npy` | **齐备** | 16,640 B，`uint8`，0..255 |
| golden 逐层参考 | `reports/golden_ref/sine_440_full/{conv1,conv2,conv3,conv4,fc1,fc2_logits,probs*}.npy` | **齐备** | conv1 792,704 B；conv2 396,416 B；conv3 196,736 B；conv4 65,664 B；fc1 256 B；fc2_logits 160 B；probs_u8_percent 136 B |
| 上一轮串口字节 | `build/uart_last.bin` | **存在（将被覆盖）** | 1,183 B，mtime 2026-10-31 13:50 ⇒ Step 0.3 先备份 |
| E2E 证据目录 | `reports/board_e2e/` | **缺失，需先创建** | Step 0 的 `New-Item` |
| 逐层抓取目录 | `build/board_frames/`（默认） / `reports/layers_sine_440_full/` | **缺失，脚本自动创建** | `uart_capture.py:102-103` |
| 结论文件 | `reports/e2e_conclusion.md` | 缺失（T11 交付物，Step 6 后写） | — |

**契约自洽性已核对通过**：`layer_contract.json` 的 `image_total_bytes = 691040` 与镜像实测长度一致；
`image_sha256 = 19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a` 与镜像实测 sha256 **逐字符一致**。

---

## 4. 判据 token 的准确字符串（逐个带出处）

`board_check.py` 的匹配方式是**全文子串**匹配：`token.encode() not in raw`
（`scripts/board_check.py:448`），不是按行、不是正则，故 token 内不要带换行。

| token（`--expect` 写法） | 板子实际打印 | 出处 | 何时出现 |
|---|---|---|---|
| `INSTREC BOOT` | `INSTREC BOOT\n`（13 B） | `src/ctrl/uart_debug.v:86`；触发 `src/ctrl/sys_ctrl.v:223`（ST_BOOT） | 上电/烧录复位后第一行 |
| `DDR3 SELFTEST` | `DDR3 SELFTEST...\n`（17 B） | `src/ctrl/uart_debug.v:88`；触发 `sys_ctrl.v:254`（ST_DDR） | PLL 全锁后 |
| `DDROK` | `DDROK\n`（6 B） | `src/ctrl/uart_debug.v:89`；触发 `sys_ctrl.v:270`（ST_DDW 收到 `st_done`） | 自检 16-beat 写/读回通过 |
| `PLL LOCK ERR` | `PLL LOCK ERR\n`（13 B） | `src/ctrl/uart_debug.v:87`；触发 `sys_ctrl.v:234,242` | HDMI 初始化失败或 PLL 超时 5 s |
| `DDR3 ERR @` | `DDR3 ERR @<8hex>\n` | `src/ctrl/uart_debug.v:90`；触发 `sys_ctrl.v:275,281` | 自检失败或 100 ms 看门狗超时 |
| `WOK` | `WOK <8hex>\n`（13 B） | `src/ctrl/weight_loader.v:333-336`（`8'h57/4F/4B/20`）+ 8 位 hex + 换行（`:354`） | 权重整镜像写完后**回读折叠 digest 一致** |
| `WERR` | `WERR <8hex>\n` | `src/ctrl/weight_loader.v:338-340`（覆盖为 `E/R/R`） | 回读折叠 digest 不一致 |
| ~~`RUN`~~ | `RUN\n`（4 B，已定义） | `src/ctrl/uart_debug.v:91` | **永不出现**：`sys_ctrl.v` 全文没有任何 `dbg_line_id <= 3'd5`（仅 0/1/2/3/4），见 K-1 |

> `WOK` / `WERR` 是 `weight_loader` 直接写 UART 的，**不是** `board_check --expect` 的抓取对象（时序上不在 boot 窗口）。
> 它们的"出处"是 `weight_upload.py` 的 stdout 行 `board reply: <text>`（`scripts/weight_upload.py:161-163`），
> **不会**落到 `build/uart_last.bin`；结论里抄这一行原文即可。

---

## 5. 判据与失败处置

### 5.1 Step 1（boot）失败

| 现象 | 最可能原因（按概率） | 下一步动作 |
|---|---|---|
| 退出码 **2**，`ftdi: ABSENT` | ① 下载器从 PnP 消失（此前被杀 `cdt_*` 的后遗症）② USB 松动 ③ 板子未上电 | ① 物理重插 USB（**不要**杀进程重试）② `python scripts\board_check.py --diag-only` 复测 ③ 确认电源/`cfg_scan_chain` |
| 退出码 **3**，`program: False` 或 `cdt_cfg exit code: 1` | ① 位流与器件不匹配 ② sbit 路径错（相对 `instrec_fpga/`）③ 电缆频率过高 | ① 核 `json.TopModule`/`Device=PG2L100H-6IFBG676` ② 用绝对路径 ③ 加 `--freq 5Mhz` 重试 |
| 退出码 **4**，`cdt_cfg did not exit` | cdt_cfg 卡在 `cfg_connect`（port 65420 无响应） | **脚本已把 PID 打印出来且故意不杀**；等 1 min 后看 `build/board_check_program.log`，再单独 `--status-only` 复测；仍卡则物理重插 USB |
| 退出码 **5**，缺 `INSTREC BOOT` | ① 串口号错（`COM5` 被占用/换成其它）② 位流未含 `uart_debug` 电平握手修复 ③ 抓取窗口太短 | ① `uart_capture --seconds 5` 看有无任何字节 ② 核 sha 是否为最新全量位流 ③ `--seconds 20`（PLL 超时 5 s + 自检） |
| 缺 `DDR3 SELFTEST` 但有 `INSTREC BOOT` | 卡在 ST_PLL：HDMI 未初始化 / PLL 未锁 / `ddr_init_done` 未到 | 等 `PLL LOCK ERR`（5 s 超时）或延长窗口；若 20 s 内两条都不出 ⇒ 该位流的 `sys_ctrl` 走了 `hdmi_fail_s` 提前分支，查 HDMI 侧 |
| 缺 `DDROK` 但见 `DDR3 ERR @…` | DDR3 写/读通路仍错（T8 已定位过一次，可能在新参数下复现） | 把 `8hex` 解成 `st_fail_addr`（`sys_ctrl.v:276`），与 `reports/ddr3_diag_conclusion.md` 的失败模式表对照；**不要**改 RTL 现场试 |
| `done=0` 或 `crc_err=1` | ① 烧录未成功 ② 位流损坏 | ① 重跑 Step 1 一次 ② 复核 P4 的 sha |

### 5.2 Step 2（权重）失败

| 现象 | 最可能原因 | 下一步动作 |
|---|---|---|
| `image ... not found` / `[Errno 2]` | `--image` 路径相对 `instrec_fpga/` 写错 | 用 `scripts\outputs\weights_image.bin`（默认值即此） |
| 卡在某一帧 `frame N (seq M) not acknowledged` | ① 板子不在可接收状态（`uart_rx` 未使能 / 复位中）② m1 AXI 写通路被自检占用 ③ 波特率/线序错 | ① 先重跑 Step 1 确认 `done=1` ② 确认烧录后**未**按 KEY1（会重跑自检）③ 核 `--baud 115200` |
| `board reply: WERR <8hex>` 且 `UPLOAD FAILED` | 写进去的数据回读不一致：① DDR3 写通路（`wlast`/16-beat）② 镜像长度与 `BASE_ADDR` 计算错位 | ① 用 `weight_loader` 的 digest 与 Python 侧同算法复算比对 ② 核 `BASE_ADDR=0`（RTL 默认）与镜像 691040 B 的帧对齐；**先**回 T8 的 DDR3 写通路结论 |
| 5 s 内无 `WOK`/`WERR`（空 reply），`UPLOAD FAILED` | ① 回读 2700 帧超 5 s（`weight_upload.py:110` 硬编码 5 s）② 板子已进 `ST_SAFEERR` | ① 用 `uart_capture --seconds 30` 观察是否有迟到行 ② 重新烧录再试一次 |
| 上传到一半板子静默 | ① 触发了 `AXI` 看门狗 ② 上位机被其它程序抢串口 | ① 重烧并先做 Step 1 ② 关闭其它串口工具（**唯一** `--port COM5` 占用者） |

### 5.3 Step 4（逐层）失败

| 现象 | 最可能原因 | 下一步动作 |
|---|---|---|
| `[frames 0, bytes N]`、`no layer_*.npy in ...`（rc=1） | ① **当前 RTL 无 9.2 逐层导出**（见 D-1）② 无 I2S 音频 ⇒ 无窗口完成事件 | 直接记 **DEFERRED**，不重试；在结论里写明两条原因 |
| 有帧但 `exact` 很低 | ① 板子输入音频与 golden 不同源 ② 参考取自全零静音 feat | ① 用与 `sine_440_full` **同一 wav** 驱动 I2S ② 显式 `--golden-feat reports\golden_ref\sine_440_full\feat.npy` |
| `reference generation failed`（rc=2） | 契约/权重/Mel 表路径错，或 `--stem` 找不到文件 | 用默认路径 + `--golden-feat`；核 §3 表 |
| 某层 `max_abs_delta` 明显而其它层为 0 | 该层定点契约漂移（requant 舍入、padding zp、shift 位宽） | 按 `AGENTS.md`「数值与 DDR3 契约」查该层；只认 `golden_pipeline.py`，不认 torch |

---

## 6. 已知坑（现场务必遵守）

- **K-1 `RUN` 不是判据**：`src/ctrl/uart_debug.v:91` 定义了 `RUN\n`，但 `sys_ctrl.v` 没有任何分支把
  `dbg_line_id` 置为 `3'd5`（只有 0/1/2/3/4）。因此 `docs/STATUS.md:566` 建议的
  `--expect "DDR3 SELFTEST" "DDROK" "RUN"` **必然返回退出码 5**。正确写法见 §2 Step 1（三个 token，去掉 `RUN`）。
- **K-2 `board_e2e.py` 的 boot 窗口是 8 s**（`board_e2e.py:77` 硬编码），比 plan 要求的 20 s 紧；
  且它不传 `--json`。故 Step 1 请直接用 `board_check.py`。
- **K-3 golden feat 有两个同名来源，默认那个是静音**：
  `scripts/outputs/golden/sine_440_full_feat.npy` 是 `int8`、min=max=0（全零）；真正的参考是
  `reports/golden_ref/sine_440_full/feat.npy`（`uint8`，0..255）。`compare_layers` 的默认
  `--golden-dir` 是前者（`compare_layers.py:58`），`board_e2e --stem` 也只会命中前者 ⇒ **必须显式
  `--golden-feat`**。另注：`reports/golden_ref/` 下是 `<stem>/feat.npy` 布局，`find_golden_feat()`
  只找 `<stem>_feat.npy`，用 `--golden-dir reports\golden_ref` 会报找不到。
- **K-4 `uart_last.bin` 是单副本**：`board_check.py:425` 每次覆盖它。Step 0.3 先备份，否则 T8 的
  诊断原始字节永久丢失。
- **K-5 `cdt_js` 永远只复用**：`board_check.py:178-199` 若发现已有实例就复用它（端口没起来也只是等 30 s），
  只有完全没有时才起一个。**任何人工操作都不得 `Stop-Process` / `terminate` / `taskkill`**。
- **K-6 TCL 必须以 `exit` 收尾**：`status_body()` 已带 `exit`（`board_check.py:243`）。不要手写 TCL 去掉它，
  否则 `cdt_cfg` 只能被杀，杀一次就可能掉一次下载器。
- **K-7 `--expect` 是 `nargs='*'`**：放在命令末尾；若想加 `--json`，让 `--json` 出现在 `--expect` **之前**。
- **K-8 串口独占**：Step 1~4 期间不要开着串口助手/另一个 `uart_capture`；`serial.Serial` 打开失败会返回 2。
- **K-9 别按 KEY1**：`sys_ctrl.v:308-311` 的 KEY1 会把 FSM 拉回 `ST_DDR` 重跑自检（`sys_run` 掉 0），
  上传权重期间误按会让 m1 仲裁行为不确定。

---

## 7. 发现的脚本/文档不一致与依赖问题（本预检的结论，供 T10/T13 复核）

| 编号 | 类型 | 事实（带出处） | 影响 | 建议归属 |
|---|---|---|---|---|
| **D-1** | **能力缺失（阻断 layers 阶段）** | 顶层 UART TX 只有一条复用通道：`weight_loader` 的 `K`/`WOK` + `uart_debug` 的 6 条状态行（`src/ctrl/instrec_top.v:806-817`、`uart_debug.v:86-91`）。**没有** design.md 9.2 的 6 字段帧（SOF `AA` + `layer_id` / `seq` / `len` / `payload` / `crc16`）导出器；`instrec_top.v:32,208` 明说 T-M2-07 的 observation taps 未消费、综合会剪掉。`npu_top.v` 也无帧导出端口。 | `uart_capture --frames` 只能拿到 0 帧 ⇒ `compare_layers` 必返回 1 ⇒ 逐层对拍**在当前位流上不可执行**（与是否有音频无关） | T10 之后的独立增强任务（新增 `layer_export` 模块，勿混入本轮） |
| **D-2** | **文档 token 错误** | `docs/STATUS.md:566` 的 `--expect ... "RUN"` 永不命中（见 K-1） | 照抄会得到退出码 5，被误判为 boot 失败 | 建议 T16/文档维护者删除 `RUN` |
| **D-3** | **默认参考是静音** | `scripts/outputs/golden/sine_440_full_feat.npy` 为 `int8` 全零；正解在 `reports/golden_ref/sine_440_full/feat.npy`（`uint8`） | 用默认路径生成的 golden 参考是静音模型，任何真实音频对拍必失败（见 K-3） | T11 用 `--golden-feat` 规避；长期建议重生成 `scripts/outputs/golden/` |
| **D-4** | **脚本 docstring 与 RTL 不一致** | `weight_upload.py:17` 声称失败行是 `WERR @<hex> want <x> got <y>`；RTL 实际只打 `WERR <8hex>\n`（`weight_loader.v:338-340,354`） | 只影响失败文案解读，不影响 `startswith('WOK')` 判定 | 低优先，文档修正 |
| **D-5** | **权重基址契约 vs RTL** | `layer_contract.json` 的 `ddr3_weight_base = 0x00100000`；`weight_loader.v:28` 的 `BASE_ADDR = 28'd0`，顶层例化未覆盖（`instrec_top.v:828-850`）；`wdma.v:261` 也从 0 起 | RTL 内部自洽（写读同址），**不影响 WOK**；但若按契约偏移做外部换算会错位 | T10/后续契约对齐 |
| **D-6** | **`sys_ctrl` 的 `ST_WEIGHT` 不可达** | `sys_ctrl.v:181` 定义了 `ST_WEIGHT` 且有 `weight_ok/weight_err` 处理（`:291-303`），但**没有任何 `state <= ST_WEIGHT` 转移**；顶层把 `weight_start` 接到 `weight_start_unused`（`instrec_top.v:771,776`） | 权重上传失败**不会**让板子进 `ST_SAFEERR`；`WOK` 完全由 `weight_loader` 自身的回读 digest 决定 ⇒ `WOK` 仍是有效判据，但"上传失败自动锁死"的保护不存在 | T10/后续（守门用 `WOK`，别等 SAFEERR） |
| **D-7** | **`board_e2e` 与 plan 参数不一致** | plan §3.1 T11 要求 `--seconds 20` + `--json`；`board_e2e.py` 硬编码 `8` 且不传 `--json` | 一键链路拿不到证据文件、窗口偏紧 | 用 Step 1 的 `board_check` 直跑 |

---

## 8. DEFERRED 项（无真实 I2S 输入时无法自动判定 —— 不得写成 PASS）

| 编号 | 项目 | 为什么不判定 | 可自动判定的替代证据 |
|---|---|---|---|
| **DEF-1** | `conv1/conv2/conv3/conv4/fc1/fc2_logits/probs` 逐层数值一致（exact / within-1LSB / `max_abs_delta`） | 需要①与 golden **同源**的 I2S 音频（板子只在窗口完成事件时产生帧）②RTL 侧 9.2 导出（当前缺失，D-1） | 离线：`pytest tests\test_compare_layers_selfcheck.py -q` ⇒ 4 passed，证明对拍工具本身正确（**证明工具，不证明板子**） |
| **DEF-2** | 端到端识别结果（类别 / 置信度 / top1 与 golden 一致） | 依赖 DEF-1 的 feat 链路 | 无（`npu_top` 的 probs 只进 UI，未上 UART） |
| **DEF-3** | HDMI 画面、概率条、频谱热图内容正确 | 需人眼/相机判读，属 T9 的 `ui_demo` 范围 | T9 的 `board_check --expect UIDEMO` + `pix_clk` WNS |
| **DEF-4** | 连续音频长跑稳定性（丢帧、FIFO 溢出） | `sys_ctrl.v:331-337` 的 `overflow_warn` 只进 LED[5]，不在 UART 文本里 | 若要量化需新增导出（同上 D-1） |
| **DEF-5** | 真实权重 → 真实音频的识别准确率 | 与 DEF-1 同因 | 无 |

**无真实音频时仍可 100% 自动判定的项目**（这些可作为 T11 的 PASS 集合）：
1. `INSTREC BOOT` / `DDR3 SELFTEST` / `DDROK` 三行文本（Step 1，退出码 0）；
2. `program_ok=True`、`status_raw` 的 `done=1`、`crc_err=0`；
3. `WOK <8hex>`（权重整镜像写 + 回读折叠一致）；
4. `--json` 的 12 键证据记录（含 `expect_missing=[]`、`verdict=PASS`）；
5. `cdt_js` PID 集合运行前后不变（仍为单实例）；
6. `--sbit` sha256 == `json.BitstreamSha256`。

---

## 9. T11 证据归档清单（跑完后照此收口）

| 产物 | 路径 | 来源 |
|---|---|---|
| 板级 12 键证据 | `reports/board_e2e_$ts.json` | Step 1 `--json` |
| 原始串口字节 | `build/uart_last.bin`（+ Step 0.3 的备份副本） | `board_check.py:425` |
| WOK 原文 | `reports/e2e_conclusion.md` 内引用 `board reply:` 行 | Step 2 stdout |
| 逐层抓取（若执行） | `reports/layers_<stem>/layer_XX.npy` | Step 4 |
| 结论 | `reports/e2e_conclusion.md` | 需含：位流 SHA、`done`/`crc_err`、三行启动文本原文、`WOK` 原文、逐层结果表**或 DEFERRED 证据**、`cdt_js` PID 前后对比、未完成项与责任任务 |

> 纪律提醒：`reports/*.md` 中的 `DEFERRED` 必须与 `PASS` 分开列，禁止把"没跑"写成"通过"；
> 任务约定 `instrec_fpga/` 之外零改动，且不提交 `build/`、`reports/*.log`。