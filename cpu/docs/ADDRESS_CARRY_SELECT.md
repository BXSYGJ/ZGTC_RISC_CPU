# 独立地址加法器分段进位选择

## 动机与最小改动

已测ALU分段版在132 MHz有+0.103 ns裕量，但其插核版本三组布局均失败，最好仍差0.082 ns。原始路径显示D-cache返回数据经forwarded_a、独立effective_address加法器进入下一次请求使能；rv32_alu中的分段逻辑并不会自动改写地址生成式。

只替换rv32_core.sv中effective_address的组合实现：低16位产生17位和；高16位预计算无进位/有进位结果，按低段bit16选择。没有新增端口、参数、寄存器、流水级或握手控制，地址对齐、store数据移位/字节选通、JALR最低位清零、异常mtval与请求选择仍使用原有完整effective_address。

原核心SHA-256 C4F0EF80E634F153F5BF1CB2B0F9BB314432333BF9DC93E1A8E9F6E1C2CC2346；普通分段候选68D5174737B6CDD3134A4C3F15F7223079AE87C33DE93A007898FEE6AAD4A284。后续仅给两个高段网络添加保留属性，保留候选为95932182D4FB09DDD7475E6A26E8790F6049A55C806F656D6332B2E9560BB43C。两候选均未取得合格物理结果，现已隔离；当前生产核心已恢复为上述C4F0EF80版本。ALU、BTB、M单元、Cache、PLL及约束均保持上一已测132 MHz版本不变，现有Target132Carry锁仍属于旧核心，不能直接用于本候选。

## 算术等价与定向检查

令B=2^16，A=A高×B+A低，I=I高×B+I低。低段和L=A低+I低的bit16就是进位C；高段选择(A高+I高+C) mod B。因此拼接结果等于(A+I) mod 2^32，和原32位RTL加法的截断行为一致，包括负立即数的二进制补码模式。该数学说明不等于已完成形式工具认证，也不保证布局工具一定保留特定最大进位链长度。

address_carry_select_tb直接实例化真实rv32_core，向整个EX译码结构体和forwarded_a注入定向操作数，分别检查完整32位地址、字/半字/字节对齐及JALR目标。16种边界值两两组合、32个位位置的进位/溢出以及20000组固定序列偏移，共20320组；新式和原式均通过。五个实际编译反例：丢进位、错用bit15、错误高段进位符号、提前清零低两位、丢立即数高段，均由运行时断言拒绝。

最初Icarus不支持强制结构体部分选择而编译失败；改为具名同布局结构体整体强制后通过，没有为适配测试改动CPU语义。测试仅隔离组合数据路径，流水级握手/执行行为由完整CPU与独立参考模型回归另行检查。日志test-address-carry-select.log保留首次失败，test-address-carry-select-fixed.log为修正后的通过记录；已接入validate.ps1。

## 同固件短测

| 种子 | 当前编译目录 | 周期 | 退休指令 |
| --- | --- | ---: | ---: |
| 性能10轮 | 20260907-062310-a083c684 | 3307565 | 2748941 |
| 验证10轮 | 20260907-062319-921d06bd | 3308242 | 2749614 |

与原ALU分段版对应的20260907-051417-065cf6aa、20260907-051424-c7ebb14f比较，两组固件、参数和全部UART字节一致。独立重验可执行文件、固件、源快照、结果与UART哈希，确认只有rv32_core.sv变化。证据build/address-carry-select-short-audit.json。此处是RTL短测，没有新硬件成绩，也不宣称执行周期下降。

## 正式实现与回归

普通分段版两频率均已失败：132 MHz构建20260907-062400-dcf04a09为10445 LUT、5020 FF、WNS -0.486 ns；135 MHz构建20260907-062427-1b277d89为10295 LUT、5029 FF、WNS -0.485 ns。均4 APM，没有成功manifest，未上板。原始报告独立解析、源快照和位流哈希见address-carry-select-plain-terminal-audit.json，不能因sbit存在就判定成功。

普通分段版完整validate-address-carry-select.log终态通过，外部RV32UI 41测试/164运行、RV32UM 8测试/32运行及共8拒绝控制通过，196次结果与之前核心逐项相同。实际集合为p0_c0_s4、p1_c0_s4、p0_c1_s1、p1_c1_s4，并非宣称单一板级D-cache几何覆盖。首次调用附带了接口未声明的CacheSetBits，审计只按实际results配置记录；后续保留属性版调用已去除此无效参数。外部测试不等于ISA认证。

