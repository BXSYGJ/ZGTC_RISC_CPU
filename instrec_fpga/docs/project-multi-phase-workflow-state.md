# 当前工作记忆：2026-11-14

当前用户目标active：结合XSY与XSY2，为现在项目加入RTOS，以125MHz 223256版本为基线。实现位于instrec_fpga/rtos/，正式FreeRTOS V11.3.3，1kHz真实定时中断，三任务+idle，静态消息队列，16KiBROM/16KiBRAM。实际CPU、完整NPUgolden、嵌套临界区和原版副本回退通过；固件7148ROM/5600BSS。编译/综合/map通过128.5/155DRM，当前PNR唯一PID20988（父continuation工具，句柄由rtos_hardware代理持有），工程build/rtos/pds/20261114-153018-rom_loop_fix-map，continuations/20261114-074722-356866。继续检查实际进程与FULL_RESULT，勿重启同一flow；仅待完整位流，当前无FTDI/CP2102，板级待测。rtos/evidence/ACCEPTANCE.json当前6/7项通过。旧时序优化paused，CPU优化已结束。


最近远端复核：2026-11-14 15:10（北京时间），XSY=0b8201e071c6c59b8d7ead23ad944684f4d0b24c，XSY2=8f902aec29c38bc4a32a4e95ab47d18411684b52。相对上次4d3d6f1新增3次提交：seed85八类整机位流归档、构建种子参数、烧录/I2S脚本修复；五组识别与RTOS无新上传。位流SHA256重算通过。当前仅fetch未合并，继续复用既定109.375/125MHz包，时序目标保持paused。


仓库D:/AAAFPGA/ZGTC_RISC_CPU_XSY，分支XSY，活动目录instrec_fpga。

最新应用目标：参加2026紫光同创赛题一，完成交响乐识别系统，识别同时出现的乐器及进入/退出。用户明确CPU工作已完成，当前聚焦应用；RTOS/Linux仍处方案评估，尚未开始移植。

2026-11-14已核查GitHub XSY=4d3d6f1、XSY2=8f902ae。两个分支都有五组多标签双头float模型；XSY另有INT8契约、725760字节权重镜像和8906样本历史评估，INT8 macro-F1 0.865587。现有起点是弦乐/木管/铜管/打击乐/键盘拨弦五组，活动时间事件与当前板端迁移待实现。详见SYMPHONY_GROUP5_CODE_AUDIT_20261114.md，接续应复用已有成果。

用户最新要求：当前轮完成后停止时序优化，选用已有125MHz和约109.5MHz中违例较小的版本。实际频率为109.375MHz。原持续时序验收目标状态paused。

所选主版本：109.375MHz的full-20261114-021145-full，setup TNS -33.413ns、155失败端点。125MHz备选：full-20261113-223256-full，slow/fast hold +0.052/0.000ns。使用入口为SELECTED_BUILD_VERSIONS_20261114.md；两个ZIP位于build/pacerv_shared_system/selected_versions_20261114，分别含原位流、202份配套输入及原最终时序报告，哈希已验证。

最后一轮full-20261114-133421-full已结束，719.426秒、退出1。500ps时钟树hold修复参数超出PDS允许的0至200ps范围，pnr未执行，无新位流；202份冻结输入未变，当前PDS进程0。保留原失败记录与当前83.333333MHz活动源码。后续接续用户的新工作要求。

实时状态以STATUS.md顶部为准。操作仅在后台进行，保留每个版本对应的RTL/IP/HEX/约束；本地提交XSY。
