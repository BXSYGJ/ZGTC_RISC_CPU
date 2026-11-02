# 双任务交接：Flash固化与五类主奏乐器识别

交接日期：2026-11-02（Asia/Shanghai）。本文是两项工作的执行入口；后续实时状态只以 [STATUS.md](STATUS.md) 顶部最新记录为准，历史条目的“待反馈/进行中”不可当作当前状态。

## 1. 目标与当前结论

| 工作 | 用户目标 | 当前完成程度 | 下一项可执行工作 |
|---|---|---|---|
| 位流与权重固化 | 断电重启后无需电脑烧录、无需串口重传模型即可启动 | 已完成可行性评估；未扫描、擦写Flash，未实现自动加载 | 核对实际Flash/配置模式与工具流程；备份原内容后验证位流冷启动，再验证用户模式Flash小块读取 |
| 五类主奏识别 | 以主导组为主要结果，同时显示五组独立活跃度 | 已冻结float模型、验证资产与双头参考输出，完成复用/CPU分工评估；未完成INT8迁移 | 训练split校准、BN折叠、建立双头INT8数值契约，并在独立验证split评估 |

两项均为当前目标，但不能一次改模型、启动介质、CPU协议再直接上板。先分别验证数值与启动链路，最后集成。没有新的明确优先级时，五类离线数值工作可先推进；Flash原语/工具资料核对可并行开展。本文不代表任一新功能已实现。

## 2. 必须保留的八类基线

- 当前最后一次经用户确认的完整系统位流：`2673246E`，中文仪表盘“正常且稳定”；CPU启动、MMIO/ISA、DDR自检、691040B/2700帧权重上传、WOK `FA0D5236`、12秒六轮NPU完成及CPU回读有证据。不是本轮重新读取的板上状态。
- 位流：`build/pds/20261102-211104-aedccc03/generate_bitstream/instrec_top.sbit`，SHA256 `2673246ECAC0ECB3E00721C53EFD6B941CC0E8CA44022064AE36C21941D89318`。板级报告：[board_dashboard_20261102_2155.json](../reports/board_dashboard_20261102_2155.json)。
- 时序仍FAIL：pix setup −2.708ns/32端点，core setup −1.267ns/1393端点，slow/fast hold −0.011/−0.009ns各1端点。实屏正常不等于静态时序或长期稳定性通过。
- 后续三个分拍修复已提交：glyph `71f8810f`、DDR自检 `7d097105`、NPU replay `3ea8f787`。这些不在上述板上位流内。真实CPU/native不同A/B、无reset两轮golden通过，每轮31141255 cycles。
- 修复源资源门控 `build/pds/20261102-224004-e25e4ce6` 已正常结束：33640 LUT、35394 FF、153.5/155 DRM、90 APM，SourcesUnchanged=true；只到dev_map，未运行PNR，无新时序、无新位流。不要重复轮询旧PID或把未执行后续阶段误报为布线失败。
- 已验收显示fallback `602AB321` 必须保留；见STATUS中的路径与完整hash。不因开发新功能覆盖八类权重、契约、基线报告或失败证据。
- 外部I2S音源尚未接；内部推理完成或静默输入不构成识别准确率验收。

## 3. 工作一：位流与权重Flash固化

详细依据：[FLASH_BOOT_FEASIBILITY_20261102.md](FLASH_BOOT_FEASIBILITY_20261102.md)、[flash_boot_feasibility_20261102.json](../reports/flash_boot_feasibility_20261102.json)。评估提交 `81bb0c37`。

### 硬件事实与关键风险

100Pro配套核心板原理图第3页标注U15/SPI0与U9/SPI1，两颗均128Mbit（16MiB），型号标注W25Q128JVEIQ/XT25BF128FSSIGU-W；实际焊接及JEDEC ID未核。图中配置模式001/MSPI，两颗共享SPI_CLK到专用CFG_CLK H13。当前位流3791112B、八类权重691040B，容量不是主要障碍；先使用板载Flash，不先购买器件或改PCB。

历史`cpu/`软SPI普通IO无法驱动H13，其flash约束为占位，不能搬用。PDS有`GTP_CFGCLK`原语（CLKIN、CE_N）及Logos2映射文件，但尚未证明PG2L100H用户模式实际可用；需核对官方语义、配置脚释放/保留选项、CS和数据脚。不可把H13强约束成普通输出，也不可用库文件存在宣称硬件读通。

### 实施步骤

