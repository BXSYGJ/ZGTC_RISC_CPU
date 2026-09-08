# fpga_lab bridge server

把 `logicmatrixsemi.com:5174`（FPGA LAB 远程实验平台）的调试变成**纯接口/命令行**操作：
本地 PDS 生成 `.sbit` 后，用本服务预约一台 PG2L200H 实验箱、烧写位流、开串口收发，全程不碰网页。

## 已验证（2026-09-07 实机）
- 纯 native（无浏览器）登录 → 预约（with_camera 自动分配 PG2L200H 箱）→ multipart 烧录
  `pds_soc_top.sbit`（SHA-256 `569CE77A...`，平台回报"固件下载完成且设备已唤醒"）
  → serial open(115200 8N1) → 发送 `A5`(hex) / `help`(text) → **收到实板 SoC UART 返回的 `?>` 监控提示符** → release。
- 冒烟脚本：`python scripts/smoke_test.py`（release 在 finally，必然释放）。

## 启动
```powershell
cd tool/fpga_lab   # 从工作区根目录
python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600
# 首次调用会读 account.txt 自动 native 登录并持久化 token 到 sessions/platform_session.json
```

## CLI（等价 REST）
```bash
python -m fpga_lab_server.cli health
python -m fpga_lab_server.cli devices
python -m fpga_lab_server.cli reserve --minutes 10
python -m fpga_lab_server.cli bitstream blink_top.sbit
python -m fpga_lab_server.cli current
python -m fpga_lab_server.cli release
python -m fpga_lab_server.cli serial-send --hex A5 --timeout 5     # 走 /ws/serial
```
也可直接 curl REST：`GET /api/v1/health | devices | current`，`POST /api/v1/devices/reserve|release`，
`POST /api/v1/bitstream`(multipart file)，`WS /ws/serial?baud=115200`。

## 说明 / 边界
- 平台是**按类型自动分配**设备（`cardType: with_camera`，时长 10/20/30 分钟），账号同时只持有一台
  "current device"，所以本服务围绕"当前设备"建模（reserve 无 box_id）。已在 `captures/api_contract.json`
  记录完整契约。
- serial open 前必须已在板上烧录含 UART 的固件（否则平台 409）。RemoteLab UART = RX AC26 / TX AB26，
  115200 8N1；普通 blink 无 UART，串口只能验证开/关，功能验证用带 UART 的 SoC 位流。
- 并发：serial 单会话（第二个连接 1008 拒绝）；服务器进程被杀/120s 超时会断开——长任务用
  `timeout 600000` 后台启动。
- 凭据只在 `account.txt`（gitignored），服务器登录一次存 token（sessions/ gitignored）；不要把密码写进代码/日志。

## 目录
- `fpga_lab_server/app.py` REST+WS；`platform.py` native HTTP 客户端；`cli.py` 命令行
- `scripts/smoke_test.py` 实机冒烟；`scripts/serial_session.py` **标准串口入口（信标门，自动换健康会话）**；
  `scripts/check_serial.py` 当前箱信标检查；`scripts/targeted_serial_check.py` 指定箱多次采样
- `test_designs/uart_beacon/` 串口信标位流（持续 115200 8N1 发字节流，判定串口桥是否送达 RX）
- `captures/api_contract.json` 契约（不含密钥）
- `blink_top.sbit` / `pds_soc_top.sbit` 本地测试位流

## 串口健康（2026-09-07 实测钉死）
原生+桥接双路多轮：**实验箱9(id59)** 烧录后板子复位丢程序（open 409）；**gateway 192.168.2.31(id61)**
串口仪器 RX 不送；其余实验箱1/2/3/4/5/7、gateway .32 信标均稳定 PASS。测试中服务器进程被工具杀掉会
造成假 FAIL（"连接被拒"），务必长超时后台/前台专跑。判定统一用 `test_designs/uart_beacon` 信标连续字节，
**标准入口**：`python scripts/serial_session.py --firmware your.sbit`（坏箱/坏会话自动释放重约，finally 必释放）。

## ram_load.py — 流控载 RAM 运行（推荐）

`ram_load.py` 是当前推荐的程序加载命令。它通过桥接服务 WebSocket 串口，用**逐块发 256 字节 + 等 K 回执**的流控方式将 `.bin` 发送到板载 bootloader 的 `R` 命令（载 RAM 直接运行），避免了旧脚本盲发导致的串口缓冲溢出丢字节问题。

```bash
# 从工作区根目录运行：
python tool/fpga_lab/ram_load.py                                    # 默认载 app_big.bin（13KB）
python tool/fpga_lab/ram_load.py cpu/build/app_huge.bin             # 载 33KB 大文件
python tool/fpga_lab/ram_load.py cpu/build/app_fib.bin              # 载斐波那契测试程序
```

流程：找健康实验箱 → 烧 SoC 固件位流 → WebSocket 连串口 → 流控发 R 命令 + .bin → 读回板子输出。

> ⚠️ `--flash` 走 W 命令写 U9 Flash，当前板子受 H13 专用引脚限制不可行（报 ERR erase）。详见 `cpu/docs/FLASH_BOOT.md`。
