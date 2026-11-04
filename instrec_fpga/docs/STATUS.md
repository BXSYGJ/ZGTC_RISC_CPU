# RTL交付状态

## 2026-11-04：最终Word与双部分RTL交付

用户指定PaceRV_作品技术报告(1).docx为最终报告，逐字节复制到docs/；旧TECHNICAL_REPORT.md从交付文件清单移除。独立分支codex/instrec8-source-docs重新组织为rtl/bare_cpu与rtl/system_application，仅收录RTL源文件。裸CPU按最终报告涉及版本保留Original_155250和H3_Base_145125，每版18个RTL模块加1份PLL，共38份，来自DYH提交4ef1ea1be32c110024dd59f08f1342b325c9df59；完整系统应用保留此前固定的56份应用／CPU RTL和75份原厂IP RTL，共131份。

验证：CPU下载字节与远程Git blob身份38/38一致；应用源文件与原分支内容131/131一致；169份SHA-256全部通过。核对三组源文件集的模块引用，所需自有模块完整，原厂加密模块保留为vp，GTP_*为PDS器件库原语；最终Word hash与用户原文件一致。未修改任何RTL、未新做编译／综合／布局布线或板级测试。

本次按只交RTL移出训练／模型／固件／脚本／约束／ROM数据及旧技术报告，ROM引用和对应资产身份保存在RTL_MANIFEST.json，完整旧工程可从cdc4969e恢复。各CPU版本和应用源文件集分别独立使用，避免同名模块冲突。原XSY用户CPU改动、Word原件及其他未跟踪资产保持原样。

下一步：按README选择裸CPU或应用文件集进行提交／集成。用户提供Word作为最终文档，不以旧Markdown替代。既有构建及板级原始事实不因源码整理改变。更新本地提交及既有远程交付分支。