1. 先确认实际Flash、启动模式、工具支持与镜像布局；保存原Flash内容及hash，明确可写范围。使用PDS支持的配置镜像/OuterFlash流程，不将`.sbit`与权重直接拼接盲写。已有流程资料尚不代表本板Flash烧写已验收。
2. 单独完成位流固化与真正断电冷启动。CPU的`prog.hex`、字体、系数ROM已进入位流，不需要另做CPU程序Flash启动。此时权重仍允许UART加载，先隔离验证配置启动。
3. 最小用户模式只读探针：JEDEC ID、小块固定地址、多次一致性。未证明该通路前不开发大规模加载器；失败则核对厂商接口，或重新评估已核验GPIO上的外接3.3V SPI方案。
4. 规划配置与模型分区及扇区边界；模型头包含magic、版本、模型ID、长度、量化契约标识、CRC32。第二颗或第一颗独立分区的选择，以实际读通及工具占用范围为准。
5. 小硬件SPI读取器经有限缓冲流式搬运Flash→DDR，复用现有loader的DDR写/读回、master1仲裁和weight_ok门控。当前UART loader只有rx_valid/rx_data，没有ready，不能直接接连续快速SPI字节流；必须补充节流/缓冲契约。WOK折叠摘要不能充当CRC32或模型身份校验。
6. CPU监督阶段、超时、有限重试与错误显示；失败保持NPU禁止并保留UART恢复。首版由外部工具写Flash，运行时擦写和A/B掉电安全更新留作后续任务。

目标启动链：Flash配置FPGA → CPU/PLL/HDMI启动 → DDR自检 → 权重读入DDR并核验 → weight_ok → 完整音频窗口 → CPU请求/NPU推理/显示。权重仍在DDR使用，不改变NPU主读取路径，也不把整份模型塞入8KiB CPU RAM或几乎用满的DRM。

### 验收与工作量

- 真正断电重上电，电脑不参与配置或权重上传；保留DONE、CPU、DDR、模型身份、加载完成、推理与HDMI证据。
- 覆盖CRC损坏、长度错误、版本/契约不匹配、无有效模型、UART恢复；错误镜像不得启动推理。
- 位流固化低至中难，工具/芯片正常时约0.5～1工作日；权重自动加载中至高难，用户读通路证实后额外约1～3工作日。专用配置接口受阻时重新估时，不能承诺当天。
- 原SDD将Flash列为范围外，正式实现时同步扩展规格/设计/任务与DoD。

## 4. 工作二：五类主奏识别＋五组活跃度

详细依据：[GROUP5_REUSE_AND_CPU_ASSESSMENT_20261102.md](GROUP5_REUSE_AND_CPU_ASSESSMENT_20261102.md)、[GROUP5_MIGRATION.md](GROUP5_MIGRATION.md)、[group5_reuse_assessment_20261102.json](../reports/group5_reuse_assessment_20261102.json)。评估 `fb641ad4`，门控交接 `f3802832`。旧“五组暂缓”决定已被用户恢复迁移的明确要求取代。

### 产品和数学语义不得改写

固定顺序：`strings / woodwinds / brass / percussion / keys`，对应弦乐、木管、铜管、打击乐、键盘/拨弦。

- activity头：五个独立sigmoid，允许多组同时活跃，不要求总和为1。
- dominance头：独立FC头做softmax，再用`activity > 0.5`掩码并归一化。没有活跃组时全部为0，显示无主导结果，不强选。
- 主界面突出主导组，同时显示五组活跃度；不能以activity argmax替代独立dominance头。

### 已有资产与校准输入

- 冻结资产目录：`models/group5_v3_float_20261102/`，epoch22 `DualHeadInstrumentCNN`；checkpoint SHA256 `5ada8db602427af8b5c7ba01aa581f5852ebf2b884d94932c821fe44cf22b636`。
- 全资产hash和严格float重载已核，5个参考样本双头logits逐值一致。这不是INT8或留出精度验收，不能仅用5样本校准。
- 只读训练缓存：`D:/0000/111/001/Pango/InstRec/data/group5_cache_v3/`；all_features为(44091,64,130) float32，labels/dominance均(44091,5)，dominance_mask及metadata齐全；split.json含train_indices=35185、val_indices=8906。训练split用于校准，验证split独立评估；新结果落在instrec_fpga内，不修改兄弟训练目录。
- 打击乐训练正例仅157，需单列该类和混合/弱主导/无活跃表现。activity subset accuracy或dominance MAE不能冒称主导组分类准确率。

### 可复用与必须修改的部分

