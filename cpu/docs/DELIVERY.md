# 工程快照交付与校验

本包用于交付当前源码和已测历史产物，不代表全部比赛验收完成。阅读入口为 `FINAL_REPORT.md`，逐项状态为 `ACCEPTANCE.md`。AI加速暂缓，其他未完成项保持明确记录。

## 制作

在Windows PowerShell 7执行：

```powershell
pwsh -NoProfile -File cpu/scripts/package_release.ps1
```

脚本通过WSL Ubuntu-22.04的Python标准库打包，输出到 `cpu/build/deliverables/engineering-snapshot-时间-随机编号.zip`，旁边JSON记录文件数、总字节和整个ZIP的SHA-256。唯一文件名且拒绝覆盖。压缩包包含当前源文件、文档、选定已测默认162 MHz性能/验证/压力、27 MHz应用/消融/ILA位流，以及原始UART、ILA CSV、分析波形和对应构建清单。损坏的162 MHz首轮压力记录也保留，并由报告明确标为拒绝样本。

2026-09-06 180 MHz实测后，打包清单增加三份已接受的寄存前递性能/验证/持续位流、五次完整UART与解析结果、启动会话及初始旧缓存排除记录，见 `HARDWARE_180MHZ.md`。此前已生成快照不会被覆盖，也不会自动包含本次新增内容，须生成新包。

不包含所有频率探索、未选入的其他load前递位流、所有外部ISA轨迹、完整GNU源码和软件安装目录；这些记录仍在原工作区。外部ISA包括两次汇总清单及其源输入哈希，不把汇总冒充全部轨迹原文。CoreMark上游C源与许可证作为参考副本保留，未包含其Git数据库。

## 校验与重建

可以在装有Python的系统上、不解压直接检查：

```text
python cpu/scripts/package_release.py --verify path/to/snapshot.zip
```

校验器拒绝条目缺失/多余、重复路径、路径穿越、符号链接、超限大小、哈希及长度不符；不会自动提取或执行ZIP中的内容。仅在校验通过后自行解压。SHA-256清单保证传输完整性，不提供签名身份认证；打包状态不能被改为“全部完成”后仍通过当前校验器。

复建需要Windows PDS及本地有效许可证、WSL Ubuntu-22.04、Icarus、Verilator、Python、GNU工具链。不要将他人的许可证或登录凭据放进包中。安装GNU工具链后运行 `validate.ps1`、`run_isa_tests.ps1` 与CoreMark两种短测。正式硬件构建见 `CLOCKING.md` 和 `COREMARK.md`。CoreMark构建器要求固定revision的干净Git工作区；包内参考副本不是已满足该门禁的离线仓库，需按构建脚本重新取得上游仓库，不能绕过revision检查。

历史PDS `build.tcl` 和manifest保留原绝对路径作为证据，不是换电脑直接双击的便携工程；迁移后使用 `run_pds.ps1` 从源码重新生成本机路径和新清单。新位流需要新的目标、哈希、时序与实板验证，不能继承旧位流分数。

## 资源与许可证边界

本项目原LICENSE原样收录，不自动改写用户修改。CoreMark上游LICENSE.md保留，GNU/PDS等依赖的许可证独立于本项目；包中不包含PDS厂商仿真库、安装程序或许可证文件。算法统计、位流和原始采集属于不同版本的证据，应按manifest匹配而非按文件名猜测。

打包只做文件身份与完整性门禁，不替代CoreMark CRC、ILA时序语义、PDS时序或实板功能验收。任何最终提交前仍需按 `ACCEPTANCE.md` 逐条复核，特别是最高频率、长期稳定性、GPIO按键、异步I/O和SCBV边界。
