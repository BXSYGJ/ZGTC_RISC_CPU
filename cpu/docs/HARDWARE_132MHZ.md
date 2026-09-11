# 132 MHz实板联合门槛记录

## 结论

实验箱2，页面型号PG2L200H，完成性能6000轮、验证6000轮和重新烧录后的第二次性能6000轮。两次性能完整UART逐字节相同，独立check_frequency_candidate.py --clock-hz 132000000均返回numeric_target_pass。当前同时满足至少3.0 CoreMark/MHz和至少0.031 CoreMark/LUT的已测频点提高到132 MHz；不把早期未满足资源门槛的更高频率配置混入这个结论。

| 指标 | 本次结果 |
| --- | ---: |
| 配置主频 | 132 MHz |
| 执行效率 | 3.0129694974344834 CoreMark/MHz |
| 吞吐 | 397.7119736613518 CoreMark |
| 资源效率 | 0.03863531898789118 CoreMark/LUT |
| 布局后LUT / FF / APM | 10294 / 5041 / 4 |
| setup WNS | +0.001 ns |
| 性能计分周期 | 1991390887 |
| 性能计分退休指令 | 1649428424 |
| 性能计分时长 | 15.0862945985秒 |

频率依据PLL配置、PDS生成时钟和固件/计数器元数据一致性，未独立测量引脚时钟。PDS估计132.0306 MHz不是实测Fmax；仅0.001 ns的正裕量不能证明温压裕量、长期稳定性或物理极限。板级SCBV警告仍未解决。

## 三次独立运行

以下时间为采集记录的UTC时间；构建目录名保留工具实际生成的原名。

| 运行 | 新G发送时间（UTC） | 周期 | 退休指令 | CRC |
| --- | --- | ---: | ---: | --- |
| performance r1 | 2026-09-06T19:21:50.653Z | 1991390887 | 1649428424 | 通过 |
| validation r1 | 2026-09-06T19:23:01.681Z | 1993862590 | 1649775523 | 通过 |
| performance r2，重新烧录 | 2026-09-06T19:24:29.775Z | 1991390887 | 1649428424 | 通过 |

验证种子计分15.1050196212秒。性能CRC为e9f5/e714/1fd7/8e3a/a14c，验证CRC为18f2/e3c1/0747/8d84/18e1；验证种子用于独立正确性检查，不取代性能种子成绩。UART的整数秒输出Iterations/Sec=400不是精确成绩，精确值由完整64位周期和132000000 Hz计算。

## 与已测126 MHz比较

两者同为6000轮，性能计分周期、退休指令与缓存统计相同。频率和吞吐提高4.7619048%，资源效率提高3.8866839%；LUT增加86、FF增加234，APM保持4。执行效率完全相同，不宣称每MHz工作量提升。

126 MHz版本为10208 LUT、4807 FF、WNS +0.128 ns，本次是10294 LUT、5041 FF、WNS +0.001 ns，故存在面积/裕量代价。除了Cache扇出属性，还包含此前M操作数预采样和PLL源码修订，不能把跨版本差异全部归于单一改动。严格同源单因素132 MHz本地比较见CACHE_ADDRESS_FANOUT.md。

## 构建、配置和源码

性能实现build/pds/20260907-030316-c8c50be4，位流SHA-256 CED9A4F1BC99A3F9A95813C75EF0179DECFC1A0D3899F83D735E9240D8E8C53A。固件SHA-256 65416C7D16CCDF6B46B881B1BE21C37D54156A674056BA01DBC43DC8F9F0216E。

验证实现build/pds/20260907-031200-25d7231c，位流SHA-256 23519A14F092AFC0E05308AF33FEC5E8DD3879A08C7BCABD0382FA3688ADF7D3。两份实现均10294 LUT、5041 FF、4 APM、WNS +0.001 ns，20份RTL/PLL/约束快照逐哈希相同，并在本次板测封存时与生产输入一致；后续本地候选不能直接沿用本成绩。

核心仍为C4F0EF80E634F153F5BF1CB2B0F9BB314432333BF9DC93E1A8E9F6E1C2CC2346；Cache为AC24EDFB561B454437519B452E5F6F90AA4C7DC538400D919919BC011877D633；M单元为AA1BF3E9AC51E8179B9C52B7ADA90DE816B219AC7263D7FB973A9289D5164C79；PLL为B1AD88A943CBEC1AF172560D7B22919E298A64FF1D033F19F7A27D23B1BD7CBB。

RV32IM/ILP32、I-cache 8 KiB、D-cache 2 KiB、两路四字行、BTB 256项，配置字0e8e86f9，LoadUseBubble=0；FastI、FetchOverlap、FastD读写、EarlyDRequest、DataOverlap开启。GCC 10.2.0、O3、unroll、链接relax，未修改CoreMark算法/固定种子，未启用LTO。串口输出等待2640000周期只用于计分区外输出。

## 实板采集链

按用户要求以独立Chrome端口19505登录，原19474会话未改动。页面预约20分钟并确认实验箱2/PG2L200H，UART显示115200、8N1、RX AC26/TX AB26。每次先核验待上传位流哈希，经页面文件选择与烧录完成终态后打开UART，收到连续3次空读后才发送新的G命令。页面实际发送载荷为G加换行，保存于commands，不把串口内部deviceId数字解释为板卡编号。

串口采集来自页面实际serial-port/read响应，逐包核验hex、bytesRead和data，按接收顺序拼接，不剪裁、重排或去重。首次打开串口时存在计分区前的零散非计分字节，来源未另行判定，保留在总审计中；每次G之前独立清空并保存索引，三份计分UART均从完整START到FINISHED，不声称捕获了完整开机READY。

三次烧录终态、三次新G、三个独立采集区间、三次清空均有记录，串口采集错误列表为空。串口已关闭，设备于2026-09-06T19:26:10.198Z确认释放；首次释放后页面状态尚在更新，复核后才确认，未重复发起释放。专用采集页已关闭，19505主页面保持登录，未改动原19474会话。

## 证据位置

build/hardware目录内：

- cache-address-maxfan64-f132-box2-performance-r1.uart、r2.uart及各自-session.json、-target.json。两份UART SHA-256均A8917C9506A0FE415167D59C25D4C1EC40E6B1C02D99167C27E6D2FC9629B82B。
- cache-address-maxfan64-f132-box2-validation-r1.uart及-session.json、-verified.json。UART SHA-256 C8F26ACCB9D667C4ACCF7D9CB92E1EC863FA1DA83A8C05F9888E1E5F419EA36C。
- cache-address-maxfan64-f132-box2-audit.json、-initial.json、-device.png，保留目标、原始接收及操作链，不含登录密码或令牌。
- cache-address-maxfan64-f132-provenance.json，对30个产物计算哈希，记录两组匹配源和相对126 MHz实测比较。

两个性能目标检查各自重读原始报告、位流、固件、源快照和对应UART；验证种子通过独立read_case及CRC/时长/配置断言。数值检查器自身不认证板卡身份，身份依据独立页面预约与采集链。

## 尚未完成

本次只新增一个合格的实板频点。执行效率继续优化、当前源ILA、独立GPIO输入正例、完整IO电气约束/SCBV、长期稳定性以及进一步频率/资源折衷仍待推进。三次长测不是长时间老化测试，有限布局试验也不能证明物理极限。当前版本不追加提交或上传GitHub。
