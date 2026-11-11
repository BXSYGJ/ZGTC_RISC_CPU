# ---------------------------------------------------------------------------
# FTDI Auto-Heal (管理员守护脚本)
#
# 设计目标：无人值守时，FT2232H 掉线后自动恢复，不用人守着插拔。
# 注册为任务计划程序：登录时触发 + 每 5min 轮询 + 最高权限。
#
# 自愈策略由温和到激烈：
#   T0  若 VID_0403 present -> 直接退出，什么都不做
#   T1  杀僵尸 cdt_js + cdt_cfg（已握不住设备，安全）
#   T2  pnputil /scan-devices          (设备树全量重枚举)
#   T3  pnputil /restart-device xHCI   (PCIe USB 主控制器硬复位)
#   T4  pnputil /restart-device RootHub30 (USB 3.0 Root Hub 复位)
#   T5  pnputil /scan-devices + 等 20s
#   => 仍 absent -> 写 FATAL 日志退出（真的需要物理重插）
#
# 全部动作都写日志到 $LogDir，便于事后复盘。
# ---------------------------------------------------------------------------

$ErrorActionPreference = 'Continue'

$LogDir  = 'D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga\build\heal_logs'
$LogFile = Join-Path $LogDir 'ftdi_heal.log'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Msg)
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function FtdiCount {
    $n = (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
          | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count
    return [int]$n
}

function CdtJsAlive {
    return [bool](Get-Process cdt_js -ErrorAction SilentlyContinue)
}

function CdtJsPortOpen {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', 65420)
        $c.Close(); return $true
    } catch { return $false }
}

function Run-PnpUtil {
    param([string]$Action, [string]$DeviceId = '')
    if ([string]::IsNullOrEmpty($DeviceId)) {
        & pnputil.exe $Action 2>&1 | Out-Null
    } else {
        & pnputil.exe $Action "`"$DeviceId`"" 2>&1 | Out-Null
    }
    return $LASTEXITCODE
}

# ---- 0. 快速退出：设备 present 就啥也不做 --------------------------------
$present = FtdiCount
Write-Log "=== HEAL START  VID_0403 present=$present  cdt_js_alive=$(CdtJsAlive)  port_open=$(CdtJsPortOpen) ==="
if ($present -gt 0) {
    Write-Log "FTDI already present; nothing to do."
    exit 0
}

# ---- 1. kill zombie cdt_js / cdt_cfg --------------------------------------
$killed_js = $false
if (CdtJsAlive) {
    if (-not (CdtJsPortOpen)) {
        Write-Log "[T1] cdt_js alive but port closed -> zombie, killing."
        Get-Process cdt_js -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        $killed_js = $true
    } else {
        Write-Log "[T1] cdt_js alive AND port open -> still holding D2XX, skip kill."
    }
}
if (Get-Process cdt_cfg -ErrorAction SilentlyContinue) {
    Write-Log "[T1] killing cdt_cfg (any lingering burn process)."
    Get-Process cdt_cfg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
if ($killed_js -or (Get-Process cdt_js -ErrorAction SilentlyContinue)) {
    Start-Sleep 2
    if (Get-Process cdt_js -ErrorAction SilentlyContinue) {
        Write-Log "[T1] !! cdt_js still alive after kill; forcing."
        taskkill /F /IM cdt_js.exe /T 2>&1 | Out-Null
    }
}

# ---- 2. mild rescan --------------------------------------------------------
Write-Log '[T2] pnputil /scan-devices ...'
Run-PnpUtil '/scan-devices'
Start-Sleep 5
$present = FtdiCount
Write-Log "[T2] after rescan: VID_0403=$present"
if ($present -gt 0) { Write-Log 'HEAL OK at T2'; exit 0 }

# ---- 3. restart PCIe xHCI host controller (INTEL A36D) ---------------------
$xHCI = 'PCI\VEN_8086&DEV_A36D&SUBSYS_201F1043&REV_10\3&11583659&0&A0'
Write-Log "[T3] pnputil /restart-device xHCI ..."
Run-PnpUtil '/restart-device' $xHCI
Start-Sleep 4
Run-PnpUtil '/scan-devices'
Start-Sleep 5
$present = FtdiCount
Write-Log "[T3] after xHCI restart: VID_0403=$present"
if ($present -gt 0) { Write-Log 'HEAL OK at T3'; exit 0 }

# ---- 4. restart USB Root Hub 3.0 ------------------------------------------
$hub = 'USB\ROOT_HUB30\4&29FE64CB&0&0'
Write-Log "[T4] pnputil /restart-device RootHub30 ..."
Run-PnpUtil '/restart-device' $hub
Start-Sleep 4
Run-PnpUtil '/scan-devices'
Start-Sleep 10
$present = FtdiCount
Write-Log "[T4] after RootHub restart: VID_0403=$present"
if ($present -gt 0) { Write-Log 'HEAL OK at T4'; exit 0 }

# ---- 5. FATAL --------------------------------------------------------------
Write-Log '[FATAL] All software recoveries exhausted. FT2232H requires physical re-plug.'
exit 1
