# LELE v2.12.0 复验记录

日期：2026-11-02。

**806 项测试和 78 个子测试全部通过，0 失败、0 错误、0 跳过，耗时约 73.5 秒。**

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 全量回归 | 806 测试、78 子测试通过，无失败或跳过 | [XML](qa_v2.12.0/full_v2120.xml)、[日志](qa_v2.12.0/full_v2120.log) |
| 针对性测试 | 97 测试、3 子测试通过，无失败或跳过 | [XML](qa_v2.12.0/targeted_v2120.xml)、[日志](qa_v2.12.0/targeted_v2120.log) |
| 原生 VTK 渲染 | 分数占据扇区、浅灰空位和绿色虚线外环已实际渲染及目视检查 | [PNG](qa_v2.12.0/partial_selection_native.png)、[像素核对](qa_v2.12.0/native_render_validation.json) |
| 真实 Qt 控件 | 原子编号、交换编号和真空层弹窗已实际截图、目视检查；操作和撤销有 GUI 用例 | 新增交互回归用例；截图仅作内部验证 |
| 旧实际文件 | QE 四份文件、CP2K Molden、POSCAR1/POSCAR2 及旋转脚本约定测试继续执行并通过 | 全量 XML 中的实际文件用例 |

JUnit `tests` 汇总为 884（包含 78 个子测试），实际 `<testcase>` 元素为 806。新增永久回归位于 `tests/test_structure_edits_v2120.py`，共 25 个参数展开后的用例。旧的右击“无条件清空”事件断言根据新需求更新为发出带鼠标位置的原子上下文请求；空白处清空、右拖和 Alt 拖动仍有回归。

## 数据与几何检查

- CIF：合成 P1 样例中 Fe 0.6 / Ni 0.4 同位点和 O 0.5 位点没有整数化；P-1 对称性展开后的占据率映射正确。CIF 导出重读保留各位点概率及晶胞度量；不支持占据率的格式不会静默生成满占模型。Boundary、扩胞、删除、LELE 剪贴板及项目保存恢复保留占据率。混占中的少数组分出现在图例，加权组成和电子奇偶性显示正确。
- 原子编号：指定新行与两原子交换均检查坐标、元素、颜色和占据率跟随；QE 力数组与周期键、氢键索引/平移方向同步重映射。POSCAR 重新读取保留新顺序。实际右击处理入口、两选区交换、空白清选和 Ctrl+Z 有 GUI 检查。
- 真空层：正交、斜晶胞及整体旋转后的 slab 都按表面法向检查。目标真空 4、12、30 Å 等情况只改变对应晶胞矢量的法向分量，原子笛卡尔数组逐项不变，另外两条晶胞矢量保持不变。跨边界分裂的代表坐标、负值和非有限值被拒绝，未发生部分变更。GUI 调整与撤销恢复原晶胞和能量。
- 底部对齐：窗口尺寸变化时，摘要文本与 Coordinates 标签页左边缘差不超过 1 个 Qt 逻辑像素。
- 选中轮廓：原生 VTK 的绿色轮廓包含 32 个有间隙的线单元，不含填充面；相机跟随且不可拾取。900×520 画面中轮廓有 1632 个绿色像素，选中前后原子中心 29×29 区域的最大通道差为 0，原子色和中心编号未被选中覆盖物改变。隐藏和全透明原子的既有行为继续通过。

新增 CIF 用例为可重现的合成数据，本次没有收到用户的实际分数占据 CIF。未声称覆盖所有 CIF 方言、所有无序组装语法或通过平均占据率确定唯一微观有序结构。

## 环境与执行

Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0；Linux、Qt offscreen / 原生 VTK EGL。

```bash
LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

私人样例路径未设置时，对应实际文件测试会跳过；本次已设置，实际无跳过。此前私人计算文件和两个原始脚本未加入源码发布包。交付为源码更新，未构建或运行 Windows EXE，Windows 图形驱动和高 DPI 的人工验收仍不在已验证结果内。

操作和数据含义见 [v2.12.0 使用说明](FEATURES_v2.12.0_CN.md)。
