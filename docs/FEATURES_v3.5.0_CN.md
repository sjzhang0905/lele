# LELE v3.5.0 使用说明

日期：2026-11-09。在 v3.4.0 基础上实现六项界面与 NMR 改动，保留原有 ESP 映射和等值面叠加。

## 1. 选中原子的独立显示

选中一个或多个原子，在 **Atoms → Atom appearance → Selected style** 中选择：

| 选项 | 行为 |
|---|---|
| Use global style | 跟随 Style 页中的整体显示方式，清除当前原子的样式覆盖 |
| Ball and stick | 球棍 |
| Space filling | 空间填充，采用现有 VESTA 半径设置 |
| Sticks | 棍状 |
| Wireframe | 线框 |

普通键的两个半段分别跟随两端原子；空间填充的一端隐藏对应半段。整体 Bonds 开关仍控制是否画普通键。颜色、透明度和标签可继续独立调整。混合占据的同一位置共用显示样式。

该设置应用于本文件中具有对应原子身份的帧，支持 Ctrl+Z、Boundary 映像和 `.lele` 工程保存。结构坐标与元素不因显示设置而改变。

## 2. Atoms 排序与坐标联动

元素按文件中首次出现的顺序排列；混合占据 CIF 使用保留的原始组分行顺序。新打开或切换文件时默认折叠；普通重绘保留已经手动展开的组。

在底部右侧 **Coordinates** 双击第一列的原子名称，例如 `12 C`，会切到 Atoms、展开对应元素并选中该原子。双击数值列仍用于坐标编辑。

## 3. NMR 表格和谱图

打开计算输出文件后，从 **Analysis → NMR spectrum / shielding table…** 进入。只有 NMR 结果、没有结构的文件也可打开，并在结果页面显示入口。

| 程序 | 本版识别的文本结果 |
|---|---|
| Gaussian | Magnetic shielding / SCF GIAO 等屏蔽块，Isotropic、Anisotropy 和完整 XYZ 张量；多计算块分开 |
| ORCA | CHEMICAL SHIELDINGS 的总张量及 CHEMICAL SHIELDING SUMMARY；原始 0 起始编号转成 LELE 的 1 起始编号 |
| NWChem | Chemical Shielding Tensors 中的 Total Shielding Tensor、isotropic、anisotropy |
| VASP | CSA 的旧式 ISO_SHIFT 表和新版 BDIR / ISO_SHIELD 表；价电子/含核、含/不含 G=0 分开 |
| CP2K | NMR 的 SHIFT / SHIELDING_TENSOR 打印文件（常见 `.data`），读取原子位置处 SIGMA TOTAL；只读该文件输出的核 |
| Quantum ESPRESSO | `gipaw.x` 的 Total NMR chemical shifts/shieldings in ppm 区段及 Total sigma；不把前面的分项贡献重复计数 |

这些是已验证的常见输出格式，不代表穷尽各程序全部版本和 NMR 方法的输出。普通输入文件本身不包含计算结果。

### 图表操作

1. **Calculation / dataset** 选择计算块，**Element** 选择元素。默认展示绝对屏蔽常数 `σ`。
2. 如需化学位移，在 **σref (ppm)** 输入该元素的参考屏蔽值，再选 **Chemical shift δ**。本版使用 `δ = σref − σ`，参考物的位移零点取 0；参考值按数据集和元素保存。没有参考值时保留原始屏蔽结果，化学位移图不生成。
3. 可选择 Sticks、Lorentzian 或 Gaussian，调节 FWHM（ppm）。化学位移横轴从左向右递减。线宽相对范围过窄、会导致欠采样时提示增大 FWHM 或改用 Sticks。
4. 表格可排序；点击一行查看完整打印张量。双击在有匹配原始结构的情况下定位该原子。结构被编辑或没有可靠结构对应关系时不给出错误定位。
5. **Export all nuclei CSV** 导出当前数据集全部元素的数值和来源。**Export displayed spectrum CSV** 导出当前元素曲线；Sticks 导出峰位置及权重。**Save plot PNG / SVG** 导出谱图。

参考值须由用户按照所用方法、基组和参考物选择。软件没有内置猜测的 TMS 屏蔽值。VASP 的旧 ISO_SHIFT 是未加参考的绝对 shift，导入时取负号转换为 shielding；原始值与约定保留在 CSV/数据说明中。不同程序的各向异性采用其打印约定，VASP 的 SPAN 单独保存，不冒充 Anisotropy。

本版谱图是各核等面积线的显示与展宽，不包含 J 耦合多重峰、同位素丰度、固体粉末谱、等价位点平均、构象 Boltzmann 加权或额外顺磁位移修正。对于周期固体，图中的各向同性线也不应当作完整实验固体 NMR 谱。

## 4–6. 新布局

| 位置 | 内容 |
|---|---|
| 左侧 | Files、Atoms、Style、Edit |
| 底部左侧 | Axes、Labels、Field、Boundary |
| 底部右侧 | Coordinates、Input / output text、Results / info |
| View 菜单 | Crystal tools…、Dipole…；原有晶面/多面体快捷菜单保留 |

两个底部区域可拖动分隔条调整宽度。设置页内容较多时可以滚动。Crystal 和 Dipole 是可反复打开的独立设置窗口，切换文件时显示当前文件的数据。

## 演示与来源

`examples/nmr_v350/synthetic_nmr_display.lele` 可直接打开，演示三种原子样式与人工 NMR 数据。该文件使用人工 H 参考屏蔽值 31 ppm；所有示例数值仅用于界面和解析验证，不是分子预测结果。

输出格式核查依据：

- ORCA：https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/nmr.html
- VASP：https://vasp.at/wiki/LCHIMAG 、https://vasp.at/wiki/LNMRSHIELD 、https://vasp.at/wiki/LNMRLEG
- CP2K：https://manual.cp2k.org/trunk/CP2K_INPUT/FORCE_EVAL/PROPERTIES/LINRES/NMR/PRINT/SHIELDING_TENSOR.html 及 https://github.com/cp2k/cp2k/blob/master/src/nmr_shift.F
- QE/GIPAW：https://github.com/dceresoli/qe-gipaw/blob/master/examples/quartz/quartz-nmr.out
- NWChem：https://nwchemgit.github.io/Properties.html 及官方论坛 https://nwchemgit.github.io/Special_AWCforum/sp/id6855.html
- Gaussian 张量打印顺序核对：https://github.com/cclib/cclib/blob/master/cclib/parser/gaussianparser.py
