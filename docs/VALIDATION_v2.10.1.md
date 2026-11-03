# LELE v2.10.1 复验记录

日期：2026-11-02。修复范围为本次 v2.10.0 独立验收的 A1–A3。

**结果：757 项测试与 78 个子测试全部通过，0 失败、0 错误、0 跳过，耗时 43.80 秒。** 原始独立验收脚本从修复前的 4 失败、6 通过，变为修复后的 10 项全部通过。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 修复前独立复现 | 4 失败、6 通过；分别对应 A1、A2 两种情形、A3 | [原版结果](qa_v2.10.1/independent_before.xml) |
| 修复后原始独立脚本 | 10 通过，无失败或跳过 | [修复后结果](qa_v2.10.1/independent_after.xml) |
| 全量回归 | 757 测试、78 子测试通过，0 失败、错误、跳过 | [完整 XML](qa_v2.10.1/full_v2101.xml)、[日志](qa_v2.10.1/full_v2101.log) |
| 新增永久用例 | 保留独立验收的 10 项，另加 40 项扩展用例 | `tests/test_acceptance_v2101.py`、`tests/test_qe_cp2k_fixes_v2101.py` |
| 原始私人样例 | 原有四份 QE 文件和 CP2K Molden 文件的实际文件测试均执行并通过 | 全量报告中的 `test_real_supplied_qe_files`、`test_actual_124_atom_example_all_frequencies_and_frozen_rows` |
| 原始源码保留 | 原包 452 个文件均保留；只修改其中 7 个文件，并增加修复说明、测试和验证记录 | [源码核对](qa_v2.10.1/source_integrity.json) |

JUnit 的 `tests` 汇总值为 835（含 78 个子测试），实际 `<testcase>` 元素为 757，不将汇总值写成 835 个独立测试函数。

## 科学数据和状态检查

- QE：最大步数与 BFGS 结束行同时出现时不再标记收敛；普通 `JOB DONE` 不确认优化成功；明确成功继续生效。失败优先级、最终重复结构、新几何、独立 PWSCF 任务，以及项目保存恢复均有覆盖。
- CP2K：分别验证 CELL 单独扩展、TOPOLOGY 单独复制、两处相同和两处不等的重复数；包括分数坐标、Bohr 坐标、斜晶胞、原子种类/顺序和非 XYZ 周期性。复制使用原始单胞，X 方向索引变化最快。
- CP2K：`ANGLES`、`ALPHA_BETA_GAMMA`、显式 `[deg]` 与 `[rad]` 得到相同晶胞；γ=120° 和体积 55.42562584 Å³ 正确。无效角度、退化晶胞、无晶胞复制、非法及过量重复数不会静默生成错误结构。
- QE 实际 `job.out` 仍保留 5 个求值/结构记录、最终原始能量 −659.95599528 Ry、最终体积 56.0357202256568 Å³及明确收敛标记。PHONON 的 48 个频率与 matdyn 的 60 个模式继续通过原有独立断言；CP2K Molden 的 124 原子、6 个模式及固定原子零位移也通过。

四份 QE 文件 SHA256 与 v2.10.0 随包记录逐一相同；CP2K Molden SHA256 为 `6697fab213a9b8ba13513b897992ea8b90894cbab21e0e96e407c07cbde42cc7`。这些私人源数据未放入修复包。

## 运行方法和环境

在源码根目录安装依赖后运行：

```bash
LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

原始独立验收脚本和四个最小复现保存在 `docs/qa_v2.10.1/`，可单独运行：

```bash
PYTHONPATH=. python -m pytest docs/qa_v2.10.1/test_independent_acceptance.py -q
```

Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0；Linux，Qt offscreen / VTK EGL。未设置私人样例环境变量时，那两个实际文件测试会按设计跳过；本次已提供文件路径，实际无跳过。

完整回归保留现有原生 VTK 渲染、项目恢复、动画/导出、选择编辑和多格式长轨迹检查。此次交付为源码修复包，未构建或运行 Windows EXE；Windows 显卡、高 DPI 与可执行文件分发不属于本次已验证结果。

实现与格式依据见 [A1–A3 修复说明](FIX_A1_A3_v2.10.1_CN.md)。
