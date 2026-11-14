# Revise CPU paper for reviewers (2)：接续记录

> 当前接续任务已推进为125MHz基线FreeRTOS接入。rtos/README.md为构建入口；官方V11.3.3、真实抢占调度和三应用任务已落地，CPU/完整NPU/回退实测通过。整机map通过，PNR20988正在生成RTOS位流；工程build/rtos/pds/20261114-153018-rom_loop_fix-map，continuations/20261114-074722-356866。恢复时先检查真实PID及FULL_RESULT，保留运行实例。目标active，原时序优化paused。板卡USB目前未枚举，尚未进行板级测试。以下保留先前接续历史。


2026-11-14，已从本机只读对话历史和实际工作区恢复当前工作。

源对话ID：`01a192cc-2454-7771-8394-1f3fb567e0f9`。当前仓库为 `D:/AAAFPGA/ZGTC_RISC_CPU_XSY`，分支 `XSY`，活动目录为 `instrec_fpga`。接续前HEAD为 `80bcfa360bc1baf6a2a5732a9b578042a7f90381`；原整机比较基线为 `852f067db4a4a710f5355e3ab311f035ced5b48d`。

## 当前任务

最新应用方向已明确：用户参加紫光同创赛题一，目标是交响乐中同时出现的乐器及其进入/退出；CPU相关工作按用户要求已完成。已只读核验GitHub XSY/XSY2，找到现有五组多标签双头模型，XSY还保存INT8契约、权重和完整历史离线评估。复用入口为SYMPHONY_GROUP5_CODE_AUDIT_20261114.md；RTOS仅处应用方案评估阶段。

对话已经从论文修订推进到100Pro+音频整机集成。用户最新要求是：当前一轮完成后停止时序优化，选用已有125MHz和约109.5MHz中违例较小的版本。该档实际为109.375MHz。原持续时序验收目标已按用户要求设为paused。

使用入口见[所选版本](SELECTED_BUILD_VERSIONS_20261114.md)：109.375MHz主选021145，125MHz备选223256。两个包各包含原位流、202份冻结输入及最终时序报告，ZIP逐文件哈希验证通过。当前83.333333MHz工作区另行保留。最后一轮133421已结束，719.426秒、exit1：500ps时钟树hold修复参数超出工具0至200ps范围，compile/synthesize/dev_map完成，pnr/report_timing/gen_bit_stream未执行，无新位流；全部202份冻结输入未变。当前PDS进程0，时序构建到此结束。

## 最初接续时的中断点（历史）

最新run为 `build/pacerv_shared_system/pds/full-20261114-035340-full`。原对话最后命令ordinal92842记录监督退出1、耗时7202547ms，7200秒时限触发。PDS实际子进程退出码未记录。

| 检查 | 实际结果 |
|---|---|
| compile / synthesize / dev_map | 完成 |
| 详细布线 | 第587轮中断，最后未布线子网2607 |
| pnr / report_timing / gen_bit_stream | 未完成 |
| 最终时序报告 / 位流 | 均未生成 |
| 冻结输入 / 当前输入 | 202份冻结哈希正确，202份当前输入全部匹配 |
| 当前PDS进程 | 0 |
| 物理资格 | `interrupted_timeout`，`qualified=false` |

原日志和冻结文件全部保留。恢复证据为 [CONVERSATION_RECOVERY_20261114.json](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/experiments/pacerv_shared_system/evidence/CONVERSATION_RECOVERY_20261114.json)，包含原命令、字面输出、监督退出状态、202份输入哈希及日志哈希。collector核对中断证据后，将其状态写入正式验证记录。

## 本轮实测

工作目录为 `D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga`。

| 模式 | 输入 | 原样结果摘录 | 退出状态 |
|---|---|---|---|
| BASELINE CPU | Git 852f067原RTL及prog.hex | `RV32 BENCH cycles=460012 inst=180008 acc=0xf2d8888b`；`RESULT: PASS` | 0 |
| MODIFIED CPU | 相同prog.hex、新H3核心及IMC/反压/取指异常用例 | `RV32 BENCH cycles=180016 inst=180008 acc=0xf2d8888b`；`PACERV_CHECKS_PASS cases=4 vendor_hashes=8` | 0 |
| ROLLBACK CPU | 从当前修改生成独立副本，恢复31份原文件 | `INTEGRATION_ROLLBACK_PASS files=31 cycles=460012 retired=180008 live_modified_unchanged=1` | 0 |
| BASELINE loader/GAP | 021145冻结输入 | `LOADER_GAP_BASELINE_PASS checksum_corruption=1 gap_outputs=768 live_unchanged=1` | 0 |
| MODIFIED loader/GAP | 当前摘要寄存级及GAP显式寄存器 | `LOADER_GAP_MODIFIED_PASS checksum_corruption=1 gap_outputs=768 live_unchanged=1` | 0 |
| ROLLBACK loader/GAP | 独立副本恢复021145冻结字节 | `LOADER_GAP_ROLLBACK_PASS checksum_corruption=1 gap_outputs=768 live_unchanged=1` | 0 |

