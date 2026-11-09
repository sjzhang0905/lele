# 3.2.1 测试记录

- 全量自动测试：1202 passed、12 skipped、78 subtests passed。环境为 Linux、Qt offscreen 和 VTK EGL，不是 Windows 原生环境。
- 使用用户提供的 WAVECAR 和 OUTCAR：3 个 k 点、48 条能带，晶胞、k 点、能带及系数与独立实现一致；所抽查的状态经独立平面波直接求和和 FFT 重建比较，最大差约 2.18×10⁻⁸。测试波函数的密度、实部和虚部均已实际生成并渲染。
- WAVECAR 中的原始占据权重在用户提供的 ISPIN=1 样例中与 OUTCAR 输出的占据数相差自旋简并因子 2。程序保留并标记原始权重。
- 缺少 ORCA 6.1.0 的 orca_2mkl，未能实测真实 GBW 的转换。无转换器时，已用用户提供的 ROH.log 验证同名日志回退；数据标记为来自日志，不代表 GBW 已解码。
- 标准复数标量 WAVECAR 已用这个样例验证；Gamma-only 半存储、SOC/自旋量子态等变体未实现。Windows 原生运行未验证。自动测试不包含用户提供的计算文件。
