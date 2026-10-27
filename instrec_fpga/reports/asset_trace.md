# InstRec-FPGA 资产溯源清单（asset_trace.md）
| 日期 | 2026-10-26 |
| 复制人 | team-leader（T-GP-01 文件操作部分） |

## 一、DDR3 IP（整目录复制）
| 项 | 内容 |
| ---- | ---- |
| 源路径 | pds_cpu_100h/ipcore/ddr3_test |
| 目标路径 | instrec_fpga/ipcore/ddr3_test |
| 源 sha256 | 3c5441b4bff33dff73811c3a025ede3b6348cb5779e21778653659b6cbfb84e0 (ddr3_test.v) |
| 目标 sha256 | 3c5441b4bff33dff73811c3a025ede3b6348cb5779e21778653659b6cbfb84e0 (ddr3_test.v) |

## 二、HDMI demo 5 文件（逐文件复制）
| 文件 | 源 sha256 | 目标 sha256 | 一致 |
| ---- | ---- | ---- | ---- |
| sync_vg.v | 062ea3ec1c4479ce7ddc28314030228e81baab4fef2a96cbfc1827668292c21e | 062ea3ec1c4479ce7ddc28314030228e81baab4fef2a96cbfc1827668292c21e | YES |
| iic_dri.v | 5f60bc8bcac110f0125a278c332065d2594874c465ec961c603662f92c16b13e | 5f60bc8bcac110f0125a278c332065d2594874c465ec961c603662f92c16b13e | YES |
| ms7200_ctl.v | 501521c4cceecd48de5741d3116eb7062c93a70a606a386682e1d8756a494199 | 501521c4cceecd48de5741d3116eb7062c93a70a606a386682e1d8756a494199 | YES |
| ms7210_ctl.v | c9b101e58f381ddf3c6d663d0003c18065302659424b8345022161413ccf09ae | c9b101e58f381ddf3c6d663d0003c18065302659424b8345022161413ccf09ae | YES |
| ms72xx_ctl.v | f55ca26277656da30dc8c1fc7ae83881626d37bd0e5385fbf73f5d04b60f1e03 | f55ca26277656da30dc8c1fc7ae83881626d37bd0e5385fbf73f5d04b60f1e03 | YES |

源路径：D:/0000/111/001/Pango/docs/盘古100Pro+开发板（MES2L676-100HP）配套资料/7_FMC扩展子卡/2_Demo/da_ad_HDMI/ad9280_ad9708_HDMI/source/

## 三、约束与脚本
| 文件 | 源 | 目标 | 源 sha256 | 目标 sha256 | 一致 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| constraints/ddr3_100h.fdc | pds_cpu_100h/constraints/ddr3_100h.fdc | instrec_fpga/constraints/ddr3_100h.fdc | 00d9761dbb4f8f3e37fb1f784aa5b6a5534dc1988c12977766262a2a6e8af495 | 00d9761dbb4f8f3e37fb1f784aa5b6a5534dc1988c12977766262a2a6e8af495 | YES |
| scripts/gen_ddr3_fdc.py | pds_cpu_100h/scripts/gen_ddr3_fdc.py | instrec_fpga/scripts/gen_ddr3_fdc.py | 465a0203acd740612cb37ed54f75095442f81d84e2c9216254c41b01de66939f | 465a0203acd740612cb37ed54f75095442f81d84e2c9216254c41b01de66939f | YES |

## 四、HDMI PLL IP（整目录复制，T-M0-07）
| 项 | 内容 |
| ---- | ---- |
| 源路径 | docs/盘古100Pro+开发板（MES2L676-100HP）配套资料/7_FMC扩展子卡/2_Demo/da_ad_HDMI/ad9280_ad9708_HDMI/ipcore/pll |
| 目标路径 | instrec_fpga/ipcore/pll |
| 功能 | GPLL_B（GTP_GPLL 原语 wrapper）：clkin1=27MHz → clkout0=148.5MHz (pix_clk) + clkout1=10MHz (cfg_clk) + lock |
| 复制人 | RTL 工程师（冯工，T-M0-07） |
| 引用方式 | hdmi_tx_if.v 直接例化 wrapper 模块 `pll`（demo hdmi_test.v 原样接线）；构建脚本需 `add_design ipcore/pll/pll.idf`（待 T-GP-01 build_full.tcl 补充） |

