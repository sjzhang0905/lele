# LELE v2.11.0 复验记录

日期：2026-11-02。

**781 项测试和 78 个子测试全部通过，0 失败、0 错误、0 跳过，耗时约 47.3 秒。** 本次包括原始 QE 四份文件、CP2K Molden、POSCAR1/POSCAR2 和用户提供的旋转脚本约定检查。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 全量回归 | 781 测试与 78 子测试通过，无失败或跳过 | [完整 XML](qa_v2.11.0/full_v2110.xml)、[日志](qa_v2.11.0/full_v2110.log) |
| 针对性回归 | 54 测试、6 子测试通过，无跳过 | [针对性 XML](qa_v2.11.0/targeted_v2110.xml)、[日志](qa_v2.11.0/targeted_v2110.log) |
| 实际 POSCAR 对照 | 同一旋转作用于晶胞与原子，并采用第 20 个原子为中心的最近周期像；100 原子顺序保留 | [样例记录](qa_v2.11.0/supplied_poscar_pair.json) |
| 脚本约定 | 与提供的 v13 脚本的原始单胞最近像及 Z 优先正交化矩阵一致 | `test_local_axes_match_supplied_rotation_script_without_pymatgen` |
| 图形界面 | 真实 Qt 重定向窗口、矩阵预览/粘贴、实际处理入口、表格刷新、撤销、网格同步和项目恢复通过 | 新增 GUI 用例；窗口已离屏渲染并目视检查 |
| A1–A3 回归 | 上一版的验收及扩展用例继续通过 | 全量报告中的 v2.10.1 用例 |

JUnit `tests` 汇总为 859，包含 78 个子测试；实际 `<testcase>` 元素为 781，不将汇总值当成 859 个独立测试函数。

## 本次修复的科学问题

旧版 `align_pair_to_axis` 使用了旋转矩阵，但周期结构在 XYZ 对齐时只旋转原子、保持晶胞不动。周期镜像平移仍沿旧晶胞方向，因而这不是完整无限晶体的刚性坐标变换。旧版两个测试明确要求晶胞固定；本次按照用户要求更新了这些过时断言，同时保留 a/b/c 固定晶胞编辑的回归。

新增测试直接核对晶胞 Gram 矩阵、全部周期原子间距离、原点、正交性、行列式和能量等价性，覆盖斜晶胞、跨边界键及部分周期方向。最近周期像变换同步更新冻结的普通键和氢键平移；不会把跨边界短键画成错误的长对角线。

新窗口的三原子模式与提供的旋转脚本采用相同的 Z 优先约定：X 方向投影到垂直于 Z 的平面，再按右手规则生成 Y。非垂直的原始两根键不会被剪切成直角。共线或重合方向、非正交矩阵、镜像矩阵及非有限数值会被拒绝。

体数据的网格几何与结构同步变换，数据数组不变；QE 完整力矢量同步旋转。刚性重定向保留能量和收敛标记；真实内部坐标改变仍使相应数据失效。项目保存、撤销和 Cartesian/Direct POSCAR 重新读取覆盖原子顺序与旋转晶胞。

## POSCAR1 → POSCAR2 实测

- 两份文件均为 100 原子，元素顺序相同；目标原点对应全局第 20 个原子。
- 由晶胞对应关系得到的行矩阵 Q 行列式约为 1.0000000000000067，正交误差处于 10⁻¹⁴ 量级。
- 完整精度矩阵下，最大原子坐标差为 **7.528901058151405×10⁻⁸ Å**，最大晶胞分量差约 **1.7763568394002505×10⁻¹⁵ Å**。
- 原始体积约 **4695.6302560431 Å³**，变换后只出现浮点舍入差。
- 使用操作说明中的 12 位小数矩阵也实际重建核对，最大坐标差仍小于 8×10⁻⁸ Å。
- 实际文件测试还逐一比较全部周期原子间距离，并导出 Cartesian POSCAR 后重新读取核对。样例和脚本只用于验收，未将其原始内容放入发布包。

## 运行方法与边界

```bash
LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

未提供私人文件路径时，相应实际文件用例会跳过；本次全部文件路径已设置，实际没有跳过。

环境：Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0；Linux，Qt offscreen / VTK EGL。窗口布局已实际截图检查，截图仅用于内部验证。未构建或运行 Windows EXE，未对 Windows 显卡、高 DPI 或安装分发作出验收声明。

操作步骤和矩阵约定见 [使用说明](FEATURES_v2.11.0_CN.md)。
