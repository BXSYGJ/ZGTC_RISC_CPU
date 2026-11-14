# 当前工作记忆：2026-11-14

当前用户目标active：结合XSY/XSY2，以125MHz 223256基线接入FreeRTOS。V11.3.3、1kHz、三应用任务/静态队列，正式固件7148B已实现。162656-direct_rom_final-map完成compile/synthesize/map，207输入一致、136.5/155DRM。正式ROM_AUDIT于17:07 PASS，全部8192数组词、22位SMT地址、8实例控制和两路固件SHA均过；VENDOR_ROM_MODEL及MAPPED_ROM_NEGATIVES（12真实篡改）归档。统一verify_system090908全部pass，8/9门槛只待bitstream。唯一PNR53608（hardware代理持有session80994），continuations/20261114-091420-953401，布局完成进入布线；固定seed2/hold8、90分钟，保持原map RESULT/INPUTS不变。原ROM数组复制全零失败证据保留；H3/202冻结基线保持，原时序优化paused；无USB板卡。位流结束后root strict collector→package/reopen→更新STATUS/CHANGELOG/memory→commit。


最近远端复核：2026-11-14 15:10（北京时间），XSY=0b8201e071c6c59b8d7ead23ad944684f4d0b24c，XSY2=8f902aec29c38bc4a32a4e95ab47d18411684b52。相对上次4d3d6f1新增3次提交：seed85八类整机位流归档、构建种子参数、烧录/I2S脚本修复；五组识别与RTOS无新上传。位流SHA256重算通过。当前仅fetch未合并，继续复用既定109.375/125MHz包，时序目标保持paused。


仓库D:/AAAFPGA/ZGTC_RISC_CPU_XSY，分支XSY，活动目录instrec_fpga。

最新应用目标：参加2026紫光同创赛题一，完成交响乐识别系统，识别同时出现的乐器及进入/退出。用户明确CPU工作已完成，当前聚焦应用；RTOS/Linux仍处方案评估，尚未开始移植。

2026-11-14已核查GitHub XSY=4d3d6f1、XSY2=8f902ae。两个分支都有五组多标签双头float模型；XSY另有INT8契约、725760字节权重镜像和8906样本历史评估，INT8 macro-F1 0.865587。现有起点是弦乐/木管/铜管/打击乐/键盘拨弦五组，活动时间事件与当前板端迁移待实现。详见SYMPHONY_GROUP5_CODE_AUDIT_20261114.md，接续应复用已有成果。

用户最新要求：当前轮完成后停止时序优化，选用已有125MHz和约109.5MHz中违例较小的版本。实际频率为109.375MHz。原持续时序验收目标状态paused。

所选主版本：109.375MHz的full-20261114-021145-full，setup TNS -33.413ns、155失败端点。125MHz备选：full-20261113-223256-full，slow/fast hold +0.052/0.000ns。使用入口为SELECTED_BUILD_VERSIONS_20261114.md；两个ZIP位于build/pacerv_shared_system/selected_versions_20261114，分别含原位流、202份配套输入及原最终时序报告，哈希已验证。

最后一轮full-20261114-133421-full已结束，719.426秒、退出1。500ps时钟树hold修复参数超出PDS允许的0至200ps范围，pnr未执行，无新位流；202份冻结输入未变，当前PDS进程0。保留原失败记录与当前83.333333MHz活动源码。后续接续用户的新工作要求。

实时状态以STATUS.md顶部为准。操作仅在后台进行，保留每个版本对应的RTL/IP/HEX/约束；本地提交XSY。