| 文件 | 源 sha256 | 目标 sha256 | 一致 |
| ---- | ---- | ---- | ---- |
| pll.v | e70c5d8615ad252fbf85fba6fc77d1433ebb424d0480595b26f0fe38c3ac6add | e70c5d8615ad252fbf85fba6fc77d1433ebb424d0480595b26f0fe38c3ac6add | YES |
| pll.idf | 6a0ffb23b6a838d5e8c1f38d595d4934df37bc305f0e521449fb25727652ff84 | 6a0ffb23b6a838d5e8c1f38d595d4934df37bc305f0e521449fb25727652ff84 | YES |
| pll_tb.v | 2815ac3cdf5278f30b0218e8b14764356015dc3fcb841389e33b83300f5c27e4 | 2815ac3cdf5278f30b0218e8b14764356015dc3fcb841389e33b83300f5c27e4 | YES |
| pll_tmpl.v | 52f511802a9ae48878aaaf563338855d8191070c6a3f2bad091451ab432587f2 | 52f511802a9ae48878aaaf563338855d8191070c6a3f2bad091451ab432587f2 | YES |
| pll_tmpl.vhdl | a826268fc21d744868b86839f4cfd1f7026a134a548254d9a8523b92d73f7f71 | a826268fc21d744868b86839f4cfd1f7026a134a548254d9a8523b92d73f7f71 | YES |
| .last_generated | 1c43d3a8ce08cb98c936f37b3a9dbd0a470654c612f78796809b5e6fb2e8dd7d | 1c43d3a8ce08cb98c936f37b3a9dbd0a470654c612f78796809b5e6fb2e8dd7d | YES |
| .settings | 18fb2deef6122d090455149a362445e24f09478da2ccfe5cebb4011392bbbf72 | 18fb2deef6122d090455149a362445e24f09478da2ccfe5cebb4011392bbbf72 | YES |
| generate.log | 121a45cd9842e6c11539e25ae7201f1a991fb65d05d42d48ccba9ded1d6b72c8 | 121a45cd9842e6c11539e25ae7201f1a991fb65d05d42d48ccba9ded1d6b72c8 | YES |

## 五、新写 wrapper（非复制资产，T-M0-04）
| 项 | 内容 |
| ---- | ---- |
| 文件 | instrec_fpga/src/ddr3/ddr3_wrapper.v |
| 性质 | 新写（IP 例化壳，非复制文件） |
| 作者 | 构建工程师（孙工，T-M0-04） |
| 参考来源 | cpu/fpga/rv32_ddr3_ip_wrapper.sv（pds_cpu_100h 已验证形态：GTP_INBUFDS 差分转单端、ips2l_rst_sync_v1_3 复位同步、APB 常量绑定、dbg 默认值） |
| IP 端口依据 | instrec_fpga/ipcore/ddr3_test/ddr3_test.v 实际端口表（MEM_ROW_WIDTH=15 / MEM_BANK_WIDTH=3 / MEM_DQ_WIDTH=32 / MEM_DM_WIDTH=4 / MEM_DQS_WIDTH=4，CTRL_ADDR_WIDTH=28） |
| 实例名 | I_ips_ddr_top（硬性保持，fdc generated-clock 路径前缀 ddr3_wrapper.I_ips_ddr_top.*） |
| 与参考差异 | ① 未消费的 IP 输出端口在 port map 中整体省略（rv32 用 `.port()` 空连接写法，本项目 check_rtl.py 将空连接列为 SV-2012 违例）；② ddrphy_cpd_lock 从留空改为引出（design.md 自检链消费）；③ 不含 rv32 中被综合剪除的 phy_rst_cnt 死代码（dbg_ddrphy_rst_n 直接接 demo 默认常 1） |
| 核验 | gen_ddr3_fdc.py 重生成 constraints/ddr3_100h.fdc 逐位一致（sha256 00d9761d…，507 行 IO 属性 = 73 针）；wrapper 端口与 fdc 17 总线名三方交叉核对全覆盖；含 wrapper+idf 的 PDS 六阶段构建通过（20261026-225759-e089fdd3） |