## 高段保留修订

普通132 MHz原生最差路径中，address_low[16]之后又进入mem_address[18]/[22]/[26]的COUT链；未观察到所期望的单纯高段结果选择。不能仅凭RTL写成两种预计算就认定综合保持了电路边界。

已核对本机PDS原厂ADS_Synthesis_User_Guide.pdf：Attribute Reference开头支持Verilog-2001属性语法，5.11节（正文83页）说明syn_keep用于保留实际连接的net，5.15的syn_preserve则针对寄存器。因本次是组合网络，只对address_high_zero与address_high_one增加(* syn_keep=1 *)，不增加寄存器或时序例外。WSL未安装pdftotext，改用已有PyMuPDF提取到build/ads-synthesis-guide.txt核查；没有伪称调用缺失工具成功。

保留后的原生综合中，32个高段位均有唯一LUT Z驱动且有LUT消费者；普通分段版对应具名驱动为0。address-carry-keep-native-nets.json与native-comparison.json绑定原厂手册及前后网表哈希。该观察只证明这些网络实际保留，不证明最大进位链长度、结构独立性或最终时序。

保留修订再次通过相同20320组及五类反例，两种10轮CoreMark的结果和UART与普通分段版完全相同，目录20260907-063806-ef761319、20260907-063816-6c645521，独立审计address-carry-keep-short-audit.json。保留版132 MHz构建20260907-063828-c34b6772为10389 LUT、5045 FF、WNS -0.247 ns；135 MHz构建20260907-063855-2d5d1bfc为10320 LUT、5051 FF、WNS -0.226 ns，仍均失败，均4 APM。相对普通分段版失败幅度有所减小，但不能以此称达到132/135 MHz，更不能拼接旧周期给失败实现计分。证据address-carry-keep-terminal-audit.json。

保留版完整validate-address-carry-keep.log已终态通过。新RV32UI构建20260907-064450-e2aad191有164次运行，新RV32UM构建20260907-064625-a09a3805有32次运行，两套共8个拒绝控制通过；源码哈希绑定95932182，所有结果与普通分段版逐项相同。外部调用只使用已声明参数，实际四配置见address-carry-keep-external-isa-audit.json。构建目录保留工具原始名称，事件审计使用UTC。

## 恢复与下一方向

两个地址方案功能均通过，但四个正式实现都失败，未采用为生产版。已经恢复已实测132 MHz版本的全部20份RTL/PLL/约束，并逐SHA-256与build/pds/20260907-051442-9813d121核对；当前核心为C4F0EF80，旧3.02972 CoreMark/MHz证据仍绑定同一生产输入，不宣称新测量。当前Target132Carry锁重新与生产源一致，但其既有插核实现时序失败仍未解决。

失败方案保存在sim/address_carry_select_candidate.svh，仅供test_address_carry_select.py向临时核心副本注入。夹具能精确重建95932182保留候选，不参与生产PDS源列表。原式与隔离候选的20320组检查及五类反例再次通过；恢复后的run_core_tests.ps1 -EarlyDRequest -BtbIndexBits 8与独立参考/内存比较也通过，日志test-address-carry-isolated.log、address-carry-restored-core.log。完整PDS和全部中间证据保留，未删除失败记录。

下一方向是研究Cache负载捕获与有效事务控制是否可以分离，而非继续只拆地址进位链。现有req_valid && req_ready同时控制请求载荷与状态/错误更新，使新地址合法性进入大量地址副本的CE；拟只在明确可接收窗口预采样无效载荷，事务状态仍按真正握手更新，并必须验证忙时、返回回压与flush期间稳定性。这不同于之前已隔离的cache_split_index地址位段分拆。此处仅为下一候选依据，尚未修改Cache或放宽任何握手检查。

继续执行至少3.0 CoreMark/MHz和0.031 CoreMark/LUT门槛；本轮无新合格频点、执行效率或资源效率成绩，不把旧周期和新LUT拼成正式新成绩。

未进行Git提交或上传；本轮没有尝试绕过此前浏览器启动的工具策略拒绝，尚未预约或烧录板卡。