权重每组13项检查通过，覆盖完整8字符摘要、CRC拒绝及DDR数据损坏检测；GAP每组3帧、768输出及768读回通过，覆盖停顿、偶数舍入和最大输入255。原始31份整机文件回退恢复了460012周期行为；活动工作区保留新实现。两个基线的来源和哈希分别记录，021145控制实验基线与Git 852f067整机基线各自保存。

精确命令如下；详细编译与仿真命令、输入哈希、完整字面输出和退出状态均写入VERIFICATION.txt。

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $taskRoot = [System.IO.Path]::Combine('D:', 'AAAFPGA', 'ZGTC_RISC_CPU_XSY', 'instrec_fpga')
    $taskScripts = [System.IO.Path]::Combine($taskRoot, 'experiments', 'pacerv_shared_system')
    Push-Location -LiteralPath $taskRoot
    try {
        & python ([System.IO.Path]::Combine($taskScripts, 'run_baseline_cpu.py'))
        if ($LASTEXITCODE -ne 0) { throw 'BASELINE CPU failed' }
        & python ([System.IO.Path]::Combine($taskRoot, 'sim', 'experiments', 'pacerv_integration', 'run_pacerv_checks.py'))
        if ($LASTEXITCODE -ne 0) { throw 'MODIFIED CPU failed' }
        & python ([System.IO.Path]::Combine($taskScripts, 'run_integration_rollback.py'))
        if ($LASTEXITCODE -ne 0) { throw 'ROLLBACK CPU failed' }
        # Each label identifies a new isolated study directory.
        $studyLabel = 'continuation_' + [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')
        foreach ($mode in @('BASELINE', 'MODIFIED', 'ROLLBACK')) {
            & python ([System.IO.Path]::Combine($taskScripts, 'run_loader_gap_timing.py')) --mode $mode --label $studyLabel
            if ($LASTEXITCODE -ne 0) { throw "Loader/GAP $mode failed" }
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_
    exit 1
}
```

额外完成时序验证器6项测试与81个RTL文件词法检查，全部通过。collector核对现有完整NPU、显示、音频、UART及DDR证据的生产源哈希；NPU全层golden一致，31,152,093周期，331次CPU DDR请求/返回。当前13项门槛中12项通过，尚待完成的门槛为 `full_pds_qualified`。

## 四件交付

| 名称 | 路径 |
|---|---|
| MODIFIED_FILE | [MODIFIED_FILE.sv](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/experiments/pacerv_shared_system/MODIFIED_FILE.sv) |
| DIFF_FILE | [DIFF_FILE.patch](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/experiments/pacerv_shared_system/DIFF_FILE.patch) |
| VERIFICATION | [VERIFICATION.txt](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/experiments/pacerv_shared_system/VERIFICATION.txt) |
| ROLLBACK | [ROLLBACK.sh](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/experiments/pacerv_shared_system/ROLLBACK.sh) |

ROLLBACK.sh为UTF-8 BOM PowerShell源码，Git模式100755；常规PowerShell入口为同目录ROLLBACK.ps1。实际回退测试由pwsh读取并执行ROLLBACK.sh，仅操作带标记的独立副本。

## 后续工作

当前一轮已归档，后续使用已选109.375MHz和125MHz包。保留每包自己的RTL、IP、HEX和约束；当前83.333333MHz工作区作为实验记录保留。

本次交付以旧位流、最终原始报告和202份冻结输入一致为核验依据。持续时序验收目标保持paused；后续按用户的新工作要求继续。历史验收记录保存其原始结果。

复用接续提示：

```text
继续 D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga 的 PaceRV 共享音频整机任务。
先读 AGENTS.md、docs/STATUS.md 和 docs/CHAT_CONTINUATION_20261114.md。
用户已要求停止时序优化，原持续时序验收目标为paused。
当前聚焦赛题一交响乐识别应用，用户确认目标为同时活跃乐器及进入/退出；CPU工作已完成。
先读docs/SYMPHONY_GROUP5_CODE_AUDIT_20261114.md，复用已有五组双头模型、XSY量化权重及离线验证成果。
当前核验结果为窗口级五大乐器组识别，板端迁移与进入/退出时间事件尚待实现；RTOS仍在方案评估。
133421已在pnr入口因500ps参数超出0至200ps范围退出1，无新位流；当前PDS进程0。
先读docs/SELECTED_BUILD_VERSIONS_20261114.md；主选109.375MHz的021145，125MHz备选223256。
所选ZIP在build/pacerv_shared_system/selected_versions_20261114，各含原位流、202份冻结输入和原最终报告。
按各包内的RTL/IP/HEX/约束使用对应版本；当前83.333333MHz源码保留为实验记录。
接续用户后续工作，保持后台操作，保留历史记录；更新状态并本地提交XSY。
```
