# DDR3 访问契约与集成验证（2026-11-11）

> 本文是 DDR3 命令地址单位、突发几何、四主口生产路径一致性的**统一契约**，
> 并附故障账本。它是离线核实（读 RTL + 行为模型对拍）的产物，板上位流
> `69041235…`（`build/pds/20261111-003237-53a02f27`）为唯一实测基准。

## 1. 结论先行

1. **命令地址单位是 `physical = 4 × cmd_addr`**（IP 把 `cmd.addr` 当 32-bit
   字地址）。每拍 **32 B**（256 bit），**突发内每拍物理 +32 B（连续）**。
2. **单拍稀疏写与连续突发读在 ×4 下不匹配**，这是功能缺陷，不是"空间浪费"。
   只有恢复字节语义（`physical = cmd_addr`）两条路径才逐字节一致。
3. 最小修复 = `ddr3_ctrl_axi.v` 输出地址前 `>>2`（第 218 / 232 行的
   `axi_awaddr` / `axi_araddr`），一处改动、需集中重建 + 全回归。
4. 主机 diag 读回可用 `destride` 在 ×4 下恢复全部页（已固化进
   `scripts/read_ddr.py` + `scripts/ddr3_layout.py`）；**片上** mel 读 / wdma
   读做不到，必须等修复。

## 2. 地址契约（实测）

| 项 | 值 |
|---|---|
| 命令地址单位 | `physical = ADDR_UNIT × cmd_addr`，**ADDR_UNIT = 4**（实测） |
| 每拍字节数 | 32 B（256-bit AXI 数据宽度） |
| 突发内部递增 | 每拍物理 +32 B，**连续** |
| 命令长度 | `len = beats − 1`（生产突发 len=15 → 16 拍 = 512 B；len=7 → 8 拍 = 256 B；len=0 → 1 拍 = 32 B） |
| 页 | 32 B（16 × int16 PCM 样本，或 16 × 16-bit 特征槽） |
| 256 B diag 帧 | 8 拍，覆盖 `[4A, 4A+256)` 物理 → ×4 下**只含 2 页**（含 3 页宽的 gap） |

决定性证据（`build/probe_addr_unit.py`）：`read(32)[0:128]==read(0)[128:256]`、
`read(64)[0:128]==read(32)[128:256]` 各 **128/128 全等**，唯一自洽解
`payload[j]=physical[4A+j]`（地址 ×4、拍长仍 32 B）。

## 3. 四主口生产路径命令几何（RTL 逐条核对）

| 通路 | 主口 | 命令几何 | 地址生成 |
|---|---|---|---|
| audio 写（左） | m0 | **单拍写** len=0，32 B/命令，页步长 32 B | `addr = 0x000000 + (win_id[0]?0x42000:0) + (page_no<<5)` |
| audio 写（右） | m0 | 单拍写 len=0 | `addr = 0x84000 + (page_no<<5)`（归档镜像，不参与推理） |
| mel PCM 读 | m2 | **16 拍读** len=15，512 B/命令，命令步长 512 B，共 516 命令 | `addr = win_base + (cmd_cnt<<9)`，`win_base = win_id[0]?0x42000:0` |
| mel 谱导出 | m2 | 单拍写 len=0，32 B/命令，1032 命令 | `addr = 0x200000 + (elem<<1)`（16-bit × 16512 槽） |
| 权重上传 | m0? | **8 拍写** len=7，256 B/命令，命令步长 256 B | `addr = 0x100000 + (seq<<8)` |
| NPU 权重读（wdma） | m1 | **16 拍读** len=15，512 B/命令，地址 +32 B/拍 | `cfg_addr` 每拍 +32 B |
| diag 读回 | m3 | 8 拍读 len=7，256 B/命令，命令步长 256 B | `addr = arg + (frame_idx<<8)` |

## 4. 单拍稀疏写 vs 连续突发读：不匹配（核心缺陷）

在 `physical = 4×cmd_addr` 下，单拍写把页 p 落在物理 `128p`，而 16 拍突发读
把命令 k 的 16 拍连续覆盖物理 `[2048k, 2048k+512)`。两者对齐条件
`2048k+32j = 128p` 仅当 `j≡0 (mod 4)` 成立：

- **mel 读**：每 16 拍命令只有第 0 拍对齐到真实页，其余 15 拍读到 128 B 物理
  gap（DDR 上电残留）。位置正确的样本恰好是每 256 样本块的前 16 个
  （= 8256 / 132096 = 1/16）。**75% 数据丢失 + 位置错乱**。
- **wdma 读**：权重帧写入物理 `[1024f, 1024f+256)`，帧间 768 B gap；16 拍读
  连续覆盖 512 B，每命令一半是 gap。**权重流被 gap 污染**。

