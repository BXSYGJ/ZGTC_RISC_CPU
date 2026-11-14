# 乐境：原生FPGA HDMI导赏与识别窗口检索

显示器直接连接 FPGA HDMI，KEY1 短按选择、双击标记、长按切页。
先完整解压 ZIP，按根目录 START_HERE.md 执行 LOAD_WEIGHTS.ps1 加载同包八类权重；运行依赖 PowerShell 7、Python 和 pyserial。
导赏页显示八类真实概率和最近窗口；检索页按类别选择窗口并标记。
识别结果到达时间按开机毫秒记录，64 槽历史与书签复位清空。

- 位流：[instrec_top.sbit](instrec_top.sbit)
- 输入、应用源码和验证记录：[symphony-hdmi-20261115.zip](symphony-hdmi-20261115.zip)
- 全部哈希：[RELEASE.json](RELEASE.json)
- 重建与操作：[应用说明](../../apps/symphony/README.md)

位流 SHA256：`59a0e54a229681934f55ef3bfef45cac4fa96ddac3fecef4421bddd673bf5ee8`。
ZIP SHA256：`c5dad9a451ee5f3a32656e7766f292acb7cba7512865c42b5737f944ebd814cb`。
ZIP 内全部 287 项均已逐一重开并核对 SHA256。
125 MHz / 148.5 MHz、seed2/hold8 固定，原始最终时序报告在 ZIP 的 build/final_timing.rtr。
最终资源：37884 LUT、40150 FF、1431 distributed RAM、94 APM、130.5/155 DRM。
最终时序 qualified=false；按用户安排保留当前工作点及原始报告。
物理板卡显示与按键实测状态：pending。
