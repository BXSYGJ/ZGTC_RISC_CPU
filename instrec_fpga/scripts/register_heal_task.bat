@echo off
:: ---------------------------------------------------------------------------
:: 一键注册 FTDI 自愈守护任务计划
::
:: 用法：右键 -> "以管理员身份运行"，跑一次就行，以后永久自动恢复。
:: 注册完成后，Windows 任务计划程序里会多一个叫
::   "FTDI Auto-Heal (instrec)" 的任务，行为：
::     1. 用户登录 30 秒后自动跑一次；
::     2. 之后每 5 分钟跑一次；
::     3. 始终以最高权限运行（T3/T4 的主机控制器复位必须管理员）；
::     4. 设备 present 就直接退出，什么都不做——无副作用。
::
:: 想卸载：schtasks /Delete /TN "FTDI Auto-Heal (instrec)" /F
:: 想看状态：schtasks /Query /TN "FTDI Auto-Heal (instrec)" /V /FO LIST
:: 想手动触发：schtasks /Run  /TN "FTDI Auto-Heal (instrec)"
:: ---------------------------------------------------------------------------
setlocal
set "SCRIPT=D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga\scripts\ftdi_heal_admin.ps1"
set "TASK=FTDI Auto-Heal (instrec)"

:: --- step 1: elevate ------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting elevation...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo =========================================
echo  Registering FTDI auto-heal task plan
echo  Script: %SCRIPT%
echo  Task  : %TASK%
echo =========================================
echo.

:: --- step 2: create (ONLOGON + delay + highest) ---------------------------
schtasks /Delete /TN "%TASK%" /F 2>nul
schtasks /Create /TN "%TASK%" /SC ONLOGON /DELAY 0000:30 /RL HIGHEST ^
    /TR "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%SCRIPT%\"" /F
if errorlevel 1 (
    echo !! create ONLOGON trigger FAILED
    pause
    exit /b 1
)
echo [OK] ONLOGON trigger registered

:: --- step 3: add a every-5-minute trigger ---------------------------------
schtasks /Change /TN "%TASK%" /SC MINUTE /MO 5 /ST 00:05
if errorlevel 1 (
    echo !! add MINUTE trigger FAILED (non-fatal; ONLOGON still works)
) else (
    echo [OK] every-5-minute trigger registered
)

:: --- step 4: verify -------------------------------------------------------
echo.
echo --- registered task definition ---
schtasks /Query /TN "%TASK%" /V /FO LIST
echo.
echo Done.  You can close this window.
echo The task will now auto-heal the FTDI dongle whenever it drops.
echo.
pause
