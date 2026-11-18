# LELE 3.6.0 固定原子信息读取范围

日期：2026-11-10

Selection 的 `Fixed X/Y/Z` 使用 **T=该方向固定、F=该方向未固定**。这与 POSCAR 源文本中 `F=固定、T=允许移动` 的符号含义相反；界面显示的是统一的“是否固定”。没有可靠信息时不生成全 F；编辑后来源未知的原子用 `—`。鼠标提示说明约束方向属于 Cartesian 还是 Direct。

固定键长、键角、二面角、质心、刚性分子/片段，以及谐振子式 restraint，都不等于把参与原子固定在空间。它们不会被误转为逐原子的 T。

## 已实现并验证的语法

| 输入来源 | 读取内容 | 方向与说明 |
| --- | --- | --- |
| VASP POSCAR/CONTCAR、带相同结构头的体数据 | `Selective Dynamics` 三个 T/F；包括显式全自由 | Direct；与坐标记录写成 Cartesian 或 Direct 无关 |
| CP2K `.inp`、`.restart` | `MOTION/CONSTRAINT/FIXED_ATOMS`；重复段、重复 `LIST`、续行、`COMPONENTS_TO_FIX` | Direct。关键词定义和 CP2K 源码明确规定约束分数坐标，不能因教程中泛称 xyz 而标为 Cartesian |
| ORCA 输入 | `%geom Constraints` 中 `{ C n C }`、`{ X/Y/Z n C }`、`n:m`；`optimizeHydrogens true`；明确的 MD `Constraint Add Cartesian` 与 `Remove All` | Cartesian；ORCA 原始编号从 0 开始，LELE 表格从 1 开始 |
| Gaussian `.gjf`、`.com` | Cartesian 坐标前的 `-1/0` freeze code；`ModRedundant` 的单原子 `X n F/A`、`n F/A`；`ReadOpt` 的 `noatoms / atoms / notatoms`、范围、元素列表；`NoFreeze` | Cartesian；ReadOpt 列出的是允许优化的原子，不能把该列表解释成固定列表 |
| Quantum ESPRESSO 输入 | `ATOMIC_POSITIONS` 后的 `if_pos` 三个 0/1；同一段内未写标志的记录按 QE 默认 1 处理 | Cartesian 力分量；输入坐标为 `crystal` 也不改变其方向定义 |
| SIESTA `.fdf` | `GeometryConstraints` / `Geometry.Constraints`；`atom/position`、`from…to/plus/minus…step`、方括号范围、`all`、`Z`、`species-i`、`clear/clear-prev` | Cartesian；明确沿单一轴的方向向量可以显示为该轴固定 |
| NWChem 输入 | `constraints` 的 `fix atom`、整数范围、命名约束组与 `set constraints`、`clear/enable/disable` | Cartesian；仅使用实际选中的约束组 |
| ASE 结构/轨迹中确实保留的约束 | `FixAtoms`、`FixCartesian`、`FixScaled` | 区分 Cartesian / Direct；混合两种基底的部分固定不强行合并 |

Gaussian 几何读取同时修正了 ASE 对 freeze code、全整数 Cartesian 坐标、逗号分隔记录的兼容问题，并处理 `Units=AU/Bohr` 与小写 `Tv`。这些转换只发生在内存中，不改原文件字节。普通 Z-matrix 保留原读取器行为；不会把内部坐标数字误当 Cartesian。

## 输出文件与其他结构格式

QE 输出若实际打印 `ATOMIC_POSITIONS` 的 `if_pos`，会随该帧读取。xTB 输出若实际打印完整 `Fixed Atoms` 表，会按原子编号、元素和原子序数交叉核对；只有匹配当前结构才保留，MD 命令不沿用被禁用的 exact fixing。以上信息在现有输出扫描中提取，不额外整文件重读。

对于 Gaussian、ORCA、CP2K、SIESTA、NWChem、VASP 等其他输出，不能只根据零受力、两步坐标相同、约束总数或原子排序推断谁固定。当前未解析到明确逐原子标志的输出和 XYZ/XDATCAR/ANI 轨迹会显示“信息缺失”，不会假设全自由；不会自动去旁边另一个输入文件复制约束。

也检查了当前普通结构与电子结构入口：CIF、普通 XYZ、PDB/PQR、MOL/SDF/MOL2、XSF、GEN、CFG、GRO/G96、SHELX RES、XSD/XTD、XV、WIEN2k STRUCT、CUBE、FCHK、Molden、WAVECAR/GBW、振动/独立 NMR 结果。它们不是统一的计算约束输入；仅在底层读取器实际给出明确 ASE 约束时保留，其他情况下不杜撰固定信息。CIF 的占据率、PDB 温度因子等也不会误用作固定标志。

## 需要真实样本才能进一步验证的复杂情况

- Gaussian Link1/QST 多结构、ONIOM 层/刚性 block/残基选择、复杂 GIC、带固定变量的 Z-matrix、使用弧度的 Z-matrix。
- ORCA 多作业和 `FixFrags/RelaxFrags` 等片段约束，以及运行中更改约束的 MD 输出。
- CP2K 多 `FORCE_EVAL`、QM/MM 或 `MOLNAME` 选择器、外部 include 中的约束；`RESTRAINT` 只标注为软约束，不视为固定。
- SIESTA 非轴方向向量、集体/刚体约束，以及不在当前文件内的 species/坐标定义。
- NWChem 多 task 切换约束组；不同程序输出中单独打印的固定原子清单。
- xTB 独立 xcontrol `$fix/$constrain`、Turbomole `$coord` 配套控制文件。目前没有可独立确定结构与编号的该类输入入口，需要与其几何文件成对提供；普通 xTB XYZ 不包含这些设置。

固定约束解析不确定时仅保留说明，不会生成可能错误的 T/F。对可能导致几何误读的单位或坐标写法则明确拒绝，例如当前未实现的弧度 Z-matrix。

## 核对依据

- [VASP POSCAR：Selective dynamics](https://www.vasp.at/wiki/index.php/POSCAR)
- [CP2K FIXED_ATOMS 关键词](https://manual.cp2k.org/trunk/CP2K_INPUT/MOTION/CONSTRAINT/FIXED_ATOMS.html)；[对应源码](https://github.com/cp2k/cp2k/blob/master/src/input_cp2k_constraints.F)
- [ORCA 几何优化约束](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations.html)；[ORCA MD 约束](https://orca-manual.mpi-muelheim.mpg.de/contents/moleculardynamics/moldyn.html)
- [Gaussian 分子规格](https://gaussian.com/molspec/)与 [Opt](https://gaussian.com/opt/)；官网读取受限时核对其日本授权代理公开的 [Opt 文档](https://www.conflex.co.jp/gaussian_support/opt.php)、[ONIOM 文档](https://www.conflex.co.jp/gaussian_support/oniom.php)
- [QE PW 输入定义](https://www.quantum-espresso.org/Doc/INPUT_PW.html)
- [SIESTA 5.4 手册](https://docs.siesta-project.org/projects/siesta/en/5.4/reference/siesta.html)
- [NWChem Constraints](https://nwchemgit.github.io/Constraints.html)
- [xTB exact fixing 与 constraining potentials](https://xtb-docs.readthedocs.io/en/latest/xcontrol.html)
