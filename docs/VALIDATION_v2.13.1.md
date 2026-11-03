# LELE v2.13.1 复验记录

2026-11-03。基线为 `LELE_v2.13.0_Sibyl_20261102.zip`，SHA-256：`117786380b81188e59bd34a79923948d6876d7ee59442101b881fbe56f5b2e2d`。修复对照见 [五项说明](FIX_DELTA_v2.13.1_CN.md)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 报告的原始独立断言，修改前 | 11 项，5 失败、6 通过，无跳过 | [before.log](qa_v2.13.1/independent_before.log)、[before.xml](qa_v2.13.1/independent_before.xml) |
| 相同独立断言，修改后 | **11 项全部通过**，无跳过 | [after.log](qa_v2.13.1/independent_after.log)、[after.xml](qa_v2.13.1/independent_after.xml) |
| 原始断言和新增边界用例 | **42 通过**，含 31 项新增断言，无跳过 | [extended.log](qa_v2.13.1/extended.log)、[extended.xml](qa_v2.13.1/extended.xml) |
| 完整回归 | **912 项测试 + 78 个子测试通过；0 失败、0 错误、0 跳过；69.21 秒** | [full.xml](qa_v2.13.1/full.xml)、[full.log](qa_v2.13.1/full.log)、[summary.json](qa_v2.13.1/summary.json) |
| 报告原始观察脚本 | 正交/斜晶胞/平移代表均正常；高精度占据回读不变；CIF 行为 Co,Ni,O,H；头部 C C O / 1 1 2；新旧距离均 2,2 | [edges.json](qa_v2.13.1/edges.json) 及 [具体输入和输出](qa_v2.13.1/samples/) |
| 实际 Qt/VTK 默认界面 | 后端 ready；Glossy、Sibyl、简化欢迎页、abc→XYZ→abc 切换及追加顺序通过 | [display.json](qa_v2.13.1/native/display.json) |
| 实际右击/交换/撤销及旧修复 | 原子索引弹窗、真空修改和撤销通过；底栏 1100/1400/1600 宽度偏差均 0；重开 1 Å 真空仍为 1 Å | [window.json](qa_v2.13.1/native/window.json) |
| 原生选中轮廓 | 32 段线，新增绿色像素 264；编号中心 9×9 最大通道差 0 | 同上 |
| wheel / 源码完整性 | wheel 构建成功，含 `lele/cif_output.py` 和入口；基线 538 个文件全部保留 | [wheel.log](qa_v2.13.1/wheel.log)、[wheel_contents.json](qa_v2.13.1/wheel_contents.json)、[source_integrity.json](qa_v2.13.1/source_integrity.json) |

独立用例原样移植为 `tests/test_delta_acceptance_v2131.py`，与报告的 `repro/test_delta_213.py` 逐字节一致。`tests/test_delta_extended_v2131.py` 新增 31 项，覆盖三个斜晶胞晶面及整数代表、占据率多次精确往返与空位、过占据拒绝、连续/非连续组分顺序、多批追加、项目、原生剪贴板、Boundary、扩胞、删除/补回/追加 C 后的曲线和颜色、真正缺失身份、重复删除不复用、新副本身份、存活对齐骨架、POSCAR 两种坐标格式与重复块，以及真实 Qt 几何监视窗口的删除、粘贴和撤销。

完整回归启用原始私人 POSCAR1/POSCAR2、QE 四文件、CP2K Molden、旋转脚本和 22.cif；原始 Sibyl.tcl 的包内副本此前已经逐字节核验，本次文件未改动。原先三个文件中的 64 项相关用例（含 v2.12.0 的 12 个移植断言、34 个修复扩展和 18 个新增功能用例）继续包含在完整回归内；重叠用例不重复累加。

环境：Linux、Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0。窗口检查使用真实 Qt 控件和生产渲染器，并为 Qt offscreen 提供独立 VTK EGL 离屏目标。

在源码根目录复跑：

```bash
QA_SIBYL_TCL=docs/reference_data/Sibyl.tcl \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests/test_delta_acceptance_v2131.py tests/test_delta_extended_v2131.py -q

PYTHONPATH=. python docs/qa_v2.13.1/repro/edge_observations.py /tmp/lele-v2131-cases

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
QA_DETACH_OFFSCREEN_HANDLE=1 EGL_PLATFORM=surfaceless PYTHONPATH=. \
python docs/qa_v2.13.1/repro/check_window.py /tmp/lele-v2131-window

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
EGL_PLATFORM=surfaceless PYTHONPATH=. \
python docs/qa_v2.13.1/repro/check_display_v2130.py /tmp/lele-v2131-display

LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py \
LELE_CHEMCRAFT_CIF_EXAMPLE=/path/to/22.cif QA_SIBYL_TCL=docs/reference_data/Sibyl.tcl \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

未提供私人样例路径时，对应用例会跳过；本次全部提供，无跳过。私人科学输入和两个用户原始分析/旋转脚本不随包分发。交付为源码更新，未生成或实机测试 Windows EXE。
