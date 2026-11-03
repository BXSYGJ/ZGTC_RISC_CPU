# UI ASCII 查表去重评估（DRM 优化 R1 项）

日期：2026-11-04
范围：只评估、不改生产 RTL（评估对象 `src/ui/dashboard_text.v`、`src/ui/demo_dashboard_text.v`，均为只读参考）
数据源：`reports/drm_storage_audit_20261103.json`（构建 `20261103-152639-fb2ffc99`，基线位流 `1497FAF4`）

## 1. 现状：端口数与复制数

`dashboard_text.v`（及同构的 `demo_dashboard_text.v`）持有 ASCII 索引表：

```verilog
reg [7:0] ascii_ids [0:127];          // 128 x 8b, $readmemh 初始化, 无运行时写
```

它只服务一件事：`format_percent()` 组合函数把百分比数字/空格/连字符的 ASCII 码换算成显示字符 ID：

```verilog
format_percent = {ascii_ids[37], ascii_ids[ones], ascii_ids[tens], ascii_ids[hundreds]};
```

读口需求（每像素时钟拍）：

| 读口 | 索引性质 | 数量 |
|---|---|---|
| `ascii_ids[ones]` / `[tens]` / `[hundreds]`（8 个 `formatted_pct` lane 并行） | 可变索引 | 8 lane × 3 = **24 个** |
| `ascii_ids[37]`（常量 `'%'`） | 常量 | 优化为常量，不占端口 |

PDS 对 `$readmemh` 初始化的 `reg` 数组推断为 DRM，每个推断实例仅提供 2 个读端口；24 个可变读口 ÷ 2 端口/份 = **12 份复制**。审计日志 `u_ui_renderer/u_text/` 下实测：

```
ascii_ids_24 .. ascii_ids_35   12 x 0.5 DRM36K = 6.0 DRM36K 当量（12 个 DRM18K）
```

即：128 字节（1 Kb）的数据被复制成 12 份 18Kb DRM，占用 `u_ui_renderer` 组（12.0）的一半、全设计 150.5/155 的 **4.0%**。这是组内最大的单项浪费（font_bits 4.0、tiles_2_concat_2 2.0 均低于它）。

## 2. 根因

- `formatted_pct` 的 8-lane for 循环写在 `always @(posedge pix_clk)` 里，每拍对 8 个 lane **并行**求值 `format_percent`；
- ASCII→glyph ID 的映射因此落在**像素扫描路径**上，迫使综合器以端口数为准复制 ROM；
- 本质是「格式化（事件级计算）被放进了像素级渲染」——百分比每帧最多变 8 个值，却在 74.25 M pix/s 的路径上做了 24 次查表。

## 3. glyph-ID 预格式化方案

核心思路：**把 ASCII→glyph ID 的转换从像素时钟域移到数据准备级，像素侧只剩单端口读 glyph ID**。

### 方案 A（推荐，顺 UI Scene ABI 路线）：CPU 侧预格式化

新的软件定义 UI（`src/ui_scene/`，本工作包已落地）即为此形态：

- `ui_scene_table.v` 的 glyph 序列 RAM（512 × 8b，双 bank）存的就是 **glyph ID**，由 CPU 在写场景时直接写入（软件侧完成 ASCII→ID 转换）；
- 像素流水（`ui_scene_render.v` stage 1）对 glyph 序列 RAM 只有 **1 个读口**（每像素至多一次 `glyph_ptr + char_idx` 查询），推断 1 份 LUTRAM/DRM 即可，无复制；
- 字模 ROM（4096 × 16b）同样是单端口同步读。

`ascii_ids` 这类映射表在新 ABI 下不存在——它被 CPU 的格式化代码取代（改字/改布局不再重综合）。

### 方案 B（过渡方案，不动 ABI、救现有 dashboard）：事件级预格式化寄存器

`percentages` / `result_ready` / `class_idx` 是**帧级/事件级**输入，只有变化拍才需要重算。把 8 lane × 4 字符的 `format_percent` 结果搬到一个事件级进程：

