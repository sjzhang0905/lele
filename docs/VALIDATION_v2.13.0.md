# LELE v2.13.0 验证记录

2026-11-02。以 `LELE_v2.12.1_fixed_20261102.zip` 为基线，SHA-256 为 `954b48536bfa93075a1c428960b7517a860eb5d7050fa1ccf98d410acf0bcb7d`。改动见 [六项需求说明](FEATURES_v2.13.0_CN.md)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 本次新增回归 | **18 通过**，0 失败、0 跳过 | [display.log](qa_v2.13.0/display.log)、[display.xml](qa_v2.13.0/display.xml) |
| 完整回归 | **870 项测试 + 78 个子测试通过**，0 失败、0 错误、0 跳过，65.97 秒 | [full.log](qa_v2.13.0/full.log)、[full.xml](qa_v2.13.0/full.xml) |
| 完整原始 RGB 对照 | Sibyl.tcl 全部 111 个 Element→ColorID→RGB 映射逐项一致；渲染值为源 RGB 四舍五入到 8 位 | 新增测试及 [原始配色文件](reference_data/Sibyl.tcl) |
| 默认 Glossy 的实际 VTK 属性 | 原子和键的高光强度 0.78、指数 60；控件与 RenderOptions 均为 Glossy | 新增测试及实际窗口记录 |
| 欢迎页 | 真实应用后端 ready；无打开按钮及拖放提示；File→Open、Ctrl+O、拖放、动画及欢迎页尺寸测试均通过 | [display.json](qa_v2.13.0/native/display.json)、[welcome.png](qa_v2.13.0/native/welcome.png) |
| 周期轴 / 分子轴 | 真实生产渲染器：周期 `a,b,c` → 分子 `X,Y,Z` → 返回周期 `a,b,c`；另验证斜晶胞、旋转晶胞、手选 XYZ、项目保存与文件切换 | 同上及新增测试 |
| 五种结构导出 | 既有顺序 O,H,C；连续两批添加 Fe,N 和 Co,H，全部格式导出重读均为 O,H,C,Fe,N,Co,H；POSCAR 逐原子固定标记也保留 | 新增测试 |
| 旧转换接口 / UI 导出 | 两种旧 POSCAR 输出均保持行序；主窗口 Export structure 路径通过；实际窗口追加 Co,H 后重读顺序正确 | 同上及实际窗口记录 |
| 旧项目 / 手动显示 | 明确存储的 GaussView style、Balanced、XYZ 和自定义颜色继续保留；自动模式及 Sibyl / Glossy 新设置可以保存重开 | 新增及原有项目测试 |
| wheel / 源码完整性 | 构建成功，含 `lele/sibyl_palette.py`、图标及入口；基线 521 个文件全部保留 | [wheel.log](qa_v2.13.0/wheel.log)、[wheel_contents.json](qa_v2.13.0/wheel_contents.json)、[source_integrity.json](qa_v2.13.0/source_integrity.json) |

新增用例保存在 `tests/test_display_and_order_v2130.py`。原欢迎页测试改为从文件菜单及欢迎页焦点验证 Ctrl+O；颜色编辑器测试更新为新 Sibyl 氧色；旧兼容配色仍显式验证为原数值。完整回归包含此前 A1–A3、B1–B4 的原始 12 项断言及扩展回归，并启用了私人 QE、CP2K、POSCAR1/POSCAR2、旋转脚本和 22.cif 样例。

环境：Linux，Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0。实际窗口检查使用生产 Qt 控件及渲染器；由于 Qt offscreen 不提供原生 drawable，仅将 VTK 绘制目标设为独立 EGL 离屏窗口。

在源码根目录复跑：

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests/test_display_and_order_v2130.py -q

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
EGL_PLATFORM=surfaceless PYTHONPATH=. \
python docs/qa_v2.13.0/repro/check_display_v2130.py /tmp/lele-v2130-display

LELE_QE_EXAMPLE_DIR=/path/to/four/QE/files \
LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol \
LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2 \
LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py \
LELE_CHEMCRAFT_CIF_EXAMPLE=/path/to/22.cif \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=full_retest.xml
```

未设置私人样例路径时，对应测试会跳过；本次全部启用、没有跳过。私人科学输入及用户的分析/旋转脚本不随包分发。交付为源码包，未生成或实机测试 Windows EXE。
