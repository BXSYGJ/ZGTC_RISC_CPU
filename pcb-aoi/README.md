# PCB AOI 视觉识别核心与训练数据

本目录归档 Loongson AOI 项目的 CNN/YOLO 视觉识别核心及 2026-07-15 现场增强数据。代码来源是 [BXSYGJ/Loongson_AOI_PCB](https://github.com/BXSYGJ/Loongson_AOI_PCB)，main 提交 `9a7da7b475cfa5c529cc35ae3092828d3ccce6a7`。整理日期：2026-10-25。

## 快速定位

| 内容 | 路径 |
| --- | --- |
| 训练、推理、评估代码 | [algorithm/core](vision-core/worktrees/algorithm-ai/algorithm/core/) |
| 训练好的 PyTorch / ONNX 模型 | [best.pt、best.onnx](vision-core/worktrees/algorithm-ai/runs/detect/pcb_defects/weights/) |
| YOLOv8n 预训练初始权重 | [yolov8n.pt](vision-core/worktrees/algorithm-ai/yolov8n.pt) |
| 从 best.pt 读取的实际网络结构 | [pcb_detector.yaml](vision-core/model-definition/pcb_detector.yaml) |
| CNN 卷积、C2f、SPPF、Detect 源码 | [cnn-source-reference](vision-core/cnn-source-reference/ultralytics-8.4.87/) |
| 训练数据、标注及原准备报告 | [pcb_defects](vision-core/datasets7.15现场增强后/pcb_defects/) |
| 完整定位与核验说明 | [核心与数据定位](vision-core/README_核心与数据定位.md) |
| 模型与数据核验报告 | [recovered](recovered/) |

## 模型

实际模型是 **YOLOv8n 七类 PCB 缺陷检测器**，参数量 3,012,213。CNN 主干属于该 YOLO 网络；在已检查的源仓库六个分支和三个部署包中，未发现另一套独立 CNN 分类器。类别为干焊点、安装不当、PCB 损伤、短路、少锡、反向、多锡。

`best.pt` 是 PCB 训练权重；`yolov8n.pt` 是通用初始化权重。`best.onnx` 的固定输入是 `[1,3,1024,1024]`，输出是 `[1,11,21504]`。ONNX 图含 64 个 Conv 算子；完整性检查与 OpenCV DNN CPU 推理均通过。真实图片样例推理检出 8 个少锡候选，见 [核验图片](recovered/verified-inference.jpg)。这项运行检查不等于重新评估全数据集精度。

CNN 源码参考提取自本机 Ultralytics 8.4.87 安装，版本与权重元数据一致，随附原许可证及来源哈希。实际模型定义来自加载的 `best.pt`。

## 数据规模与完整性

数据来自用户提供的 `datasets7.15现场增强后.zip`。原包 SHA-256 为 `e215e4d5c6ed376c279627afc4d5b7e6c2e3c6919bacf85a49c1dfe9a6feef06`。

| 划分 | 图片 | TXT 标注 |
| --- | ---: | ---: |
| train | 1,164 | 1,164 |
| val | 66 | 66 |
| field 原图存档 | 195 | 保留现场 LabelMe JSON |
| 全部图片文件 | 1,425 | — |

训练与验证合计 1,230 张；field 原图是训练目录中的副本。按图片内容 SHA-256 去重后，共 1,221 张不同图片；训练集中有 9 对相同字节的图片。原始文件全部保留。3,781 个数据文件已经逐一与原 ZIP 条目 SHA-256 比对，图片解码和主划分标注检查通过，数量与原数据准备报告一致。

train 有 56 个空标注、val 有 8 个空标注，与原准备报告相符。val 没有 `pcb_damage` 类目标；`test` 复用 val，没有独立测试集。train/val 之间无字节完全相同的图片，未据此声称不存在全部同源或近似图片。

确认范围是所提供 ZIP 的完整恢复；没有对夸克整个 `code`、`AAAED` 云端目录逐项比较。源 GitHub main 的 24 张示例图片与部署包并非完整训练集。

## 本地复查

使用 PowerShell 7 和 `requirements.txt` 所记录的 Python 依赖，在本目录运行 `Verify-Recovery.ps1`。脚本检查 35 个项目文件和 3,781 个数据文件的 SHA-256，并重新加载 `best.pt`、核验训练输入。原 ZIP 位于当时机器的历史路径；新电脑没有该 ZIP 时仍会核验全部展开文件。原始核验报告中的绝对路径记录的是当时取证位置。

模型核验脚本是 `recovered/inspect_models.py` 和 `recovered/inspect_checkpoint.py`。训练入口是 `vision-core/worktrees/algorithm-ai/algorithm/core/train.py`，其原相对数据路径已验证可定位这里的 train/val。

`loong_detect` 原样保存为历史推理参考，其默认根路径假设来自旧布局。完整网站仍由来源仓库维护。本归档不启动训练或硬件控制。
