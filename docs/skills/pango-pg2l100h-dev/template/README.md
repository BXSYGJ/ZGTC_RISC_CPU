# 盘古 100Pro+（MES2L676-100HP）最小 PDS 全流程例程（模板）

本模板验证 **PG2L100H-6IFBG676**、盘古 100Pro+（MES2L676-100HP）开发板的
「建工程 → 综合 → 实现 → 生成位流 → JTAG 下载 → 上板」全流程。**不含 RISC-V CPU**。
用法与说明见技能根目录 `../SKILL.md` 与 `../references/`。

## 功能

8 个 LED 每 0.5 秒移动一次；KEY0 低电平复位，KEY1 松开向高位、按下向低位移动。

| 信号 | 功能 | 管脚 |
| --- | --- | --- |
| `clk` | 27 MHz | D18 |
| `rst_n` | KEY0 低有效 | C22 |
| `key` | KEY1 低有效 | C23 |
| `led[0..7]` | 高电平点亮 | A20/C18/C19/E18/A17/A18/C17/B17 |

## 运行

环境：Windows PDS 2022.2-SP6.4（`PDS_ROOT`）+ 有效许可证（`PANGO_LICENSE_FILE`）+ USB Cable II。
本机**无 WSL / 无 Icarus**，`sim/` 仅供登记，不在本机跑仿真。

```powershell
# 1) 综合 → 实现 → 生成位流
pwsh -NoProfile -File .\scripts\run_pds_full.ps1
# 产出：generate_bitstream/blink_top.sbit

# 2) 下载（二选一）
#    GUI：PDS → Tools → Configuration → Scan Device → 选 sbit → 右键 Program
#    CLI：先打开 PDS Configuration 拉起 jtagserver(65420)，再
#         cdt_cfg.exe -file .\scripts\program_full.tcl
```

## 已验证基线

- PDS 六阶段成功，生成 `blink_top.sbit`（约 3.79 MB），setup WNS 34.379 ns MET。
- 位流已下载到盘古 100Pro+ 板，**8 个 LED 跑马灯运行**（2026-10-11）。
- `gen_bit_stream` 出现 `SCBV has not been set` 为原厂正常提示，非错误。
