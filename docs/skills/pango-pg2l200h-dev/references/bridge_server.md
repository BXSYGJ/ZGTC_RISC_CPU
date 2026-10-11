# 桥接服务器：把 FPGA LAB 远程调试变成纯接口/CLI

位置：`D:\0000\111\001\Pango\tool\fpga_lab\`（README、CLI、脚本齐全）。

此前"远程调试"= 人工网页操作。桥接服务器把平台封装成本地 REST + WebSocket + `remote-lab` CLI：
开发完 `generate_bitstream/<top>.sbit` 后，一条命令预约、烧写、串口收发，全程不碰网页。

## 快速上手（他人新机器也可照此用）

前提：Python 3.10+（`fastapi/uvicorn/httpx/websockets/click` 已装）；账号文件含两行（邮箱、密码），默认读
`../account.txt`，换机器可用环境变量 `FPGA_LAB_ACCOUNT` 指向别处。桥接不需要 PDS/WSL。

```powershell
# 1) 起服务（前台专用终端；后台跑注意 120s 会被杀，须用 600000ms 超时）
pwsh -File D:\0000\111\001\Pango\tool\fpga_lab\scripts\run_server.ps1
#    等价：cd fpga_lab && python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600
#    首次调用自动读账号 native 登录，token 落 sessions/（gitignored），密码不下盘

# 2) CLI（任意目录可用包装器；等价 python -m fpga_lab_server.cli …）
D:\0000\111\001\Pango\tool\fpga_lab\remote-lab.cmd health
remote-lab.cmd devices
remote-lab.cmd reserve --minutes 10
remote-lab.cmd bitstream <.../top.sbit>
remote-lab.cmd serial-send --hex A5 --timeout 5
remote-lab.cmd release
```

（可选）`cd fpga_lab && pip install -e .` 后直接用 `remote-lab` 命令，效果同 `remote-lab.cmd`。

## 状态（如实记录，2026-09-07 已实机验证）
- 本地已验证：PDS 批处理 → `.sbit`。
- 远程已验证（真实 PG2L200H 实验箱）：native 登录 → `request-by-type` 预约（自动分配 with_camera 箱）
  → multipart 烧录（平台回报"固件下载完成且设备已唤醒"）→ serial open(115200 8N1) → 发 `A5`/`help`
  → **收到实板 SoC UART 返回的 `?>` 监控提示符** → release。
- 验证证据脚本：`fpga_lab/scripts/smoke_test.py`（release 放 finally，必然释放设备）。

## 串口链路事实（2026-09-07 原生+桥接双路钉死）
- **坏箱（平台侧）**：实验箱9(id59) 烧录后板子复位丢程序（open 409"板上还没有你的程序"）；gateway 192.168.2.31(id61) 串口仪器 RX 不送（open 后仅 8 字节即静默）。
- **好箱**：实验箱1/2/3/4/5/7、gateway .32 等，信标连续字节稳定收到（20s 读数 27 次满 64B）。
- **干扰源**：桥接服务器进程一断，测试立刻"连接被拒/FAIL"，会伪装成串口时好时坏。服务器务必前台专跑或长超时后台；Start-Process 分离启动在会话结束会被连带杀掉。
- **全 0x00 两义**：平台无数据空读回 allZeroPayload 占位（交互固件空闲也触发）≠ 一定断链；判定统一用信标仲裁。
- **标准做法（信标门）**：`python scripts/serial_session.py --firmware <user.sbit>` 内部先烧 uart_beacon 验证该会话串口真的收到字节，坏箱/坏会话自动释放重约，通过才烧你的固件并开串口（finally 必释放）。
- 辅助：`check_serial.py` 测当前箱；`targeted_serial_check.py --targets 59 61` 指定箱多次采样；`debug_serial_raw.py`/`native_target.py` 原生直连排障。

REST 等价：`GET /api/v1/{health|devices|current}`、`POST /api/v1/devices/{reserve|release}`、
`POST /api/v1/bitstream`(multipart `file`)、`WS /ws/serial?baud=115200`。

## 平台建模要点（务必记住）
- 平台**按类型自动分配**实验箱（`cardType: with_camera`，时长 10/20/30 min），账号同时只持有一台
  **current device**。因此桥接 API 没有 box_id 预约语义，围绕"当前设备"建模。
- serial open 前必须先烧好含 UART 的固件（否则平台 409"板上还没有你的程序"）。RemoteLab UART =
  RX AC26 / TX AB26，115200 8N1；`blink`（LED）无 UART，串口仅能验证开/关。
- 登录返回 JSON token；所有 API 带 `Authorization: Bearer <token>`；`sessions/` 持久化 token，绝不存密码。
- 平台单会话：新登录会使旧浏览器会话失效（本地脚本别把旧 storage state 当长期凭证）。
- 完整契约：`fpga_lab/captures/api_contract.json`。

## 诚实边界
- 本服务器作者**实际执行过**上面第"远程已验证"整条链路；但 SoC 固件交互仅拿到 `?>` 监控提示符，
  DYH 记录的 `ZSOC PASS` 需精确菜单交互，尚未在桥接链路复现——不要声称已复现 ZSOC PASS。
- 摄像头画面、示波器、ILA 仍属人工网页流程，未做桥接（v1 范围外）。
- 平台为网页 SPA，若其 REST/WS 变更导致桥接失效，先重新抓包（契约文件 + `platform.py` 数据驱动），
  再改代码。
