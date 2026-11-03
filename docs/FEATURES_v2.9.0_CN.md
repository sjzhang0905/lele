# LELE v2.9.0

新建结构的默认配色、成键判据和 space-filling 半径已分别接入三套参考数据。

| 设置 | 新默认值 | 调整位置 |
| --- | --- | --- |
| 原子颜色 | GaussView style（Chemcraft 兼容色板） | Style → Atom colours |
| 普通成键 | Chemcraft b816bt 原子对距离上限，×1.00 | Style → Bond search / Bond cutoff × |
| Space-filling 半径 | VESTA 3.5.8 Atomic，100% | Style → Style / VESTA radii / Atom size |

GaussView 这一项采用 Chemcraft 内置的 **GaussView style**，尚未取得 Gaussian
原始完整 RGB 表，因此界面明确写为 **GaussView style (Chemcraft)**。它是兼容
配色，不能据此承诺和某个 GaussView 版本逐元素、逐像素一致。元素和单个原子的
自定义颜色仍有更高优先级。可选择 **Legacy LELE** 使用此前的色板。

普通成键读取各元素对的普通键上限，默认系数为 1.00。修改系数或切换成键模型时，
会重建当前文件所有帧的自动成键；手工添加/移除的键及绝对距离的元素对规则继续
生效。普通键表中的氢键记录不会被当作普通键。自动氢键仍由独立开关及现有几何
判据控制。几何编辑继续保持已冻结的拓扑。旧版项目恢复此前的共价半径成键模型
及保存的系数；需要新判据时选择 **Chemcraft pair ranges**。

选择 **Space filling** 后，**VESTA radii** 可以选择 Atomic、Ionic 或
van der Waals；**Atom size 100%** 就是所选表中的原始半径。Space-filling
尺寸与球棍尺寸分别保存，切换显示类型时不会相互覆盖。Ionic 使用表中代表性
价态/配位数的数值，不自动判断当前结构中每个原子的离子状态。

成键表覆盖 H–Db；未覆盖的元素使用明确记录的共价半径回退。兼容色板覆盖 H–Sg；
未覆盖元素使用中性灰。VESTA 表覆盖 H–Am，另含 D 和 XX；超出范围的元素使用
XX 占位半径。原子图例、图像导出和选择拾取使用同一套颜色/实际显示尺寸。

参数和格式解析依据见[详细来源](display_reference_data.md)，测试及渲染记录见
[验证报告](VALIDATION_v2.9.0.md)。本包为源码，Windows 独立 EXE 需重新构建。
