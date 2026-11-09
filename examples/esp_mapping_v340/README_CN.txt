人工解析示例，非真实分子 ESP 计算结果。

直接用 LELE v3.4.0 打开 mapped.lele：在 density=0.2 的表面上映射 potential。
打开 overlay.lele：同时显示不同数据场的三张等值面。
两个工程都嵌入网格，不依赖外部 CUBE；可继续编辑每层配置。

手动操作：打开 synthetic_density.cube → Import another field file… →
synthetic_potential.cube → Surface layers / ESP color mapping… → 保留正等值面
并设为0.2 → Source field 选 density → Color mapping 选 potential。

density = exp(-(x²+y²+z²))；potential = 0.2x - 0.1y + 0.3z。
两张网格具有不同间距与斜基矢；这里的单位只是解析示例约定。
实际 ESP 应使用电子结构程序提供的、同一构型和坐标系的密度及电势网格。
