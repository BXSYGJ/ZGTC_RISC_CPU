# PaceRV 145.125 MHz 三版本交付

这三个归档包含对应 RTL 源码、V0 位流、V0/V1 固件、编译与运行回执、布局布线报告和修改/回滚证据。解压即可浏览对应版本的完整文件。复现构建使用包内 README 记录的原工作区路径。

| 版本 | V0 CoreMark/MHz | V1 CoreMark/MHz | Slow setup | LUT | FF | DRM36K | APM | GPLL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [H6 LoadALU 最高分](PaceRV_H6_LoadALU_145125_Experimental.zip) | 3.511833433 | 3.510807712 | -0.218 ns | 7255 | 2541 | 25 | 4 | 1 |
| [H6 SelectiveLoad 后续集成推荐](PaceRV_H6_SelectiveLoad_145125_Experimental.zip) | 3.511364165 | 3.509956797 | -0.044 ns | 7125 | 2541 | 25 | 4 | 1 |
| [Loop16 时序通过](PaceRV_Loop16_145125_Verified.zip) | 3.484719042 | 3.480411318 | +0.030 ns | 6547 | 2813 | 25 | 4 | 1 |

器件 PG2L200H-6FBB676，CPU 配置频率 145.125 MHz，参考时钟 27 MHz，setup uncertainty 0.150 ns，指令集 RV32IMC。两组测试各运行 6000 次，计时超过 10 秒且 CRC 通过。成绩来自实际 RTL 仿真；位流完成实际 PDS 布局布线。前两个版本保留实验时序失败状态，Loop16 全部十类时序检查通过。新位流的板上烧录和 UART 采集待完成。

SelectiveLoad 把加载响应旁路集中于合法 ADD/ADDI、XOR/XORI，并使用 8 位分组 carry-select 加法器。与最高分版本相比，V0 成绩相差约 0.0134%，slow setup 改善 0.174 ns。

## 文件与核验

- [SHA256SUMS.txt](SHA256SUMS.txt)：三个原始 ZIP 的 SHA256。
- [UPLOAD_VERIFICATION.json](UPLOAD_VERIFICATION.json)：上传前 ZIP CRC、清单文件哈希、固件及位流核验结果。
- [evidence/FINAL_AUDIT.md](evidence/FINAL_AUDIT.md)：独立审计结果，含周期、CRC、RTL 绑定与时序状态。
- [evidence/FINAL_AUDIT.json](evidence/FINAL_AUDIT.json)：完整独立审计回执。
- [RESULTS.md](RESULTS.md)：本地实验报告原始快照。其中实验目录链接以原工作区为基准；各 ZIP 提供对应源码与证据。
- [FINAL_STATE.json](FINAL_STATE.json)：本地交付状态原始快照。

三个归档各自的 MANIFEST.json 记录全部文件的大小和 SHA256：LoadALU 160 项、SelectiveLoad 297 项、Loop16 160 项。两个旧包文件位于 ZIP 根目录，SelectiveLoad 包包含一层同名根目录。

对 SelectiveLoad 包，可在此目录执行 `python verify_package.py --zip PaceRV_H6_SelectiveLoad_145125_Experimental.zip`，验证原始清单、RTL 与固件绑定及时序状态。旧包按照各自 MANIFEST.json 验证，结果保存于 UPLOAD_VERIFICATION.json。
