# 交响乐乐器组识别：XSY / XSY2代码核验

核验日期：2026-11-14。当前应用目标为全国大学生嵌入式芯片与系统设计竞赛2026紫光同创赛题一中的交响乐识别系统。用户已确认识别目标是同时出现的乐器及其进入、退出；CPU工作按用户要求视为已完成，后续聚焦应用。

## 实际核验范围

仓库：BXSYGJ/ZGTC_RISC_CPU。通过Git远端查询与fetch核对：

| 分支 | 远端提交 | 日期 |
|---|---|---|
| XSY | `4d3d6f1be60026b307ab26ac48450f8b4031859d` | 2026-11-14 |
| XSY2 | `8f902aec29c38bc4a32a4e95ab47d18411684b52` | 2026-11-03 |

本轮读取Git对象、模型源码、清单及已有报告，并比较模型资产SHA256。识别指标引用仓库已有离线评估，本轮未重新执行训练或8906样本评估。当前工作区保留原分支与源码，未合并远端代码。

## 已有识别资产

两个分支都保存`models/group5_v3_float_20261102/`：

- `model_source.py`定义`DualHeadInstrumentCNN`，包含activity与dominance双头。
- `float_state.npz`为真实权重文件，2,685,373字节；SHA256为`0fb659348612629a91818cba45280e38b721047f3d8122e0726fa4a6e8ac4826`。
- `reference_vectors.npz`保存五条64×130特征、五维标签及双头输出，包含多个乐器组同时活跃的参考；SHA256为`584fb765a5270a869db855e8c4b9c6d803d906fcbcd470c8e3795c6097f9acaa`。
- 训练配置记录模型epoch22、35,185训练样本、8,906验证样本，activity损失为BCEWithLogitsLoss。完整训练数据缓存由文档指向外部兄弟InstRec工程，Git保存冻结权重、配置和参考数据。

五组顺序为strings、woodwinds、brass、percussion、keys，即弦乐、木管、铜管、打击乐、键盘/拨弦。activity为五个独立sigmoid，可同时活跃；dominance来自独立输出头，经activity mask后归一。活跃度是模型分数，声学能量比例需另行定义与测量。

两个分支的模型源码、float权重和参考向量逐字节一致，三者哈希与冻结清单一致。train_config的Git文本换行与原清单记录不同，恢复原CRLF后哈希吻合。

## XSY较新的量化与评估

XSY还包含：

| 内容 | 现有路径 |
|---|---|
| INT8契约生成、整数参考推理 | `scripts/golden_pipeline_group5.py` |
| 验证与双头后处理 | `scripts/eval_group5_int8.py` |
| 逐层契约 | `scripts/outputs/group5_contract.json` |
| 双头权重镜像，725,760字节 | `scripts/outputs/group5_weights_image.bin` |
| 40份量化权重/偏置/尺度等数组 | `deploy/weights_group5/` |
| 已有离线验证报告 | `reports/group5_int8_calibration_20261103.json` |
| 已有量化契约复核 | `reports/group5_int8_contract_review_20261104.md` |

已有8906条验证记录：float macro-F1为0.8730742849，INT8为0.8655871912，下降约0.75个百分点；量化模型与float模型的主导组判定一致率为0.9705816304。上述数据属于离线验证，主导组一致率比较的是两个模型的输出。

冻结float清单中的quantized=false描述原float资产；XSY随后新增的INT8成果以量化契约及评估报告为准。

## 与当前板端的衔接

已选125MHz和109.375MHz位流仍运行八类、64×258特征和softmax链路。现有五组模型的冻结输入为44.1kHz、66150样本、64×130特征，双头各五输出；接入时需要对齐采样/特征契约、130帧几何、GAP计数及双头调度和输出。

已有五组模型提供窗口级乐器组活跃度。用户需要的进入/退出事件还需按时间戳连接连续结果，加入每组阈值、持续时间及迟滞策略，并用标注音乐片段检验时间误差。第一阶段可输出五大乐器组；组内小提琴/大提琴等细分类属于后续标签与模型扩展。

建议应用主线：五组多标签识别→乐器组进入/退出事件→HDMI活动时间轴。RTOS用于窗口事件、推理服务、结果整理、显示与记录的协作；当前仅完成方案讨论，尚未开始RTOS移植。

原时序验收目标保持paused，125/109.375MHz所选包继续保留。本轮没有新增PDS构建、上板操作或CPU修改。


## 2026-11-14 15:10再次检查上传

以上分支表为首次核验时的快照。本次重新查询远端并fetch后，XSY最新为0b8201e071c6c59b8d7ead23ad944684f4d0b24c；XSY2仍为8f902aec29c38bc4a32a4e95ab47d18411684b52。

| 北京时间 | 提交 | 新增内容 |
|---|---|---|
| 14:31:08 | 394481e | 归档seed85整机位流，构建脚本新增PlacementSeed |
| 14:48:12 | e155db9 | 移除USB开关支持，修复i2s_capture等待函数返回值解包 |
| 14:50:18 | 0b8201e | 补回flash_bitstream.py的__main__入口 |

增量共10个文件，683行新增、208行删除。五组模型、量化权重、golden推理及RTOS实现均未出现在本次变更清单中。

远端归档为instrec_fpga/releases/seed85-timing-20261114/artifacts/instrec_top_seed85.sbit，3,791,112字节。直接读取Git对象并重算SHA256：88e10b450cb8657321ad8bdb136f8e395ef48c555ba2db4c030671ed339fa7fd，与SHA256SUMS一致，校验退出0。

归档README记录ddrphy_sysclk slow setup WNS -0.809ns / 352失败端点，hold -0.117ns / 2端点；历史上板记录为DDR3 pattern 3/3、mel exact 100%及八个logits逐项匹配。此处引用上传者归档，本轮只核查文件和哈希，未执行板级重测。八通道结果对应现有八类识别；五组交响乐识别迁移和进入/退出事件仍为应用待办。

本次未checkout、merge、运行PDS或烧录。新归档与此前所选PaceRV整机包是不同源码快照；保留109.375MHz主版和125MHz备版的选择。
