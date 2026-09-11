# 同步Cache与保留高段ALU版132 MHz ILA

日期：2026-09-07。本页绑定新Target132Kept配置，不覆盖旧Target132Carry或Target120；暂无本版真实板上波形。

## 冻结来源与通道

源实现为build/pds/20260907-094625-f8c6e702，非插核132 MHz/种子7时序已通过。新增ila_target132_kept_sources.json锁定全部20份输入，其中Cache SHA-256为680F03DF60A726DAB321904A2F72FF2C2A94B9E7D7D5D20842B4492B1CDC57F5，ALU为47E2A54401C1F3AEEC1E4F840682DC353B51FA20757634A46ACC6134A513BBB6。只与旧Target132Carry的这两份RTL不同，其他18份相同；旧源锁文件未改。

独立FIC使用cpu_clk上升沿、109通道、1024深度，关闭存储资格与多窗口。106位仍是fetch_complete，107位仍是mem_fire。通道表虽与旧132 MHz版相同，但这不授权复用旧源或旧波形：分析器必须绑定显式Profile、源清单与该配置专用源锁，不能仅凭CSV列名区分两个源码版本。

当前真实源ADF已由cdt_ins执行ins_open、ins_core_info、ins_save并逐路确认全部109个名称。插核构建目录为build/ila/20260907-101047-f1aac71b；verify.stdout.txt与verify.stderr.txt无原生错误。原生保存后的时钟、宽度、深度和采样选项与模板逐项一致，ADF、网表、固件、原始源清单的拷贝均与源实现逐字节相同。独立证据见build/ila-target132-kept-mapping-audit.json。该映射审计不自动证明插核后时序合格。

## 验证覆盖

- Windows与WSL分别通过ILA Python回归32项测试方法，包括Legacy27、Target120、旧Target132Carry及新配置。新配置复用现有九项边界测试并增加两项来源隔离测试：相同通道不能替代旧Profile，重新计算源清单哈希也不能把旧源锁冒充新源。
- 新配置继续检查mem_fire必须伴随mem_valid、下一拍wb_valid必须有上一拍mem_fire，以及既有流水PC/valid传递约束；不新增异常场景下不成立的反向断言。
- 每个源文件的错误修订、错误频率/配置、损坏或重算哈希的FIC、六类产物篡改、原始时序为负或约束失败、CLI缺少manifest均被拒绝。合成夹具仅测试分析器，不是硬件波形。
- PowerShell运行器、前置测试及完整回归入口均通过语法与UTF-8 BOM检查；新测试接入validate.ps1。RTL本轮未再改变，使用已完成的当前源全回归，并另跑新增的ILA专项测试。
- 三个非默认配置各20项PowerShell前置拒绝、3项布局种子参数拒绝通过；新增4项成功返回码测试覆盖调用前LASTEXITCODE缺失/非零，以及删除显式成功退出后的反例。共67项契约检查；退出码测试只执行合成成功尾部，不伪装PDS运行。
- 三份既有Target120真实CSV重新读取：两份性能、一份验证，各1024样本，匹配旧插核manifest及产物哈希继续通过。不把这些历史数据标为本版132 MHz采集。

## 插核实现

性能种子插核实现20260907-101047-f1aac71b已独立核验通过：132 MHz、布局种子7、9084 LUT、6876 FF、21.5 DRM等效用量、4 APM，setup WNS +0.095 ns。DRM栏保留原始小数，不说成21.5颗物理器件；资源分母取布局后CLMA+CLMS。109通道、1024深度保持不缩减，没有关闭探针或降低采样时钟。位流SHA-256为2E828A42EAA8FCB92591EDE8948F5E5034ADDBFADE4C87F73C737016CB47912D，FIC为32CE37340C0DED64B78C2233EB4E1C4C2AD3FA9FE518C235896924FB627BDFEE；证据见build/ila-target132-kept-performance-audit.json。

本次外层命令以1退出，却已输出成功manifest。核查发现运行器使用Start-Process启动厂商程序，成功返回时没有显式exit 0，调用方读取LASTEXITCODE可能得到缺失或陈旧值。没有忽略这一不一致：独立重读原始报告、器件/时钟/资源、实际种子与生成成功日志，以及全部分析器产物绑定，确认真实PDS结果通过。运行器现于完成manifest输出后显式exit 0，失败仍exit 1；四项退出码测试复现并拒绝旧行为。补丁在性能插核构建之后加入，不声称性能构建已使用该补丁。

匹配验证种子插核20260907-101924-e6deb252也已完成，并在修正后的返回码契约下退出0。来自源20260907-095438-af2f16ac，同为132 MHz/种子7、9084 LUT、6876 FF、21.5 DRM等效用量、4 APM、WNS +0.095 ns。验证位流SHA-256为4F3AE77A87B805A709EC0D83A6E76B4B7A95B27A497107911067A8A547415D13；FIC为8604EA8D8118D5656678F94584FF2E3C73DF18DEEFDF5CF8FEC5CF0020621E27。

两份插核实现的20源锁、6000轮性能/验证固件身份、真实源ADF/网表/HEX副本、109条原生确认、六类绑定产物、原始报告和成功种子/生成命令均已重新核验，见build/ila-target132-kept-paired-audit.json。资源与时序完全一致；FIC仅规范化构建根路径和一条已校验格式的工具生成时间注释后相同，其余属性未忽略，原始FIC哈希仍分别绑定。插核过程不重复综合，因此使用已有parse_ila_reports入口，synthesis_luts为空，不能假造综合计数来让通用解析器通过。两个本轮构建均已终态，均未下载到远程板；没有真实采样就不宣布当前源ILA验收通过。

非插核的132/135 MHz两组性能/验证结果见ALU_KEPT_PRECOMPUTE.md。当前源真实ILA、实板长测、GPIO输入事件、电气约束/SCBV与长期稳定性仍未完成。只有用户明确要求时才上传GitHub。