```verilog
// result/percentage update domain (one shot per change, not per pixel)
reg [7:0] pct_glyphs [0:31];          // 8 lane x 4 glyph id, 256 FF, no RAM
always @(posedge pix_clk)
    for (lane = 0; lane < 8; lane = lane + 1)
        pct_glyphs[lane] <= format_percent(percentages[...], ...);
```

像素路径改为纯 mux（`slot`/`tile_s1[1:0]` 选择 glyph ID 常量选择器），`ascii_ids` RAM **整体删除**：12 × 0.5 = 6.0 DRM36K → 0。代价是 32 × 8b = 256 个 FF 加一级寄存（视频延迟不变——该寄存器替换的是原有的 `formatted_pct` 寄存器组，级数相同）。

`class_ids`（256 × 8b，索引 `{class, char}`）是单读口，推断 1 份，不在去重范围；如需进一步收敛可走同一思路（result_ready 拍把 top-1 类名 32 字符锁进 FF）。

## 4. 预期 DRM 节省（对照 drm_storage_audit_20261103.json）

| 项 | 现状 | 方案后 | 节省 |
|---|---|---|---|
| `u_ui_renderer/u_text/ascii_ids_*`（12 份 DRM18K） | 6.0 DRM36K 当量 | 0（方案 A：表不存在；方案 B：删除） | **6.0** |
| `u_ui_renderer` 组 | 12.0 | 6.0 | -50%（组内） |
| 全设计 | 150.5 / 155（97.1%） | 144.5 / 155（93.2%） | -4.0%（全局） |

全局余量从 4.5 提升到 10.5 DRM36K 当量。当前 DRM 已经 97.1%，这 6.0 是 M5 之后放回 spec/bars 扩展空间的最低成本来源之一。

## 5. 迁移风险清单（方案 B，现有 dashboard 路线）

1. **位级等价**：`format_percent` 的 clamp（>100→100）、valid=false 显示 `--`、100 显示 `1 0 0`、个位补空格等特判必须逐 bit 保持，否则 `dashboard_ui` / `demo_dashboard` 两个 TB 的期望全变。
2. **事件级触发**：预格式化的锁存条件是 `percentages`/`result_ready`/`class_idx` 变化（或每 vsync 一拍），需要新写一个变化检测；锁存前一拍像素路径读到旧值属于可接受的帧内过渡，但必须保证复位后初值为 `--` 状态。
3. **双份同构代码**：`dashboard_text.v` 与 `demo_dashboard_text.v` 是两份拷贝，必须同步修改，否则 demo 与正式 UI 行为分叉；理想做法是先合并为一个参数化模块再改。
4. **TB 覆盖**：`tb_dashboard_ui.sv` 断言了 RAM 几何（`ascii_ids` 深度/内容），删表后该断言要改为断言 `pct_glyphs` 寄存器值；`tb_demo_dashboard.sv` 的 5 帧光栅期望需重跑比对。
5. **综合推断不确定性**：删掉 RAM 后 24 个读口变成 mux 树（约 200 LUT 量级），需复查 WNS（当前 +1.443，余量充足）；PDS 对 FF 阵列的初始化（`$readmemh` 不再适用）需要 initial 块或复位值覆盖。
6. **上板回归**：UIDEMO / M4 位流需重新构建烧写，肉眼比对 dashboard 百分比 lane 的显示（含 0%、100%、invalid `--` 三态）。

方案 A 没有上述风险——它不触碰 `src/ui/` 现有文件，只是在新 UI 路线上不再复制该模式；旧 dashboard 按需再决定是否做方案 B。

## 6. 结论

- 12 份 `ascii_ids` 复制的成因 = **8-lane 并行 format_percent 的 24 个可变 RAM 读口** ÷ 2 端口/实例，纯像素域查表所致；
- 新 `ui_scene` 实验模块已按单端口 glyph-ID 预格式化形态实现（CPU 写 glyph ID，像素侧单口读），可作为方案 A 的参考实现；
- 若在现有 dashboard 上实施方案 B，可确定性节省 6.0 DRM36K 当量（全设计 -4.0%），风险集中在 format_percent 位级等价与双份同构代码同步。
