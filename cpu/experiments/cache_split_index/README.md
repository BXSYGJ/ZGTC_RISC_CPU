# 拆分Cache请求寄存器实验

此目录仅保存未通过物理时序的独立实验，不被默认PDS/SoC构建引用。

rv32_cache.sv SHA-256：3CBF9F55E63BC492A1866D4609DCEA8106F2517FD273C9EC81B76DFC5B6644AC。

将保存的地址拆为索引、标签与低位，只对索引寄存器设置syn_maxfan=64。功能回归及短测通过，但132 MHz WNS=-0.523 ns、135 MHz WNS=-0.220 ns；没有新实板成绩。详见../../docs/CACHE_SPLIT_INDEX.md。

../../scripts/test_cache_request_capture.py明确读取此隔离源码做32配置和5故障反例；production分支另外验证实际生产源码，不把实验用例的通过等同于生产文件已采用该改动。
