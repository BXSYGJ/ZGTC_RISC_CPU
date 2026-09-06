# 配置电压与I/O时序证据边界

核查日期：2026-09-06。本次没有修改SCBV、引脚电压或时序例外，没有下载新位流。目的在于把尚未确认的硬件参数与已有内部时序证据分开，避免为消除告警而猜设置。

## 已取得的原始资料

| 来源 | 页码 | SHA-256 |
| --- | --- | --- |
| 本机PDS_2022.2-SP6.4/doc/Pango_Design_Suite_User_Guide.pdf | PDF150，印刷149 | E2AC3F2AC7BB539CC51FE85CC239EA2249F4EE6790912B67C86CAE23A3898BA2 |
| 配套MES2L676-200HP硬件使用手册_v1.2.pdf | PDF11，印刷8 | B045D4A3BB436A5CCD499D107081B4DE0DA26F84C19FF20BFE53E4C4D66D9E4C |
| 厂商Logos2 Family Hardware Design Guide，UG040012 V1.4 | PDF7表2-1、PDF11第3.1节 | 3C2879F4A83893C10D9FA6DACBB8649AA144EACF13DF0A127FF3DD4E7D061EBD |

第三份下载自厂商地址，保存在本地 `build/vendor-docs/UG040012_V1.4.pdf`：

```text
https://www.pangomicro.com/en/uploads/38579124_1729131891.pdf
```

下载文件的PDF元数据标题沿用其他手册名称；本次以可视首页的UG040012 V1.4和实际章节内容确认身份，没有只信HTTP文件名或metadata。表2-1已经渲染为 `build/vendor-docs/scbv-table.png` 逐行核对。厂商原PDF不纳入工程快照。

## SCBV：已知与未知

本机PDS手册说明SCBV默认为None，支持PG2L200H；同时注明L4与L5均使用时该设置无效。器件安装数据 `arch/vendor/pango/logos2/pg2l200h/data/config/ini_data/Logos2-PG2L200H.ini` 中存在None、Low Voltage、High Voltage候选文本，但这些文本本身不能证明某块板应选哪一个，也不等于已经取得Tcl设置接口。

UG040012 V1.4表2-1区分配置接口电压、VCCIOCFG、L4/L5供电以及SCBV实际引脚连接。JTAG采用3.3 V或2.5 V时，表中SCBV接VCCIOCFG；低电压JTAG配置对应GND并约束L4/L5的允许电压。第3.1节要求工程设置与真实硬件相符。不能只看UART/LED的LVCMOS33就推断配置接口电压或SCBV实物连接。

MES2L676-200HP手册明确L3/L4/L5供电为3.3 V，L6/L7可调。该证据可以约束这块参考板的分析，却不能单独证明远程实验箱5使用同一核心板版本、同一VCCIOCFG和同一SCBV连接。本地提供的底板SCH不是完整核心板配置电源原理图，未从中取得缺失的SCBV网络证据。

当前结论：不将None擅自改成High Voltage或Low Voltage。已有成功下载、UART运行和CoreMark结果证明指定实验中的可工作性，不证明配置电压设置已依据电路完成审核。该项仍未关闭，也不能把PDS告警无条件当无害。

关闭该项所需资料是远程箱实际板型/版本及核心板配置电源原理图，明确配置模式、VCCIOCFG、VCCIOL4、VCCIOL5和SCBV引脚网络。若平台声明统一JTAG接口电平，也需将声明与具体板卡对应；取得依据后再核对PDS受支持的设置接口并重新构建、核验和上板。

## 边界扫描补充证据
2026-09-06补充只读核查：PDS自带PG2L200H_FBB676 BSDL确认AB15/SCBV有输入扫描单元0，边界寄存器长1079位。远程前端封装表包含该脚，但数据单元表缺失SCBV；不能据此前端缺项推断器件无法扫描。150字节帧离线解码工具及反例测试见[BOUNDARY_SCAN_AUDIT.md](BOUNDARY_SCAN_AUDIT.md)。尚未采集实板SCBV，尚未确认后端扫描模式；即使取得数字高电平，也不能替代配置电源网络与电压证据。


## 当前异步I/O约束解释

`constraints/board.fdc` 为D18创建27 MHz参考时钟，非27 MHz构建另经PLL生成CPU时钟。PDS门禁已校验生成时钟周期和有效负载，防止仅约束参考输入。

文件中 `set_false_path -from [get_ports {rst_n key uart_rx}]` 作用于异步输入。RTL复位两级同步释放，GPIO与UART有同步器；这不是证明亚稳态概率、复位恢复/移除或外部端到端时序满足所有条件。UART协议由独立采样和实板收发验证，不是与CPU时钟同源的外部同步接口。

UART_TX和LED未定义外部源同步接收时钟或input/output delay契约。因此当前All Constraints Met应解释为已施加约束下的内部路径检查，不应推广为未给定外部时序条件全部满足。不能凭空添加零延时约束来制造“已约束”的外观。

后续须根据外部接口契约核对同步器结构、例外覆盖和未约束路径，再判断是否需要更精确的最大延时、复位时序或I/O约束。厂商资料、PDS报告和实板协议测试属于不同层次的证据。
