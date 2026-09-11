# 同步可写缓存与H3/C2预测器组合

仅用于隔离实验，不能作为实板已通过版本。生产工程不变，不上传GitHub。

- rv32_btb.sv由experiments/btb_history_width/rv32_btb.sv仅将HISTORY_BITS默认值1改为3生成，逐字节与既有H3候选相同。
- 数据缓存引用experiments/cache_synchronous_writable/rv32_cache.sv（DB55CBF5）；核心C4F0、ALU47E2和其他输入不变。
- 相对于已合格的同步缓存H1阶段，仅更换BTB；相对于原H3阶段，仅更换数据缓存。两条对照都必须独立核验。
- configuration.json只提供参数给相同固件短测；没有时钟和源码快照的硬件绑定，不能用于宣称合格135 MHz分数。
- 正式长测需使用本组合自身合格PDS的manifest.json，并重新执行性能与验证6000轮。
- 执行效率、时钟与面积共同评价；不把不同源码的仿真/板上成绩与本版LUT分母拼接。
