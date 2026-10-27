# REQ-MEM-003 DDR3 IP 契约适配 checklist（T-M0-05 归档）

| 日期 | 2026-10-26 |
| ---- | ---- |
| 归档人 | 构建工程师（孙工） |
| 模块 | src/ddr3/ddr3_ctrl_axi.v + src/ddr3/ddr3_arbiter.v |
| IP 端口依据 | ipcore/ddr3_test/ddr3_test.v 实测端口表（F-07） |

## 一、IP 特例硬性规则落实

| # | REQ-MEM-003 规则 | RTL 落点 | Python 模型对拍 |
| ---- | ---- | ---- | ---- |
| 1 | 写完成以 axi_wready 握手判定（IP 无 axi_wvalid） | S_W 状态 `axi_wready && beat_cnt==cur_len` 判完成（write_cmpl），无 wvalid 输出 | `test_read_fifo_routing_lossless`（wr_beats 守恒） |
| 2 | axi_wusero_last 作旁证（非阻塞） | S_WLAST 4 周期观察窗，miss 计数导出 `wlast_miss_cnt[7:0]` | `test_wlast_side_evidence_window_is_sufficient`（0 miss） |
| 3 | 读前同地址 dummy-write（1 beat，wstrb 全 0 屏蔽） | S_DW_AW→S_DW_W：len=0、wstrb=32'h0、wdata=0，与真读同 addr | `test_dummy_write_precedes_every_read`（每读必有同址 masked dummy） |
| 4 | rvalid 期间逐周期收数（IP 无 axi_rready） | S_R 每周期 push 16×256bit 弹性 FIFO（深度=最大突发 16） | 模型内置 assert（FIFO 溢出即失败）+ beat 守恒断言 |
| 5 | 反压只存在于仲裁器内部 | FIFO 非空不接受新读命令（arb_en 条件），上游经 m{i}_rd_ready 弹性消化 | `test_read_fifo_routing_lossless` |
| 6 | axi_awuser_ap=1、awuser_id/aruser_id 固定主设备号 | 参数 AXI_USER_AP=1（默认），id={2'b00,cur_master} 0..3 | —（RTL 常量） |
| 7 | 全部长突发 len=15、32B 对齐 | 约定不做硬件强制（len≤15 合法性入 addr_err 检查），dummy 内部固定 len=0 | 生成器全 len=15 + `test_arbiter_flags_region_violations` |
| 8 | 每主 32bit wait_cnt 导出（REQ-MEM-004） | arbiter wait_cnt_0..3；命令执行期间对在飞主 valid 屏蔽，计数=纯排队时间 | `test_design_rate_wait_budget`（等待 ≤ 活跃 10%） |

## 二、地址映射（design.md §5.1 / REQ-RSC-006）

| 区域 | 基址..尾址 | 仲裁器区域检查 |
| ---- | ---- | ---- |
| PCM 左环形 | 0x000000..0x083FFF | ✓ region_pcm_l |
| PCM 右存档 | 0x084000..0x0C5FFF | ✓ region_pcm_r |
| 权重镜像 | 0x100000..0x1B7FFF | ✓ region_wgt |
| 谱导出快照 | 0x200000..0x20FFFF | ✓ region_spec |
| 自检图案 | 0x300000..0x30FFFF | ✓ region_self |
| 32B 对齐 + len≤15 | — | ✓ addr_aligned / len_legal，违例锁存 addr_err[主] sticky |

## 三、板级自检验证项（并入 T-M0-10）

1. **dummy-write 路径**：自检图案区写→读回比对（REQ-MEM-005 用例），读命令前 dummy-write 正确性间接由数据回读正确性证明；
2. **wlast_miss_cnt==0**：UART 导出核对（写响应旁证无失配）；
3. **wait_cnt 观察**：长稳运行 60s 各主 wait_cnt ≤ 预算 10%（REQ-MEM-004）；
4. **to_err/cmd_to_err==0**：无 AXI 握手超时。

## 四、与已验证参考（pds_cpu_100h rv32_burst_ddr3）的差异登记

| 项 | rv32（已上板） | 本设计 | 回退参数 |
| ---- | ---- | ---- | ---- |
| awuser/aruser ap 位 | 0（官方 demo 值） | 1（design.md §2.2.5） | AXI_USER_AP |
| dummy-write strobe | 全 1（写 0，会碰数据） | 全 0（纯屏蔽，不碰数据） | DUMMY_WSTRB_ALL1 |

若 T-M0-10 板级读写异常，优先切换上述两个参数复测（一行参数改动，无需重构）。

## 五、构建核验

- check_rtl.py：16 文件 0 违例（含 ddr3_ctrl_axi.v / ddr3_arbiter.v）
- PDS 六阶段全 OK（20261026-232501-11307c74，两新模块 rtl_analyze 干净、无 E/W）
- pytest tests/test_ddr3_arbiter_model.py：9 passed