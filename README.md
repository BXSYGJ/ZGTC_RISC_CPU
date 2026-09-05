# ZGTC_RISC_CPU

面向全国大学生 FPGA 创新设计竞赛紫光同创赛道选题一的 RISC-V CPU 项目。

## DYH 分支

`DYH` 是个人开发分支。当前首先建立 PG2L200H 目标器件、MES2L676-200HP 板卡、
WSL 仿真与 PDS 实现流程的可复现基线；CPU 微架构、指令系统和验证平台将在后续提交中
逐步加入。当前内容不代表 CPU 已经完成。

## 目录

| 路径 | 内容 |
| --- | --- |
| `pds_minimal_blink_200h/` | 已通过仿真、PDS 全流程和远程实板验证的双向流水灯基线 |

最小例程的环境要求、引脚定义、运行命令和验证结果见
[`pds_minimal_blink_200h/README.md`](pds_minimal_blink_200h/README.md)。

## 开发约定

- 日常开发与验证提交到 `DYH` 分支。
- RTL、testbench、约束和可复现脚本纳入版本控制。
- PDS 数据库、中间产物、日志、仿真输出、位流及本地许可证不提交。
- 合并前至少执行 RTL 自检；涉及器件实现的修改还应完成 PDS 时序检查。

## 许可证

本仓库采用 [MIT License](LICENSE)。
