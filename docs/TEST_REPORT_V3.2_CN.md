# 3.2.0 测试记录

- 全量自动测试：1192 passed、11 skipped、78 subtests passed。测试环境为 Linux、Qt offscreen 和 VTK EGL；并非 Windows 原生环境。
- 最终改动相关的格式、工程文件与界面回归：77 passed、1 skipped。缺少真实外部样例的测试被跳过。
- 独立数值检查：用 PySCF 生成的测试基组和分子轨道，比较 s/p/d/f 的球谐和笛卡尔轨道值、顺序及相位。该检查使用合成 FCHK 和生成的 Molden 样例，并不代表已验证所有软件版本的文件。
- 通过 EGL 对正负等值面和倾斜网格进行实际渲染检查。
- 限制：没有实际的用户 Gaussian、ORCA、VASP 生产文件用于覆盖所有格式变体；没有本机 ORCA 工具，因此 GBW 的真实转换未实测。WAVECAR 轨道等值面未开放。Windows 下的原生运行和安装尚未验证。
