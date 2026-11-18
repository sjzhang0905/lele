# 周期性输入的“应用新坐标”范围（v3.6.0）

操作直接替换原文本中的结构数值，不重新生成整份计算输入。换行、非结构参数、基组、赝势、计算设置和原有注释保留。对不能可靠建立原子对应关系的输入，会拒绝生成修改结果，并提示提供样本。

| 输入 | 已处理结构写法 | 晶胞与单位 |
|---|---|---|
| CP2K `.inp` / `.restart` | 单个 FORCE_EVAL / SUBSYS 的内嵌 COORD；KIND / ELEMENT 别名；Cartesian / SCALED | A/B/C 矢量和 ABC / 角度；Å、Bohr、nm。ABC / 角度在需要更新时转换为显式 A/B/C，以保留旋转或倾斜晶胞的方向 |
| QE PW 输入 | `ibrav=0`，内嵌 ATOMIC_SPECIES / ATOMIC_POSITIONS / CELL_PARAMETERS | Cartesian Å / Bohr / alat，以及 crystal 分数坐标；保留现有单位。`A` / `a` 与 `celldm(1)` 正确换算；没有显式 alat 时按物理单位 CELL_PARAMETERS 第一矢量长度确定 |
| SIESTA `.fdf` | 内嵌 ChemicalSpeciesLabel / AtomicCoordinatesAndAtomicSpecies | Fractional、Ang、Bohr、ScaledCartesian 及官方别名；LatticeVectors 或 LatticeParameters；保留 LatticeConstant 比例 |

周期性画布结构将当前晶胞写入周期性目标；孤立画布结构写入周期性目标时使用 30 × 30 × 30 Å 晶胞，不自动平移或包裹坐标。

**CP2K `PERIODIC NONE` 是例外：** CP2K 的非周期计算仍需 CELL 定义积分网格。本版保留目标的 CELL 与 PERIODIC / Poisson 等设置，仅替换坐标，不删除必须的计算网格。

## 原子顺序与原子数

普通模板允许原子顺序改变：新的元素必须能唯一映射到目标已定义的 KIND / species，不猜测或生成新的基组和赝势。如果同一元素有多个 KIND / species，只有原有顺序且未经过重排时才保留对应标签。

不同原子数仅在安全的纯坐标模板中允许。坐标行不能含需要对应到原子的额外字段或行尾注释；输入也不能含原子编号、固定约束、速度、COLVAR、磁矩或类似专属记录。通过检查时替换原子记录，并同步 QE `nat`、SIESTA `NumberOfAtoms` 或 CP2K `TOPOLOGY/NUMBER_OF_ATOMS`（原有时）。这些计数属于结构信息。

原子重排后，CP2K 的 MOLNAME、COLVAR、QMMM/CDFT 和原子编号关键词，以及 QE 逐轴 flags、约束、速度/力、HUBBARD 等记录，不进行未经验证的身份映射。SIESTA `DM.InitSpin`、`DM.InitSpin.AF`、MD.FCfirst/FClast、传输原子设置和未知非全局块也按此原则拒绝。

## 需要样本的复杂输入

包括 CP2K 外部坐标、预处理/变量、多个 FORCE_EVAL、MULTIPLE_UNIT_CELL 展开、强制晶胞 SYMMETRY；QE 非零 ibrav、crystal_sg 与空间群生成原子；SIESTA include / 重定向、Zmatrix、SuperCell、AtomicCoordinatesOrigin、ghost/custom species。拒绝发生在写文件之前。

## 验证

用户提供的 `RuO2-1.restart`（216 个原子）与 `NCM111_PBEU_geoopt-1.restart`（36 个原子）均已通过新坐标替换再读取。最大坐标误差分别约 5.0×10⁻¹⁴ Å、7.1×10⁻¹⁵ Å；所有非结构行逐行一致，原文件未修改。记录在 `verification/v3.6.0/periodic_template_actual_samples.json`。

测试还覆盖旋转晶胞、分数坐标、单位换算、CRLF、注释和原参数保持、纯模板增删原子、复杂/危险映射拒绝，以及 QE A/alat 的“读取 → 准备替换 → 验证读取”完整流程。

## 语法依据

- [CP2K COORD](https://manual.cp2k.org/trunk/CP2K_INPUT/FORCE_EVAL/SUBSYS/COORD.html)
- [CP2K 非周期计算仍需 CELL](https://github.com/cp2k/cp2k/blob/master/docs/getting-started/first-calculation.md)
- [Quantum ESPRESSO PW 输入说明](https://www.quantum-espresso.org/Doc/INPUT_PW.html)
- [QE cell_base 单位与重复 lattice-parameter 校验](https://gitlab.com/QEF/q-e/blob/develop/Modules/cell_base.f90)
- [SIESTA 5.2 参考手册](https://docs.siesta-project.org/projects/siesta/en/5.2/reference/siesta.html)
