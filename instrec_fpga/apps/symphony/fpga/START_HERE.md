# 乐境：板端启动

1. 完整解压发布 ZIP，保留根目录 `LOAD_WEIGHTS.ps1` 和 `runtime/` 文件夹。
2. 将显示器接到 FPGA 的 HDMI 输出，按既有板卡流程下载同包的 `instrec_top.sbit`，连接 PCM1808 与线路音源。
3. 将电脑连接到 FPGA 串口，确认 Windows 设备管理器中的 COM 编号，并关闭占用该串口的监视工具。电脑需要 PowerShell 7、Python 3 和 `pyserial`。
4. 在解压目录打开 PowerShell，执行以下命令。将 **COMn 替换为 FPGA 的实际串口**，例如 `COM7`：

```powershell
pwsh -File ./LOAD_WEIGHTS.ps1 -SerialPort COMn
```

脚本会先核对固定八类权重的大小与 SHA256，再调用同包上传器。上传成功时可看到 `UPLOAD OK` 和 `WEIGHT_LAUNCHER_PASS mode=upload`。如需指定 Python，添加 `-PythonExe 'D:/Anaconda/python.exe'`；添加 `-DryRun` 可仅核验权重与协议分帧。

5. 收到识别结果后，FPGA 显示器更新导赏页。KEY1 短按切换类别筛选，长按进入检索页；检索页短按选择下一条匹配结果，双击添加或取消书签，长按返回。导赏页双击标记最近一次结果。

历史保留最近 64 次识别结果；时间按结果到达的开机毫秒记录。重新启动后按上述步骤加载同包八类权重，历史和书签随复位清空。
