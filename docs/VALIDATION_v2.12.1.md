# LELE v2.12.1 复验记录

2026-11-02。基线为 `LELE_v2.12.0_20261102.zip`，SHA-256：`e24cbf92c0c425556335ca402b91670465ba0d3f899f3949f95ff3130cabf073`。修复说明见 [A1–B4 对照](FIX_A1_B4_v2.12.1_CN.md)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 独立验收原断言，修复前 | 12 项中 10 失败、2 通过 | [before.log](qa_v2.12.1/independent_before.log)、[before.xml](qa_v2.12.1/independent_before.xml) |
| 相同独立断言，修复后 | **12 通过，0 失败** | [after.log](qa_v2.12.1/independent_after.log)、[after.xml](qa_v2.12.1/independent_after.xml) |
| 完整回归，包含原始私人样例 | **852 项测试 + 78 个子测试通过；0 失败、0 错误、0 跳过；62.63 秒** | [full.log](qa_v2.12.1/full.log)、[full.xml](qa_v2.12.1/full.xml) |
| 原始 POSCAR1 | 100 个原子；原样、改真空、重编号均保留 96 个完全固定原子；逐原子标记及顺序另有永久回归断言 | [project_examples.json](qa_v2.12.1/project_examples.json) |
| 原始 22.cif | 无 occupancy 列、未命名空间群，直接导入成功，434 个原子；带 occupancy 列的恒等操作合成文件也通过 | 同上及扩展测试 |
| 真实窗口事件、拾取及弹窗 | 后端 ready；左键选择、右击改号、交换、撤销、真空修改均通过 | [window.json](qa_v2.12.1/native/window.json) |
| 实际自动布局 | 窗口宽 1100、1400、1600 时偏移均为 **0 像素**，最后再等待 3.2 秒仍为 0；这些测量发生在脚本的手动对齐调用之前 | 同上 |
| 小真空实际弹窗 | 设置 1 Å，关闭重开仍为 **1 Å**，确认按钮可用 | 同上及 [native_assertions.json](qa_v2.12.1/native_assertions.json) |
| 选中轮廓保留 | 32 段虚线，新增绿色像素 264；编号中心 9×9 区域最大通道变化 **0** | [选中前](qa_v2.12.1/native/before.png)、[选中后](qa_v2.12.1/native/selected.png) |
| wheel 构建 | `lele_explorer-2.12.1-py3-none-any.whl` 成功；含新增 CIF/约束模块、图标和入口 | [wheel.log](qa_v2.12.1/wheel.log)、[wheel_contents.json](qa_v2.12.1/wheel_contents.json) |
| 原源码完整性 | 基线 498 个文件全部保留，修改文件及新文件另列 SHA-256 | [source_integrity.json](qa_v2.12.1/source_integrity.json) |

独立用例原样保存在 `qa_v2.12.1/repro/test_acceptance_extra.py`，相同断言同时纳入 `tests/test_acceptance_v2121.py`。`tests/test_acceptance_extended_v2121.py` 新增 34 项：周期/反演/特殊位置混占回读、冗余及冲突组分、两种 POSCAR 坐标模式和三种编辑路径的精确固定标记、重复元素块、项目和扩胞、监视项重排后项目重开、无效映射、外观撤销、配位/对齐/偶极映射、小真空连续修改、旧项目记录、原值精度和实际布局事件。

环境：Linux、Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0。图形复测使用真实 Qt 鼠标事件和应用事件循环；Qt offscreen 没有原生 drawable，验收脚本为原生产渲染器提供独立 VTK EGL 离屏目标。没有替换拾取、弹窗、布局或结构编辑逻辑。

在源码根目录复跑：

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
PYTHONPATH=. python -m pytest docs/qa_v2.12.1/repro/test_acceptance_extra.py -q

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
QA_DETACH_OFFSCREEN_HANDLE=1 EGL_PLATFORM=surfaceless PYTHONPATH=. \
python docs/qa_v2.12.1/repro/check_window.py /tmp/lele-v2121-window

PYTHONPATH=. python docs/qa_v2.12.1/repro/check_project_examples.py /path/to/POSCAR1 /path/to/22.cif

LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py \
LELE_CHEMCRAFT_CIF_EXAMPLE=/path/to/22.cif \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

未设置私人样例路径时对应测试会跳过；本次全部设置，无跳过。私人计算文件及用户的两个原始分析/旋转脚本不随源码分发。交付为源码更新，未构建或运行 Windows EXE；Windows 显卡及高 DPI 尚未实机验收。
