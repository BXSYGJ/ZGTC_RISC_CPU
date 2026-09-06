# 远程数字孪生与SCBV边界扫描核查

日期：2026-09-06。此轮为只读核查，没有申请设备、启动扫描、驱动引脚或烧录。当前没有真实SCBV采样值。本页不构成配置电压审核通过，也不把数字孪生按键等同于机械按键。

## 器件原始依据

本机PDS附带的纯文本BSDL文件：

```text
D:/PDS_2022.2-SP6.4/arch/vendor/pango/logos2/common/tile_based/valence/parts/pg2l200h/bsm/PG2L200H_FBB676.bsm
SHA256 E2379C425EBA0F9FFDEAF7A73AC923AE9D8EB715C2274BB635C7E895AEBA48FD
```

| 信号 | 封装引脚 | 边界扫描数据单元 | 来源说明 |
| --- | --- | --- | --- |
| SCBV | AB15 | 0 | input，BC_2；文件第2636行 |
| 平台KEY1 / L3_PAD38 | C23 | 846 | bidir，控制单元845；第1790行 |
| 远程UART_RX / L6_PAD6 | AC26 | 14 | bidir，控制单元13 |
| 远程UART_TX / L6_PAD5 | AB26 | 12 | bidir，控制单元11 |

第1556行给出BOUNDARY_LENGTH=1079；注释说明单元0最接近TDO。第1471–1474行分别给出PRELOAD/SAMPLE=`1010000000`、EXTEST=`1010000001`。这些是BSDL指令字面值，不是已经核实的远程JTAG发包参数，不能据此直接猜测后端API。

**更正证据边界：SCBV并非没有扫描单元；缺失的是网页前端PG2L200H数据单元映射表中的SCBV条目。** 器件BSDL明确具有单元0。BSDL中的输入方向也不能说明远程核心板把该脚接到哪一条电源网络。

## 平台公开前端证据

读取已观察到的公开脚本，没有执行脚本中的控制函数，也没有下载账户存储或令牌：

```text
http://www.logicmatrixsemi.com:5174/assets/DigitalTwinComponent-D3lu3nOF.js
UTF-8 bytes: 693275
SHA256: 4be9d6910acc59f9aff3d028c30f8f79d48c224151c5ae2e18426b7f5cad4fa1
Checked: 2026-09-06T02:38:53.522Z
```

此资源是平台实现证据，不是厂商电气原理图；路径随平台更新可能变化。

- 封装映射Sd包含AB15→SCBV、C23→L3_PAD38、AC26→L6_PAD6、AB26→L6_PAD5。数据单元映射Dk包含L3_PAD38→846/845，但没有SCBV条目。
- 组件KEY1映射L3_PAD38。平台通用模型含5个LED和5个KEY，不应替代参考MES底板8LED/2KEY接线表，更不证明实际板型或核心板版本。
- 启动/停止使用`/modules/debugger/boundary-scan/start`和`stop`；前端启动请求只含deviceId，未显式选择SAMPLE或EXTEST。单凭接口名无法保证扫描对运行中设计无干扰。
- 虚拟按键调用`/modules/debugger/boundary-scan/drive`，发送数据单元高字节、低字节和电平三字节；按下电平0、松开1。它是边界扫描驱动，不是机械执行器，也不是CPU直接写GPIO。
- 状态同步与`ws:boundary_scan_data`事件的原始帧入口只接受100或150字节。PG2L200H解码分支用1079位，按`bit_position=1078-cell`、字节内MSB优先取值。其余121位未在本页赋予协议意义。
- 前端解码器以长度≤135进入645位分支，但实际原始帧入口限定100/150字节。不能把紧密打包的135字节PG2L200H BSR直接交给该长度判别逻辑；本项目解码器明确指定器件和150字节封装，不猜器件。

## 离线工具与验证

`scripts/boundary_scan_decode.py`仅读取本地JSON并输出JSON，没有网络、JTAG或设备控制功能。输入必须恰好包含device、packing、origin、rawFrame四项：device为PG2L200H，packing为logicmatrix-msb0-descending-150，origin为synthetic或unverified_capture，rawFrame为150个0–255整数。拒绝重复JSON键、布尔值伪字节、错误帧长、未知器件和未知位序，输入上限16 KiB。

该工具按公开前端的位序假设解释数据：SCBV位于byte134的bit1；KEY1位于byte29的bit7；UART_RX位于byte133的bit7；UART_TX位于byte133的bit5。均为零起始索引。返回完整原始帧SHA-256及BSDL指纹，尾部121位参与哈希但不参与四个信号的解码。

`scripts/test_boundary_scan_decode.py`的10项测试已通过：全零/全一、四引脚独立单比特、邻位干扰、尾部隔离与哈希、错误长度、错误字节、显式器件/位序/来源、输入结构与不变性、重复JSON键、BOM输入和超长CLI反例。已接入validate.ps1。此处只使用合成帧，不声称已采集板卡帧。

## 后续实板证据门槛

1. 先明确远程扫描后端所用指令及启动/停止恢复语义，尤其是否会切换EXTEST并覆盖用户I/O；确认后再决定是否在专用测试固件上使用。
2. 实际捕获需保留具体设备/租约、时间、序号、完整原始帧及运行模式，并用至少一个已知GPIO电平独立校准位序，不能仅凭解码器输出确认采样来自指定器件。
3. 即使SCBV解码为高，也只提供数字输入电平证据，不区分2.5 V/3.3 V，不证明VCCIOCFG或L4/L5真实供电。配置网络与板型证据仍按CONFIGURATION_ASSURANCE.md补齐。
4. 若未来通过边界扫描触发KEY1，应称为边界扫描注入GPIO事件；需要另证CPU同步器、GPIO中断和应用确实响应。不能称机械按键测试，也不能仅用孪生UI颜色作为CPU执行证据。

因此本轮不改SCBV工程设置、不新增未核实I/O电压约束、不关闭配置审核或独立GPIO实板验收项。