行为模型已锁死该结论（`tests/test_ddr3_contract_consistency.py`）：
`addr_unit=4` 下 mel 读与原始样本**不等**，且位置正确样本 == 每命令前 16 个；
`addr_unit=1` 下**逐字节相等**。

> 注意：这条结论**推翻**了 STATUS 早前"×4 只是空间浪费、片上流水线读到的
> 正是 audio 写下的数据"的说法——那句只对"起始地址共享同一约定"成立，对
> "稀疏写 vs 突发读的对齐"不成立。这正是本次收敛要抓的根因。

## 5. 修复方案（暂不实施，待集中构建）

`instrec_fpga/src/ddr3/ddr3_ctrl_axi.v`：

```verilog
assign axi_awaddr = cur_addr[27:2];   // 原 = cur_addr;  恢复字节语义
assign axi_araddr = cur_addr[27:2];   // 原 = cur_addr;
```

改动后 `physical = cmd_addr`，四主口全部对齐；mel 读 / wdma 读恢复逐字节正确。
需：重建位流 + `check_rtl.py` + `pytest` + 上板全回归（自检 → 重复长读 →
同窗 PCM/feat/logits 对拍）。

## 6. 主机读回契约（×4 下可行，已固化）

`scripts/ddr3_layout.py`（唯一真源）+ `scripts/read_ddr.py`（正式读回）：

- `frame_plan(addr, npages, unit)`：×4 下每帧 2 页，命令地址步长 64 B；
  spans = `[(0,32),(128,32)]`。
- `destride(frames, plan)`：按 spans 重组，得到页序字节流。
- PCM：单声道 `int16`、132096 样本、264192 B；窗基址
  `pcm_win_base(win)=0x0 或 0x42000`（ping-pong）。
- feat/谱：`0x200000`，16512 × 16-bit 槽 = 33024 B；低字节是 uint8 特征
  （`zp_in=49`），高字节 0x00；`read_feat` 读 33024 B 后取 `raw[0::2]`。
- 同一锁定窗口重复读回必须 sha256 全同（测试已锁）。

## 7. 故障账本（三本，互不合并）

| # | 故障 | 根因 | 证据 | 修复 | 待验证 |
|---|---|---|---|---|---|
| 1 | 启动自检 `@0x00300200` 失败 | `instrec_top.v` m3 `rd_ready` 被 `st_m3_sel` 门控，自检读阶段末拍陈旧被当首拍 | `tb_ddr3_m3_share` 精确复现 `fail_addr=0x300200,to_err=0` | 1 行 `!st_done` 门控，S1 全过 | 板上重验自检 |
| 2 | UART 长读随机停帧 | 传输层（周期遥测插帧 + 主机流水线 + `S_ACK` 吞字节），**非** DDR 超时 | 连续 3 次读 264192 B `holes=0`、sha256 全同 | 重写读回协议 | 已闭环 |
| 3 | 地址 ×4 混叠 | IP 字地址解释（`physical=4×cmd_addr`） | probe 重叠 128/128 全等 | 见 §5（`>>2`）| 集中构建后全回归 |

**已撤销、不得再作为改 RTL 依据**：
- "PCM 静默丢页 / 每 4 页只有 1 页有音频" —— 实为 ×4 主机读回混叠假象。
- "单拍写不被 DDR3 IP 可靠提交" —— 实为 ×4 混叠，写路径本身无丢页。

## 8. 生产路径一致性测试清单

`tests/test_ddr3_layout.py`、`tests/test_ddr3_contract_consistency.py`、
`tests/test_read_ddr.py`（共 20 用例）：

- ×4 / 字节两种语义下 frame_plan + destride 全窗往返。
- audio 写→mel 读：×4 不等、字节语义逐字节相等；位置正确样本精确断言。
- 权重上传→wdma 读：×4 不等、字节语义相等。
- feat 导出→diag 读：两种语义下 destride 恢复全部 16512 特征字节。
- 同一锁定窗口重复读回字节全同（sha256 等价）。
- 跨页 / 跨突发 / 跨窗口单调 ramp 不丢不乱序（字节语义）。
- **超时≠成功**：`done` 仍会发但 `to_abort=1、read_cmpl=0`，上层必须看
  `to_abort`/`to_err`，不能只看 `done`。

## 9. 上板验收顺序（离线全绿后执行）

1. 自检（st_fail=0）。
2. 重复长读同窗 PCM，sha256 全同。
3. 同窗 PCM / feat / logits 与 `golden_pipeline.py` 参考逐级对拍，定位首个
   偏差环节后才允许改功能。
4. 若判定需改 RTL（§5 `>>2`），集中构建一次，不复用旧位流。
