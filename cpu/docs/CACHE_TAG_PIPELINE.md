# Cache 标签提前读取实验

日期：2026-09-07。目标是不增加命中气泡，同时缩短限制时钟频率的缓存控制路径；所有修改均隔离，不替换生产20份输入，也不上传GitHub。

## 先完成更小的H1候选验证

通用H1/C2使用BTB源码A747330D，135 MHz种子7性能/验证实现均为8127 LUT、5014 FF、WNS +0.027 ns。

- 性能构建：build/btb-history-width-h1-c2-portable-stage/build/compiled/20260907-125619-06bc3b1e。6000轮、1946176342周期、1649428424退休，CRC通过，模型时间14.4161210519秒。
- 验证构建：build/btb-history-width-h1-c2-portable-stage/build/compiled/20260907-125643-f0c2d1d0。6000轮、1951421059周期、1649775523退休，CRC通过，模型时间14.4549708074秒；验证结果不产生性能分数。
- 两者从启动即绑定各自PDS清单；原始UART、固件、18份编译输入和20份物理输入重新核验。
- 对比同135 MHz固件的旧分立H1：执行拍数不变，少54 LUT、多5 FF。执行效率投影3.0829683161 CoreMark/MHz，吞吐投影416.2007226784 CoreMark，资源效率投影0.05121209827 CoreMark/LUT，相对旧分立实现提高0.66445%。
- 审计：build/generic-h1-full-comparison-audit.json、build/generic-h1-full-validation-audit.json。不是移用旧板测数据，也不是新实板成绩。

本轮通用H1也完成完整非对称CPU集成、196次外部ISA及8个拒绝，并经build/generic-h1-isa-audit.json独立核验。首次ISA构建20260907-131714-67dd52a2因隔离stage遗漏sim/isa适配器目录而终止，未运行成功用例；补齐原始目录后重新生成两份独立通过构建，失败日志保留，不计为RTL功能失败或通过。

## 路径定位修正

最初从原生路径名caches[0].enabled.cache_1误判为指令缓存。本轮对照rv32_memory_system.sv通道连接及原生存储推断表后确认：cache_1拥有512×32异步可写数据存储和128×6标签，是2 KiB数据缓存；cache拥有两路1024×32同步只读数据存储，是8 KiB指令缓存。不能把PDS变换后的层级数组下标直接当作RTL通道下标。

因此保留先完成的只读标签试验，但不再声称它直接切断数据侧关键路径；后续版本把相同机制扩展到两个缓存。

## 电路变化

原标签查找由request_address寄存器出发，经有效位/标签数组选择、比较产生hit。新实现把两个路的标签及有效位在请求接收边沿读入寄存器，LOOKUP拍只做寄存器标签比较，不改变公开接口或状态机拍数。

ready窗口使用实时请求组索引，忙时使用保存的请求索引。回填最后一拍写入标签并立即进入LOOKUP时，同沿读数组会读到旧值，所以逐路旁路新标签和有效位。标签数据不额外复位；有效位复位为零。写回、错误回填、刷新和请求非法地址语义保持。

- 固定基线：experiments/cache_tag_pipeline/baseline.sv，SHA-256 680F03DF60A726DAB321904A2F72FF2C2A94B9E7D7D5D20842B4492B1CDC57F5。
- 只读试验：experiments/cache_tag_pipeline/readonly_only.sv，SHA-256 508D42D9183BF7177301EE6168A606A89F745C879F3E27207DF68D874BDDE6C9。
- 双缓存试验：experiments/cache_tag_pipeline/rv32_cache.sv，SHA-256 D3B49CBAC9E7B3C8266F17F85D9E5B31C82B0C00EEA2E9A507584D468651A8F4。
- 两个隔离stage均采用通用H1/C2；相对8127 LUT物理基线，20份设计输入中只改变rv32_cache.sv。

## 定向测试与反例

scripts/test_cache_tag_pipeline.py复用逐周期Cache参考比较：32种地址宽度/读写/快读/快写/重叠组合，加16种只读实际容量组合；后者也独立运行固定基线，避免驱动只适配新实现。

初次只读试验的live_busy_tag_index错误注入未被随机流检测到，没有据此宣布反例通过。新增合法的无效请求噪声及定向序列：先在相邻组两路装入不同标签，再回填目标组，使错误读取实时索引导致另一组的同标签伪命中。固定基线也通过新序列，错误版本产生功能断言失败。

最终双缓存版本48种正例通过；8种错误分别在只读和读写模式运行，共16个编译成功、运行失败的错误注入。覆盖旧索引、忙时实时索引、两路标签旁路删除、两路有效位旁路删除、错误选路和只在req_valid时读取。拒绝必须来自功能断言，不能仅因覆盖率或编译失败。

原有test_cache_synchronous_read.py、test_cache_ready_payload.py、test_cache_request_capture.py均通过，新增驱动参数默认关闭；validate.ps1保留UTF8 BOM、语法检查通过，并接入新定向测试。

## 只读版本结果

- 完整非对称CPU/SoC/参考模型/旁路/独立提前读写/严格lint流程通过。
- 196次外部ISA及8个拒绝通过；审计重新核验原始日志、固件、上游及适配器输入，不等于完整ISA认证。
- 两种10轮短测3251073/3258866周期，与通用H1同固件完整UART逐字节一致，18份输入只有Cache不同；短测不是性能分数。
- 135 MHz/种子7构建20260907-130252-7b584326终态失败：8021 LUT、5017 FF、19 DRM、WNS -0.242 ns；位流虽生成但不合格，不烧录，不用135 MHz计算正式分数。
- 新关键路径从数据缓存request_address到指令缓存synchronous_tags.valid_way0，说明逻辑被移到请求侧后形成了新的跨通道路径，不能仅凭减少LUT宣布优化成功。
- 证据：build/cache-tag-pipeline-short-audit.json、build/cache-tag-pipeline-physical-audit.json、build/cache-tag-pipeline-isa-audit.json。

## 双缓存版本状态

48种差分、16个拒绝、完整非对称CPU集成和严格板级lint通过；两种短测与通用H1完整UART逐字节一致，保持3251073/3258866周期。196次外部ISA及8个拒绝均通过。135 MHz/种子7物理构建20260907-131127-fa668113终态失败：7911 LUT、5020 FF、19.5 DRM、WNS -0.719 ns。少216 LUT但时序明显退化，不能采用或用135 MHz给该失败位流计算正式分数。证据见build/cache-all-tag-pipeline-physical-audit.json和build/cache-all-tag-pipeline-isa-audit.json。

原始最差路径已经转为数据存储读取：request_address[3] → asynchronous_writable.storage_1的RAM64X1D及两级选择 → d_rsp_data[29] → mem_value[13] → forwarded_b[13] → 有符号比较/分支判断 → mem_cause[0]。12级逻辑，逻辑2.617 ns、布线4.961 ns（65.466%）。这是本版报告中的实测实现路径，不再把它解释成标签查询路径。

下一步可从680F缓存基线探索可写数据的同步读实现，而非直接采用失败的标签版。必须保持写命中字节合并、末拍回填旁路、重叠请求，以及脏行写回首拍/后续拍/背压时序；先证明逐周期等价，再检查原生RAM推断与PDS。是否改善仍待实验，不通过随意增加load-use气泡来换取表面频率。

## 未关闭项

生产输入、已发布版本和已测132 MHz成绩不变。本轮无Git、浏览器或板卡操作。新候选的实板长测、独立GPIO输入、SCBV电气确认、对应源码ILA和长期稳定性仍未完成。小正裕量不是稳定性或物理极限；后续频点必须先核验PLL/运行器支持。
