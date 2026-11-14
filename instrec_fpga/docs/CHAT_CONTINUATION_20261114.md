# Revise CPU paper for reviewers (2)：接续记录

2026-11-14，已从本机只读对话历史和实际工作区恢复当前工作。

源对话ID：`01a192cc-2454-7771-8394-1f3fb567e0f9`。当前仓库为 `D:/AAAFPGA/ZGTC_RISC_CPU_XSY`，分支 `XSY`，活动目录为 `instrec_fpga`。接续前HEAD为 `80bcfa360bc1baf6a2a5732a9b578042a7f90381`；原整机比较基线为 `852f067db4a4a710f5355e3ab311f035ced5b48d`。

## 当前任务

对话已经从论文修订推进到100Pro+音频整机集成。最新有效要求是采用“高性能PaceRV核心＋共享整机存储和外设”，并完成PG2L100H-6IFBG676本地PDS完整构建和快慢角时序验收。用户已取消远程上板，允许适度降频，要求继续设法使时序合格。

当前候选系统时钟109.375MHz、像素148.5MHz、音频48kHz。权重校验在S_RD_SET寄存digest_q/rdigest_q，S_RD_CHK比较并输出摘要；GAP使用256项32位显式寄存器和共享加法器。生产源码保留这两项修改。

## 实际中断点

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

从当前源检查GAP显式寄存器组的映射占用和路由状态，建立新的独立冻结run并继续物理验收。035340缺少RESULT.json，现有--restart入口要求该文件，直接调用会在启动前失败；新run保留原中断记录。旧025700的93.75MHz快照未含最新GAP和摘要修改，采用该档时须重新准备并重跑相应音频、UART、回退和输入哈希检查。

最终验收继续要求十张时序汇总表、Design Summary、实际系统/像素时钟、0.150ns及以上实际路径预算、冻结输入和位流一致。验证通过后更新STATUS、CHANGELOG、交接记录并本地提交XSY。当前无活跃PDS。

复用接续提示：

```text
继续 D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga 的 PaceRV 共享音频整机任务。
先读 AGENTS.md、docs/STATUS.md 和 docs/CHAT_CONTINUATION_20261114.md。
已完成CPU集成和功能验证；最新035340构建因7200秒时限中断，无最终时序报告和位流。
保留digest_q/rdigest_q与GAP显式寄存器修改，从当前源码建立新的冻结PDS工程，完成100Pro+本地快慢角时序验收。
仅后台运行；每次一个PDS；保留历史输入与日志；更新状态和本地提交，不push。
```
