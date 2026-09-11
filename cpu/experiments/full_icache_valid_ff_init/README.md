# 完整功能 I-cache 受控初始化实验

该候选保留 I-cache 原 valid 读接口，去除 valid 阵列的并行复位，尝试用启动期间逐项清零减少控制资源；GPIO、UART、42/33 ILA、D-cache 和所有对外行为均保留。

缓存/SoC 回归通过，固定 157.5 MHz PDS 得到 6706 LUT、3262 FF、WNS -0.322 ns。PDS 仍将无复位 valid 阵列推断为与分布式 RAM 候选相同的实现，关键路径时序失败，故不晋级、不插核、不上板。
