# LELE v2.13.2 修复与复验记录

2026-11-03。针对 v2.13.1 全量验收报告中的两项问题：PQR 元素误读/拒绝导入，以及负网格计数 CUBE 无法载入。

**这两项问题已修复，当前复验全部通过。**

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 原验收的同一组独立断言，修改前 | 114 项：110 通过、4 失败、0 跳过；四个失败断言归为两项问题 | `qa_v2.13.2/before_independent.*`、`before_format_coverage.*`、`before_long_integrity.*` |
| 原验收的同一组独立断言，修改后 | **114 项全部通过，0 失败、0 错误、0 跳过；15.312 s** | `qa_v2.13.2/independent_all.xml`、`independent_all.log` |
| 完整回归，含新增 69 项 | **981 项测试及 78 个子测试通过；0 失败、0 错误、0 跳过；101.835 s** | `qa_v2.13.2/full.xml`、`full.log` |
| 原始最小复现输入 | 三种空白布局 PQR 均为 O、(1,2,3) Å；负计数 CUBE 正确返回 O、2×2×2 网格、原点及 0.5 Å 体素；正常对照通过 | `qa_v2.13.2/samples/findings.json`、`minimal_after.log` |
| 实际 Qt/VTK 窗口 | 五个 PQR/CUBE 复现及对照文件均实际打开；元素、坐标表、体数据及渲染通过 | `qa_v2.13.2/native/repaired_formats.json` 及同目录 PNG |
| wheel 构建与独立运行 | 构建成功；包含两个新读取模块；从源目录之外的 wheel 解包目录运行同样五个窗口检查通过 | `qa_v2.13.2/wheel.log`、`wheel_native/repaired_formats.json` |
| 原文件保留及代码语法 | 基线成员全部保留；生产 Python 模块语法检查通过 | `qa_v2.13.2/source_integrity.json`、`summary.json` |

完整回归为原来的 912 项加本次新增 69 项。新增 69 项已计入 981，不再重复累加；独立 114 项单独统计。JUnit 的完整回归声明数 1059 包含 78 个子测试。

## 改动范围

- `lele/pqr_input.py`：统一 PQR 记录解析，支持空白字段、可选 Chain ID、固定列宽、常见生物分子原子标签、明确错误行及中途取消。
- `lele/cube_input.py`：共享 CUBE 几何/网格读取；规范计数符号及长度单位，保留原文件、标量场和 ASE 现有的数据顺序处理。
- `lele/legacy_converter.py`、`lele/formats.py`：接入两个读取器，保持有效原子结构与体数据可用性分开，传播取消。
- `tests/test_pqr_cube_v2132.py`：69 项新回归，覆盖空格/制表符、两种记录类型、有无链号、固定列宽、原子标签/离子、超宽坐标、编码、非法行；Bohr/Å、正负原子数、斜网格、场数值、CASTEP 边界、缺失/多通道/超大场、五种输出、旧转换入口、项目重开及中途取消。
- 版本号、README、CHANGELOG 和修复说明更新为 2.13.2。

具体行为见 [修复说明](FIX_PQR_CUBE_v2.13.2_CN.md)。多通道 CUBE 仍不自动选择通道；已有体数据点数上限和 float32 存储保持。PQR 非标准原子标签仍可能存在命名歧义。

## 测试环境与范围

Linux、Python 3.12.14、ASE 3.29.0、NumPy 2.3.5、SciPy 1.17.0、PySide6 6.12.0、VTK 9.7.1、pytest 9.2.0、Pillow 12.3.0、Matplotlib 3.10.8。实际窗口检查使用 Qt offscreen 和原生 VTK EGL 渲染目标，分子绘制和文件导入逻辑均为生产实现。

完整回归提供了原 POSCAR1/POSCAR2、QE 四文件、CP2K Molden、旋转脚本、22.cif 及 Sibyl.tcl，故没有跳过私人样例测试。私人科学输入不随源码重新分发。

长轨迹独立断言复验 1200/4800 步的十类输入场景，以及 ORCA 1500/6000 帧；检查完整数量和末次科学数据。这些合成输入沿用原全量验收的数据，未重新声称任意文件大小/原子数下的性能。

交付为源码更新；**未生成或实机测试 Windows EXE**。无显示服务器的 Linux 环境需要支持 EGL 的 VTK；本次使用 9.7.1。

## 复跑

在源码根目录，先配置私人样例路径（不配置时，对应原有用例会跳过）：

```bash
export QA_SIBYL_TCL=/path/to/Sibyl.tcl
export LELE_ROTATION_EXAMPLE_DIR=/path/to/POSCAR1_and_POSCAR2
export LELE_QE_EXAMPLE_DIR=/path/to/four_QE_files
export LELE_CP2K_MOLDEN_EXAMPLE=/path/to/COF2_O2_a_freq-VIBRATIONS-1.mol
export LELE_ROTATION_SCRIPT=/path/to/rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py
export LELE_CHEMCRAFT_CIF_EXAMPLE=/path/to/22.cif
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
EGL_PLATFORM=surfaceless python -m pytest tests -q -ra --junitxml=full_retest.xml
```

复跑原验收的 114 项独立用例；其中长轨迹数据可通过包内工具重建：

```bash
python tools/benchmark_multistep.py --generate --counts 1200 4800 --repeat 1 \
  --data /tmp/lele-2132-bench --output /tmp/multistep.json
python tools/benchmark_orca_loading.py --generate --counts 1500 6000 --repeat 1 \
  --data /tmp/lele-2132-bench --output /tmp/orca.json
LELE_AUDIT_SOURCE="$PWD" LELE_AUDIT_BENCH_DATA=/tmp/lele-2132-bench \
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
EGL_PLATFORM=surfaceless PYTHONPATH=. python -m pytest \
  docs/qa_v2.13.2/repro/test_independent_full.py \
  docs/qa_v2.13.2/repro/test_format_coverage.py \
  docs/qa_v2.13.2/repro/test_long_integrity.py -q -ra
```

原最小输入与实际窗口检查：

```bash
PYTHONPATH=. python docs/qa_v2.13.2/repro/reproduce_findings.py /tmp/lele-2132-samples
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
EGL_PLATFORM=surfaceless PYTHONPATH=. python \
  docs/qa_v2.13.2/repro/check_repaired_formats.py \
  /tmp/lele-2132-samples /tmp/lele-2132-window
```

基线源包 SHA-256：`5ceaacfd12b4cdd25d7391a9b8ffe7843ed3007a838ade78264c0923679adb8f`。同组原验收脚本逐字节保留；修改差异见 `qa_v2.13.2/changes.patch`。
