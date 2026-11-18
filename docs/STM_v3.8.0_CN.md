# PARCHG 与模拟 STM

打开 VASP 的 `PARCHG*` 文件后，在 Analysis 菜单打开 Simulated STM。
包括 `PARCHG+0.3`、`PARCHG-0.3`、`PARCHG.0001.ALLK` 等文件名。

## 两种模式

- **Constant height**：在最外层原子向真空方向指定高度处，绘制部分电荷密度。
  色标是 e/Å³，可用对数色标。它对应简单针尖近似下的相对电流对比。
- **Constant current (isodensity)**：从真空中点向表面逐层搜索指定密度的首次交点，
  在相邻采样面之间作线性插值。色标是相对最外层原子的向外高度（Å）。
  输入是密度等值值，不是绝对电流 nA；PARCHG 本身没有针尖和实验电流的校准信息。

两种模式都可选择晶格面、上/下表面、面内重复单元、色图和可选的密度高斯平滑。
双通道共线自旋文件可选择 total、up、down，其中 up/down = (total ± magnetization)/2。
默认不平滑。平滑参数明确使用网格点单位，不会修改输入数据。

最大无原子周期空隙用于识别真空和展开跨越晶胞边界的 slab；搜索限制在所选表面到
真空中点的范围，避免拾取周期重复 slab 的另一表面。不存在交点或真空起点已经高于
等值值的像素显示为空白，CSV 保留为 NaN。找不到至少 1 Å 的空隙时提示换面。
复杂多 slab 结构应先检查此自动真空识别是否符合预期。

斜晶胞保留面内真实几何；取样沿该平面的实际法向进行，而不是直接把倾斜的第三晶矢
当作扫描方向。默认扫描步长保证三个网格方向的变化均不超过半个网格点，避免强倾斜
晶胞中的横向密度细节被跨过。输入结构晶胞必须与密度网格一致。

## 文件与导出

- VASP 网格按 x 最快、z 最慢还原。密度沿用 `原始值 / 晶胞体积` 的归一化；
  网格积分满足 `sum(raw)/Ngrid`。不会再次除以网格点数。
- PARCHG 的能量窗口由原始计算中的 EINT/NBMOD 等参数决定。`+0.3` 文件名
  不足以证明其偏压或能量窗口，因此软件不会自动编造这一信息。
- 工具栏或 Export image 导出 SVG/PNG 等；SVG 保留矢量文字和坐标轴，密度热图
  作为图像嵌入，避免数万像素生成巨大的 SVG。PNG 的分辨率和平滑由统一导出框选择。
- Export samples CSV 输出每个真实计算采样点的面内位置、密度/高度及参数说明。

## 方法参考与实现边界

p4vasp 的 STMWindowApplet 将固定网格平面用于恒高图，将 createCCPlane 系列
用于恒流等密度面，并提供密度平滑和图像插值。LELE 根据同一物理思路独立实现，
未复制 GPL 代码；增加了真实法向扫描和无交点掩码。

- p4vasp upstream: https://github.com/orest-d/p4vasp
- p4vasp 原始 STMWindowApplet 源码的发行包镜像：
  https://www.apt-browse.com/browse/ubuntu/xenial/universe/amd64/p4vasp/0.3.29%2Bdfsg-3/file/usr/lib/python2.7/dist-packages/p4vasp/applet/STMWindowApplet.py
- VASP STM 方法说明： https://vasp.at/wiki/Partial_charge_densities_and_STM_simulations
- VASP 网格归一化与积分公式： https://vasp.at/wiki/CHGCAR
- PARCHG 文件与自旋通道： https://vasp.at/wiki/PARCHG

这属于常用 Tersoff–Hamann 思路下的部分密度对比图，不包含具体针尖电子结构、
轨道方向性或绝对电流的独立计算。

## 随附样本验证

用户提供的 `PARCHG+0.3` 为 38 原子、168×168×480 单通道网格。
识别为 VASP PARCHG，表面法向 z，无原子空隙约 13.5741 Å。
恒高 2 Å 的密度范围约 4.75718×10⁻⁵ 至 2.82456×10⁻⁴ e/Å³。
以该图中位数 1.7981113×10⁻⁴ e/Å³ 作恒流等值值，全部像素均得到交点，
高度约 1.43044–2.20386 Å。验证记录与预览保存在 verification/v3.8.0。