## 六、派生 IP 核（pll_audio，T-M0-09 任务三）
| 项 | 内容 |
| ---- | ---- |
| 源资产 | ipcore/pll/pll.v（第四节登记的 HDMI demo GPLL，T-M0-07） |
| 目标路径 | instrec_fpga/ipcore/pll_audio/ |
| 派生方式 | 文本派生（复制整目录后改 module 名 + 频率参数；本地无 IP Compiler GUI 自动化，综合实际编译 .v 的 localparam，idf 为 IP 工程记录同步改） |
| 派生人 | 集成工程师（沈工，T-M0-09） |
| 频率方案 | fVCO = CLKIN × RATIOM × RATIOF / RATIOI = 27 × 2 × 16.0 / 1 = 864 MHz；clkout0 = 864 / 4.0 = 216 MHz（精确整数 8:1）。公式用 demo 核自身数字验证：27×2×19.25 = 1039.5，/7 = 148.5、/100 = 10.39 与 idf REQ_FREQ 字段吻合 |
| 参数 diff | module pll→pll_audio；STATIC_RATIO0 7.0→4.0；STATIC_RATIOF 19.25→16.0；STATIC_DUTY0 7→4；STATIC_DUTYF 19→16（DUTYx==RATIOx 规律对应 50% 占空比）；其余参数含内部 GTP_GPLL 实例名 u_gpll 原样保持（fdc generated-clock 路径 u_audio_pll/u_pll_audio/u_gpll/CLKOUT0 硬依赖） |
| idf 同步 | instance pll→pll_audio、CLKOUT0_REQ_FREQ 148.5→216.0、CLKOUT1_REQ_FREQ 10.39→8.64、STATIC_RATIO0 7.0→4.0、STATIC_DUTY0 7→4、file_list 文件名 pll_*→pll_audio_*；advancedPage 档位值（UI 状态非物理参数）保持原样 |
| 降级 | 未触发（40 分钟决策点内完成）；clkout1（8.64 MHz）为 audio_pll 未用输出，悬空合法 |
| 核验 | 20261026-235807-84386179 六阶段构建通过（pll_audio 时序 clk_nco 同域 WNS +1.526） |

| 文件 | 源（ipcore/pll/） sha256 | 派生（ipcore/pll_audio/） sha256 |
| ---- | ---- | ---- |
| wrapper .v | e70c5d8615ad252fbf85fba6fc77d1433ebb424d0480595b26f0fe38c3ac6add (pll.v) | 68a1951e0d473a16454ea8c20b99dec5276e438f7faa473fc1749d5f434c103b (pll_audio.v) |
| .idf | 6a0ffb23b6a838d5e8c1f38d595d4934df37bc305f0e521449fb25727652ff84 (pll.idf) | ca9ed620b83000aaf05c416ddb175f84875f1af5f16090b7afa9f83c4fe3cbc6 (pll_audio.idf) |
| testbench | 2815ac3cdf5278f30b0218e8b14764356015dc3fcb841389e33b83300f5c27e4 (pll_tb.v) | 91534581110e5a4813537ccf7ed2e2633e6481d8b9b57ce77dbb8e6403dab3da (pll_audio_tb.v) |
| 模板 | 52f511802a9ae48878aaaf563338855d8191070c6a3f2bad091451ab432587f2 (pll_tmpl.v) | 4e751d77cdf4810ecc11a5a22bc8c9f6139bd36e851ff4ca7d70b19055b9a0af (pll_audio_tmpl.v) |

（派生文件与源 sha256 不同为预期结果——参数已改；两列并存供审计回溯。pll_audio_tmpl.vhdl、.last_generated、generate.log 同目录顺带复制，内容未改。）

## 六B、新写约束：clock_groups_async.fdc（T-M0-09 构建侧）
| 项 | 内容 |
| ---- | ---- |
| 文件 | instrec_fpga/constraints/clock_groups_async.fdc（sha256 503ca238…） |
| 性质 | 新写约束（构建工程师孙工） |
| 目的 | 跨域异步组：{clk_nco}/{pix_clk}/{cfg_clk} 与 DDR3 家族（ref_clk/rst_clk/ddrphy_sysclk/phy_dq_*）互斥声明；同时声明 cfg_clk 的显式 create_generated_clock 放 instrec_top.fdc（×77/÷200）以替代不可引用的层级推断时钟名 |
| 硬依赖 | 必须在 ddr3_100h.fdc 之后 add_constraint——PDS 逐条执行约束，组内引用未创建时钟触发 SDC-2027 整条忽略（本构建实测教训，修复前 clk_nco→ddrphy_sysclk 报 WNS -7.149 假违例） |
| 核验 | 20261027-000612-a71f1451 构建：SDC-2027=0、Setup 表仅剩同域行、Design Summary All Constraints Met |

## 七、溯源约定
- 既有工程 cpu/、pds_cpu_100h/、docs/ 等目录零改动（REQ-BLD-004）；
- 后续新增复用资产须追加登记于此。
