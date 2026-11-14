# 当前工作记忆：2026-11-14

用户已明确要求把相关内容上传 GitHub，并允许新建分支。当前发布分支为 `codex/rtos125-integration`，起点是验收完成的 `12d79828b8c67920f14750a23400a122bd0597c8`；仓库仍为 BXSYGJ/ZGTC_RISC_CPU。源码、RTOS 验证记录随分支提供，位流与原交付 ZIP 复制归档到 `instrec_fpga/releases/rtos125-20261114-175148/`，两份成品哈希与 DELIVERY.json 一致，README/RELEASE.json 提供远端入口。后续上传和分支核验使用本轮明确授权。

当前RTOS实现目标已完成：结合XSY/XSY2，以125MHz 223256基线接入FreeRTOS V11.3.3、1kHz、三应用任务/静态队列；H3和202原始输入不变。最新162656-direct_rom_final-map整机六阶段完成，207输入和map.adf/controls前后相同；1789.913秒exit0，PDS=0。实际ROM全容量/22位SMT/控制/厂商模型/12真实负例全部通过；最终统一verify094556含13命令PASS，8→9/9，source/VERIFICATION均UTF8无NUL。交付build/rtos/releases/rtos125-20261114-175148.zip，586文件SHA全部重开通过，bit3791112B SHA525d08ea4b903de7604453b0457f131c0aa79d00e9611a4e43de6ba84a5eaf00。最终资源36749LUT/39739FF/136.5DRM/94APM；最终rtr系统slow setup -11.834ns、pixel -1.140ns、slow hold+0.020ns、fast hold-0.035ns，用户已接受时序违例，原报告保留。无FTDI/CP2102，上板未测。原时序优化paused，五组应用资产保持；后续工作按用户新指令推进。构建入口rtos/README.md，证据ACCEPTANCE/DELIVERY/VERIFICATION，最后本地提交不push。


最近远端复核：2026-11-14 15:10（北京时间），XSY=0b8201e071c6c59b8d7ead23ad944684f4d0b24c，XSY2=8f902aec29c38bc4a32a4e95ab47d18411684b52。相对上次4d3d6f1新增3次提交：seed85八类整机位流归档、构建种子参数、烧录/I2S脚本修复；五组识别与RTOS无新上传。位流SHA256重算通过。当前仅fetch未合并，继续复用既定109.375/125MHz包，时序目标保持paused。


仓库D:/AAAFPGA/ZGTC_RISC_CPU_XSY，分支XSY，活动目录instrec_fpga。

最新应用目标：参加2026紫光同创赛题一，完成交响乐识别系统，识别同时出现的乐器及进入/退出。用户明确CPU工作已完成，当前聚焦应用；RTOS/Linux仍处方案评估，尚未开始移植。

2026-11-14已核查GitHub XSY=4d3d6f1、XSY2=8f902ae。两个分支都有五组多标签双头float模型；XSY另有INT8契约、725760字节权重镜像和8906样本历史评估，INT8 macro-F1 0.865587。现有起点是弦乐/木管/铜管/打击乐/键盘拨弦五组，活动时间事件与当前板端迁移待实现。详见SYMPHONY_GROUP5_CODE_AUDIT_20261114.md，接续应复用已有成果。

用户最新要求：当前轮完成后停止时序优化，选用已有125MHz和约109.5MHz中违例较小的版本。实际频率为109.375MHz。原持续时序验收目标状态paused。

所选主版本：109.375MHz的full-20261114-021145-full，setup TNS -33.413ns、155失败端点。125MHz备选：full-20261113-223256-full，slow/fast hold +0.052/0.000ns。使用入口为SELECTED_BUILD_VERSIONS_20261114.md；两个ZIP位于build/pacerv_shared_system/selected_versions_20261114，分别含原位流、202份配套输入及原最终时序报告，哈希已验证。

最后一轮full-20261114-133421-full已结束，719.426秒、退出1。500ps时钟树hold修复参数超出PDS允许的0至200ps范围，pnr未执行，无新位流；202份冻结输入未变，当前PDS进程0。保留原失败记录与当前83.333333MHz活动源码。后续接续用户的新工作要求。

实时状态以STATUS.md顶部为准。操作仅在后台进行，保留每个版本对应的RTL/IP/HEX/约束；本地提交XSY。