| 部分 | 复用与修改 |
|---|---|
| 音频/FFT/Mel核心 | 复用44100Hz、FFT2048、hop512、Hann、Mel64、top_db80框架；窗口改66150样本，归一统计、边界与输入量化重新对拍 |
| conv/pool/DDR/replay | 通道1→48→96→192→256及3×3计算器可复用；130帧几何、计数、地址、缓存深度、重放版图必须重核 |
| GAP | 新末层4×8，32点，round-half-even移位5；旧64点移位6不能照用 |
| FC | 共享256维GAP向量，串行执行两套256→128→5，复用FC引擎，新增调度和权重地址 |
| CPU/MMIO | 复用RV32I与ROM/RAM/UART；新增同帧10logits完整快照、frame ID、valid/完成状态、ACK及UI原子提交 |
| HDMI/UI/测试框架 | 复用扫描与卡片结构、全帧RTL预览和native golden框架；更新中文五组标签、语义与新数值夹具 |

几何：64×130 →32×65 →16×32 →8×16 →4×8。理论conv MAC 231413760，约旧461445120的50.2%；双头纯INT8权重716976B，不含bias/requant/header/对齐，比旧纯权重增加33024B。不能用理论MAC直接承诺延迟；固定最大深度不改就不会自动省DRM。最新153.5/155 DRM余量很小，必须真实新源门控。

### CPU当前作用及目标职责

当前生产实例为RV32I（ENABLE_M=0、预测关闭），8KiB ROM/8KiB RAM，无模型DDR直访。固件启动自检、读取DDR状态、提交NPU请求、读top1/最后概率事件/cycle、UART报告和ACK；重计算、DMA及UI扫描均由硬件承担。当前最后概率事件不是获胜类置信度，UI也不是CPU发布的业务结果。轻量控制核分工合理，但应用决策较薄。

五类目标：NPU算前端、卷积、池化、GAP和串行双FC；CPU从同一frame ID读取10logits，做定点sigmoid、stable softmax、mask/再归一、主导/无活跃判定，可配置阈值、有限重试及可选平滑，再原子提交UI。先用LUT/整数实现与测周期，不要求FPU或直接开启M扩展。可选平滑默认旁路，不能混淆原始golden与平滑显示。

### 实施顺序与验收

1. 训练split采样校准、BN折叠，建立每层/双头INT8契约、bias/requant/镜像与模型ID。不得复用旧八类量化常数。
2. 在独立val split比较float/INT8：分别报告activity逐类指标、dominance和最终主导组指标、无活跃及稀少类退化。记录数据选择、版本、命令和hash；结果决定能否继续，未有结果不预设“精度通过”。
3. 新130帧前端及全层位级golden；参数化尺寸和DDR版图，明确round-half-even、输入零点及边界，不引用八类golden冒充新模型。
4. 串行双头、完整MMIO快照、CPU定点后处理和UI提交；实际CPU/native联合覆盖不同A/B无reset、多活跃、无活跃、阈值附近、帧一致性与超时恢复。
5. 实际RTL全帧渲染五类UI；新源唯一compile/synth/map资源门控，通过后限时PNR并核验完整十表setup/hold。旧映射库不能冒充新源。
6. 安全烧录后验收CPU/DDR/新模型加载/双头/CPU/UI闭环；接真实音源后才做识别准确率验收。最终再和Flash启动集成，做完整脱机冷启动回归。

五类迁移是中至高难的跨模型、RTL、固件和UI工作，不是把8改5。最先解除的风险是量化精度，其次固定尺寸与资源/时序；完成这些证据前不承诺交付日期。

## 5. 执行纪律与接手检查

1. 先读STATUS顶部，再git status/diff；分支XSY。只修改/提交instrec_fpga，保护cpu两项用户diff、PCB、obj_dir和无关报告。push此前已获授权。
2. 此文档交接不启动PDS或板级操作；最后记录无PDS/monitor残留。未来一次仅一个PDS，冻结源、检查hash、记录CPU/阶段/日志并设置审查截止，失败证据不得覆盖。
3. 禁止终止/重启/新建cdt_js，不操作既有cdt_cfg。烧录沿用安全复用流程；历史JS9040/cfg46156身份需只读确认，不能仅凭旧PID操作进程。
4. 所有新模型/契约/镜像/报告独立命名、落在instrec_fpga并可跟踪；训练大缓存只读。不提交build、原始日志、令牌等。
5. 实施后按STATUS → CHANGELOG → 外部项目记忆 → git commit顺序交接，记录已验证和未执行阶段；文档变更不重复跑整套RTL回归。

接手首轮输出应分别是：Flash通路/镜像工具核对结果，以及五类校准计划或首批量化契约/留出评估结果。保留现有可展示的八类系统，避免在没有候选验证证据时反复烧录。
