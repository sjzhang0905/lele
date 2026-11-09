本目录全部 NMR 数据均为人工测试数据，不是真实量化计算结果。

快速演示：打开 synthetic_nmr_display.lele。
O 使用 Space filling，一个 H 使用 Sticks，另一个 H 使用 Ball and stick。
Analysis → NMR spectrum / shielding table 可查看 H 的谱图与原始张量。
人工参考屏蔽值 H=31 ppm 已保存在工程中；两个 H 的人工化学位移为 3 和 5 ppm。
该参考值只用于测试，不可直接用于实际研究。

synthetic_gaussian_nmr.log 包含结构和人工屏蔽块。
synthetic_orca_nmr.out、synthetic_cp2k_shift.data、synthetic_gipaw_nmr.out、synthetic_nwchem_nmr.out
是验证结果单独加载的简化示例，不具备完整计算输出的所有区段。

操作说明见 docs/FEATURES_v3.5.0_CN.md。
