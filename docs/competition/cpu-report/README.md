# PaceRV竞赛报告：CPU部分

[阅读完整中文报告](CPU_REPORT.md)。本文面向嵌赛FPGA赛道，作为队伍总报告的CPU部分，按作品概述、系统组成、完成情况与性能、总结、参考文献组织。

## 文件索引

| 文件 | 内容 |
|---|---|
| [CPU_REPORT.md](CPU_REPORT.md) | 中文正文、4张图与4张表 |
| [assets/](assets/) | 中文架构图及链表、矩阵、状态机局部波形；PNG用于插入文档，SVG保留矢量文字与图元 |
| [EVIDENCE.json](EVIDENCE.json) | 实测指标、比较来源、源文件哈希与图表来源 |
| [VERIFICATION.json](VERIFICATION.json) | 指标复算、源哈希、采样统计、字数及图表检查记录 |
| [source/prepare-report-assets.py](source/prepare-report-assets.py) | 原研究工作区的中文图表生成与证据整理脚本 |
| [source/verify-report.py](source/verify-report.py) | 原研究工作区的指标、素材与文本核对脚本 |

## 性能与成果

PaceRV在已核实的公开单发射五级顺序RV32IMC FPGA实现中达到SOTA执行效率：结果保持版为**3.442075 CoreMark/MHz**，145.125 MHz下为**499.531 CoreMark**。基础版使用**6,097 LUT / 2,541 FF**，结果保持版使用6,150 LUT / 2,541 FF，资源数均覆盖完整系统。

报告包含已有板级CoreMark运行结果和新加入的本地RTL仿真波形。三张波形图各展示函数入口附近32个边沿，表内统计对应完整1,024边沿采样窗口。

相关研究获IEEE MCSoC 2026录用。正式硬件与研究材料分别位于：

- [PaceRV硬件仓库](https://github.com/BXSYGJ/PaceRV)：处理器、固件、上板输入与实测依据。
- [PaceRV-MCSoC2026研究仓库](https://github.com/BXSYGJ/PaceRV-MCSoC2026)：论文实验数据、预测代码及复现材料。
- [本仓库的独立ILA与裸核发布集](../../../cpu/validated-extensions-20261101/README.md)：三套独立含ILA实现及原始CSV/VCD波形。

## 图表生成脚本的使用环境

`source/`保存本次报告在原研究工作区使用的脚本。脚本按`ccfa-workfiles/competition/cpu-report/`的原始目录层级定位工作区；输入文件清单及哈希保存在`EVIDENCE.json`中。重绘需要对应的PaceRV、论文复现目录、原始ILA采样CSV及论文架构图，并安装Python、Matplotlib、NumPy和Pillow。文本诊断步骤还调用本机安装的CCFA Paper Writer检查脚本。

本目录可直接阅读正文和使用图表；完整CPU的构建、烧录及测试按上方硬件发布入口执行。
