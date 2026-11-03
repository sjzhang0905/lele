# LELE v2.10.1：A1–A3 修复说明

日期：2026-11-02。基于本次上传的 v2.10.0 源码和独立验收报告修复。

| 问题 | 修复后的行为 |
| --- | --- |
| A1：QE 达到最大步数仍显示收敛 | 只有明确的 `bfgs converged` 才确认优化成功。单独的 BFGS 结束提示或 `JOB DONE` 不标记收敛；同一 PWSCF 任务内的失败、最大步数和错误信息优先。 |
| A2：CP2K 晶胞与原子重复混用 | `CELL/MULTIPLE_UNIT_CELL` 只扩展晶胞，`TOPOLOGY/MULTIPLE_UNIT_CELL` 只复制原子坐标。分数坐标转换和复制平移都使用原始单胞。 |
| A3：CP2K `ANGLES` 被忽略 | 与 `ALPHA_BETA_GAMMA` 使用同一角度解析，支持默认度数及 `[deg]`、`[rad]`；保留非正交角度和体积。 |

QE 的普通程序完成状态与优化收敛分别保存。成功后的相同最终结构、相同结构上的最终 SCF 求值仍按原有记录规则保留；新结构不会仅因早先出现过成功提示而继承收敛。串接的不同 PWSCF 任务互不影响。

CP2K 验收中的单个 He、4 Å 单胞案例，读取结果为：

| CELL 重复 | TOPOLOGY 重复 | 原子数 | 晶胞边长 / Å | 原子 x 坐标 / Å |
| --- | --- | ---: | --- | --- |
| 2×1×1 | 默认 | 1 | 8、4、4 | 1 |
| 默认 | 2×1×1 | 2 | 4、4、4 | 1、5 |
| 2×1×1 | 2×1×1 | 2 | 8、4、4 | 1、5 |
| 默认 | 默认 | 1 | 4、4、4 | 1 |

这些是读取器的独立参数验收。CP2K 当前源码在 TOPOLOGY 实际复制原子时要求两处重复数一致，因此不一致时 LELE 保留两项输入含义，并在读取说明中提示该计算兼容性要求。表格不表示每种参数组合都是可直接运行的 CP2K 作业。

`ABC 4 4 4` 配合 `ANGLES 90 90 120` 的体积现在约为 **55.42562584 Å³**。缺失、非法或无法支持的角度单位会给出读取说明并不生成伪造的几何结构。非法重复数、缺少重复平移所需晶胞以及过量原子复制也会明确报告。

原有 10 个独立验收用例已作为 `tests/test_acceptance_v2101.py` 纳入回归；扩展用例位于 `tests/test_qe_cp2k_fixes_v2101.py`。旧的 QE 长轨迹成功样例补上真实的明确收敛行，失败样例仍保留 BFGS 结束行，避免再次漏测两行同时出现的情况。

格式依据：

- [QE 官方 BFGS 终止实现](https://github.com/QEF/q-e/blob/develop/Modules/bfgs_module.f90)：`terminate_bfgs` 区分明确成功、失败和最大步数；不同分支都会打印结束提示。
- [CP2K CELL 定义](https://manual.cp2k.org/cp2k-2026_1-branch/CP2K_INPUT/FORCE_EVAL/SUBSYS/CELL.html)：晶胞重复和 `ANGLES` 别名、角度单位。
- [CP2K TOPOLOGY 定义](https://manual.cp2k.org/cp2k-2026_1-branch/CP2K_INPUT/FORCE_EVAL/SUBSYS/TOPOLOGY.html)：坐标重复的独立含义。
- [CP2K 原子坐标读取](https://github.com/cp2k/cp2k/blob/master/src/atoms_input.F)与[原子复制实现](https://github.com/cp2k/cp2k/blob/master/src/topology_multiple_unit_cell.F)：原始单胞、复制平移、X 方向优先顺序及重复数兼容性。

具体复验结果和运行边界见 [v2.10.1 验证记录](VALIDATION_v2.10.1.md)。
