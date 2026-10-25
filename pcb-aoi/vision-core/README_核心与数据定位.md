# PCB 视觉识别核心与训练数据

整理日期：2026-10-25。

代码来源：[BXSYGJ/Loongson_AOI_PCB](https://github.com/BXSYGJ/Loongson_AOI_PCB)，main 提交 `9a7da7b475cfa5c529cc35ae3092828d3ccce6a7`。

## 核心在哪

项目使用 **YOLOv8n 七类目标检测模型**。仓库通过 `from ultralytics import YOLO` 调用网络。CNN 主干就是这个 YOLO 网络的组成部分；在已检查的六个 GitHub 分支和部署包中，没有发现另一套单独训练的 CNN 分类器。

从 `best.pt` 实际读取到：`DetectionModel`，7 类，3,012,213 个参数，深度系数 0.33、宽度系数 0.25。结构包含 Conv、C2f、SPPF、多尺度特征融合和 Detect 检测头。

本目录保留了 GitHub 的相对布局，训练脚本当前的相对数据路径可以直接找到恢复的数据。

| 内容 | 本目录内路径 |
| --- | --- |
| 训练入口 | `worktrees/algorithm-ai/algorithm/core/train.py` |
| 检测入口 | `worktrees/algorithm-ai/algorithm/core/detect.py` |
| 评估入口 | `worktrees/algorithm-ai/algorithm/core/evaluate.py` |
| 数据及类别配置 | `worktrees/algorithm-ai/algorithm/configs/pcb_defects.yaml` |
| PCB 训练权重 | `worktrees/algorithm-ai/runs/detect/pcb_defects/weights/best.pt` |
| 龙芯／OpenCV 推理模型 | `worktrees/algorithm-ai/runs/detect/pcb_defects/weights/best.onnx` |
| 通用预训练初始权重 | `worktrees/algorithm-ai/yolov8n.pt` |
| 实际权重中提取的网络结构 | `model-definition/pcb_detector.yaml` |
| 训练参数和 100 轮指标记录 | `worktrees/algorithm-ai/training/latest/` |
| 图像格式转换、增强和现场数据准备 | `worktrees/algorithm-ai/algorithm/tools/` |
| 网站使用的推理封装 | `worktrees/cloud-cooperative-platform/local_dnn_detector.py` |
| 龙芯推理参考实现 | `loong_detect/detect_opencv_dnn.py` |

`best.pt` 是 PCB 模型，`yolov8n.pt` 是初始化权重，两者用途不同。`best.onnx` 固定输入为 `[1,3,1024,1024]`，输出为 `[1,11,21504]`。训练记录的 `imgsz=960` 与导出 ONNX 的 1024 输入分别对应训练和导出设置。

`loong_detect` 是仓库根目录中的历史参考脚本，其内置默认根路径仍是原代码布局假设；本次原样保存。核验脚本显式指定模型和配置，实际完成了 OpenCV 推理。完整网站及部署包保存在 `../recovered/github/Loongson_AOI_PCB-main/`。

## CNN 网络源码

模型的实际结构定义来自本次加载的 `best.pt`。具体层实现来自本机已安装的 **Ultralytics 8.4.87**，与 `best.pt` 和 `best.onnx` 中记录的版本一致，位于 `cnn-source-reference/ultralytics-8.4.87/`。

| 模块 | 源文件和定义 |
| --- | --- |
| 卷积及激活 | `nn/modules/conv.py`：`Conv`，第 39 行 |
| 特征提取 | `nn/modules/block.py`：`C2f`，第 288 行；`Bottleneck`，第 457 行 |
| 空间池化 | `nn/modules/block.py`：`SPPF`，第 208 行 |
| 检测头 | `nn/modules/head.py`：`Detect`，第 37 行 |
| 网络组装 | `nn/tasks.py`：`DetectionModel`，第 373 行；`parse_model`，第 1775 行 |
| 通用 YOLOv8 定义 | `cfg/models/v8/yolov8.yaml` |

这里提取的是相关源码参考文件及其原许可证。完整依赖仍由本机 Ultralytics 安装提供。具体模型的七类结构以 `model-definition/pcb_detector.yaml` 为准。

## 找回的数据

来源是你下载的 `D:/AAAFPGA/datasets7.15现场增强后.zip`，大小 184,424,602 字节。

SHA-256：`e215e4d5c6ed376c279627afc4d5b7e6c2e3c6919bacf85a49c1dfe9a6feef06`。

解压位置：`D:/AAAED/vision-core/datasets7.15现场增强后/pcb_defects/`。

| 目录 | 照片数 | 配套标注 |
| --- | ---: | --- |
| `images/train` | 1,164 | `labels/train`：1,164 个 TXT |
| `images/val` | 66 | `labels/val`：66 个 TXT |
| `images/field` | 195 | 现场原图及 LabelMe JSON；照片也被纳入训练目录 |
| 合计 | 1,425 | 含现场原图目录的重复存档 |

实际训练／验证划分合计 **1,230 张**；整个包按图片内容 SHA-256 去重后为 **1,221 张**。训练目录存在 9 对字节完全相同的图片。现场目录的 195 张原图是训练目录中的备份副本，不能再次算作独立训练样本。没有改动或删除这些文件。

训练集包含 4,490 个目标，验证集包含 203 个目标，当前训练／验证主标注均为 YOLO bbox。原有 polygon 标注备份和现场 JSON 也已保留。

训练集有 56 个空标注，验证集有 8 个空标注；这些数量与原 `dataset_preparation_report.json` 一致，其中现场数据处理策略明确允许负样本。验证集没有 `pcb_damage` 类目标；`test` 指向 `images/val`，没有独立测试集。训练与验证集之间没有字节完全相同的图片，此项检查不等于排除了所有同源或近似图片。

压缩包共恢复 3,781 个文件；每个文件都对照 ZIP 条目逐一 SHA-256 核验。ZIP CRC、所有照片解码、主划分图片与标注配对、类别编号和归一化坐标检查均通过。实际计数与包内数据准备报告相符。这里确认的是这个已下载压缩包完整恢复，未对整个夸克 `code`、`AAAED` 云端目录逐项比对。

包内 `dataset.yaml` 保留了以前电脑上的绝对路径。训练入口读取的是 `worktrees/algorithm-ai/algorithm/configs/pcb_defects.yaml`；已验证其相对路径指向本次恢复的数据，读到 1,164 张训练图和 66 张验证图。

## GitHub 是否包含完整训练集

已检查 `main`、`algorithm-ai`、`hardware-sm`、`phone-browser-inference`、`ui-integration`、`cloud-cooperative-platform` 六个分支及 main 内三个部署 ZIP。main 有 24 张测试／现场示例图片，其他五个分支和三个部署包未包含完整训练图片集。算法目录的 `.gitignore` 忽略 `datasets/`。本次数据由你提供的 ZIP 找回。

本地微信旧备份 `Loongson_AOI_PCB_key_code.rar` 也已提取到 `../recovered/wechat-backup/`。它的说明明确表示过滤了数据集，且其中的旧模型 SHA-256 与 main 当前模型不同；旧版单独保存。

## 验证证据与复查

- `../recovered/model-inspection.json`：ONNX 检查、算子、输入输出、模型哈希与真实图片推理结果。
- `../recovered/checkpoint-inspection.json`、同名 `.txt`：PyTorch 权重元数据及实际网络结构。
- `../recovered/dataset-audit.json`：图片、标注、重复、类别计数及原准备报告。
- `../recovered/dataset-file-manifest.json`：恢复数据的逐文件 SHA-256。
- `../recovered/vision-core-manifest.csv`：从 GitHub 提取的源码、权重及配置的 SHA-256。
- `../recovered/cnn-source-manifest.csv`：本地框架源码来源及 SHA-256。
- `../recovered/verified-inference.jpg`：真实 PCB 图片检测示例，检出 8 个少锡候选。

在 PowerShell 7 中复查：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $script = [System.IO.Path]::Combine('D:/', 'AAAED', 'Verify-Recovery.ps1')
    & $script
} catch {
    Write-Error $_
    exit 1
}
```

本次完成了权重读取、训练输入路径核验和 OpenCV 单图推理，没有重新训练模型。GitHub 下载副本和原数据 ZIP 均保留。
