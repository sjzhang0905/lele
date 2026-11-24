# 固定原子、静电势与空穴–电子分布

## 固定原子

| Edit 菜单 | 快捷键 | 作用 |
| --- | --- | --- |
| Fix selected atoms | Ctrl+F | 固定选中原子的三个方向 |
| Clear fixed axes on selected atoms | Ctrl+Shift+F | 清除选中原子的全部方向约束 |
| Select fully fixed atoms | Ctrl+Alt+F | 选中当前帧三个方向均固定的原子 |

快捷键修改当前结构帧的优化约束。可用 Ctrl+Z 撤销，也可以保存到 LELE 项目。Current selection 中的 Fixed X/Y/Z 用 T 表示固定，鼠标提示标明 Direct 或 Cartesian 基底。原文件中只固定一个或两个方向的原子会保留原标记。

File → Export structure 可直接写出新的 POSCAR 或 Gaussian GJF。POSCAR 的 Selective dynamics 用 F 表示固定，T 表示可移动，三个标志始终沿直接晶格方向。导出时重新合并元素分组，固定标记随原子一起排序。外部程序的 Cartesian 部分固定在晶格能准确表示该运动方向时可转写，不能表示时导出窗口会提示具体原子。GJF 对整原子固定写入 -1，同一坐标段中其余原子写入 0。仅部分固定的位点在 GJF 中可移动，具体编号见导出提示，GJF 标题也记录该项转换。计算类型沿用结构导出的默认路由，运行 Gaussian 几何优化时要在路由中使用 Opt。

输入支持 POSCAR/CONTCAR、Gaussian、ORCA、CP2K、QE、SIESTA、NWChem 中可确定的逐原子约束。输出可读取 Gaussian 的显式冻结列或单原子 ModRedundant 回显、ORCA 的输入回显、CP2K 回显中的 FIXED_ATOMS、SIESTA 与 NWChem 回显输入中的固定段、QE 的 if_pos、xTB 的 Fixed Atoms 表，以及带 Selective dynamics 标志的 XDATCAR。vasprun.xml 和 ASE 结构可使用对应读取器保留的逐原子约束。仅有位置和力的 OUTCAR、普通 XYZ 和常规 XDATCAR 通常没有逐原子固定信息。缺失记录保持未知。

## 从两份本地文件绘图

| Analysis 菜单 | 第一栏 | 第二栏 | 图形 |
| --- | --- | --- | --- |
| Electrostatic potential (ESP)… | 电子密度 CUBE 或 CHGCAR/CHG | ESP CUBE 或 LOCPOT | 在密度等值面上按电势着色，带色标 |
| Electron–hole distribution… | electron CUBE | hole CUBE | 电子为浅绿色，空穴为青色，两个图层可独立设置 |

1. 在 Analysis 选择对应功能。即使尚未打开结构文件，也可以使用。
2. 用两行各自的 Browse 选择文件。多数据集 CUBE 可在 Dataset 中指定通道。按显示的场单位输入等值，点击 Plot。
3. 结果进入独立文档。Field → Surface layers / ESP mapping 可继续调节颜色、透明度、等值或 ESP 色标范围。File → Save PNG 可导出当前视图。LELE 项目会保存两个选定网格和图层。

ESP 采用两个文件中的原子顺序及笛卡尔坐标核对结构，周期场另核对晶胞。密度与电势可以使用不同的网格分辨率。LELE 在密度表面顶点的实际空间位置三线性采样电势。电势网格仅覆盖部分表面时，未覆盖顶点显示为灰色。普通 CUBE 标量单位以产生该文件的程序为准。

VASP 应选同次计算的 CHGCAR（或 CHG）以及用 LVHAR = .TRUE. 生成的离子势与 Hartree 势之和。CHGCAR 取总密度。对于一个、两个或四个数据块的 LOCPOT，标量势依次取唯一通道、上下自旋平均或第一个通道。LELE 将电子势能取负后显示为正试探电荷的静电势，单位为 V。周期势的参考零点沿用该次计算。ESP CUBE 使用文件自带的符号约定。LOCPOT 本身不能标明是否含交换关联项，应核对原计算的输出设置。

空穴–电子图适用于同一几何和同一激发态的一对密度。常规非负的 electron 和 hole 数据都使用正等值。若输入的空穴数据采用负值记号，可以为该层填写负等值。

## WAVECAR 的轨道 CUBE

将同一计算的 CONTCAR 或 POSCAR 放在 WAVECAR 旁，然后打开 WAVECAR。Field → VASP WAVECAR pseudo-wavefunction 中依次选择 Spin channel、k-point 和从 1 开始的 Band。选择 Re ψ、Im ψ 或单态密度 |ψ|²，点击 Reconstruct WAVECAR field，再用 Field → Export active field CUBE 导出当前场。需要复波函数时，将实部和虚部分别保存。没有坐标文件时，LELE 也可用同目录中唯一能匹配晶格的受支持 OUTCAR 的末帧作为参考结构。

上述重建适用于已验证的全复数标量格式（45200、45210），支持单自旋和共线双自旋。实部与虚部取 WAVECAR 保存的相位，单态密度没有乘占据或 k 点权重，且不含 PAW 现场增强。Γ 点的全复数存储可重建，Gamma-only 半存储与 SOC/非共线旋量布局超出当前范围。轨道能量和原始占据可在 Analysis → HOMO / LUMO and orbital energies 中查看。

[VASP WAVECAR](https://vasp.at/wiki/WAVECAR) · [POSCAR](https://vasp.at/wiki/POSCAR) · [LVHAR](https://vasp.at/wiki/LVHAR) · [LOCPOT](https://vasp.at/wiki/LOCPOT) · [势的符号约定](https://vasp.at/forum/viewtopic.php?t=19993)
