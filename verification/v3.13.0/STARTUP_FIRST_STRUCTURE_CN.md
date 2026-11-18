# v3.13.0 欢迎页与首次打开文件验证

## 修改

- 等待当前可见的欢迎页标题、副标题、版本、鹦鹉及快捷键区域完成首轮绘制，再在下一轮事件循环自动启动后台加载。
- 后台预导入 ASE 读取注册表、LELE 支持的 PDB/MOL/SDF/XSF/GEN/CFG/GRO/G96/TRAJ/RES/XSD/XTD/XV/STRUCT 等明确读取模块、SciPy spatial/周期邻居搜索、原生 ORCA/Gaussian/CP2K/VASP/QE/SIESTA/xTB 解析、体数据与等值面依赖。
- 后台线程只做模块导入。Qt/VTK 对象创建、Initialize，以及原子、键、标签、世界坐标轴、角落坐标轴、等值面的小场景预热，均在 GUI 线程执行。
- 预热完成后清除临时场景和 framebuffer，保留欢迎页与用户的显示设置；不创建虚拟文件，也不等用户打开第一个结构才初始化。

## 对比条件

基线为上一版 `LELE_v3.12.0_20261112.zip` 原始源码，当前为修改后源码。每项每版本 3 次，基线/当前交替运行，每次启动全新 Python 进程。Linux、Python 3.12、Qt offscreen 界面及实际 VTK/EGL 渲染管线；所有运行均确认 OpenGL 可用。

**这不是重启电脑后的测试，也没有清理操作系统文件缓存；不包含 Windows 启动脚本及原生 QVTK 窗口嵌入成本。** Qt offscreen 不提供有效的 X11/Windows native drawable，因此使用 QWidget 外壳内的独立 EGL 渲染窗口，避免把无效图形上下文的错误输出当成渲染耗时。

## 中位数（秒）

| 测试文件 | 欢迎页绘制：旧 → 新 | 后台 Ready：旧 → 新 | 第一次打开：旧 → 新 | 第一次打开加速 | 新版第二次打开 |
|---|---:|---:|---:|---:|---:|
| XYZ | 0.441 → 0.483 | 0.968 → 1.832 | 1.009 → 0.218 | 4.6× | 0.052 |
| POSCAR | 0.458 → 0.511 | 0.899 → 1.849 | 0.918 → 0.121 | 7.6× | 0.063 |
| ORCA | 0.508 → 0.477 | 0.954 → 2.124 | 0.680 → 0.212 | 3.2× | 0.061 |
| PDB | 0.453 → 0.697 | 0.910 → 2.541 | 1.168 → 0.309 | 3.8× | 0.088 |

后台 Ready 稍晚是主动提前准备更多内容的结果，不能将其描述为总启动时间缩短。欢迎页仍先出现，随后自动准备；首次文件打开减少了此前隐藏的初始化等待。

所有 12 次新版首次打开均没有新增 NumPy/SciPy/ASE/VTK/PIL 模块导入（旧版 237–484 个子模块）；实际读取文件、计算该文件的成键和创建其图形仍需要时间。

## 回归

- `startup_regression_full.log`：37 项启动、欢迎页、进度动画及 Windows 启动缓存测试通过。
- `startup_firstfile_import_guard.log`：后台完成后首次打开 PDB 及随后打开 XYZ 均不再导入新的科学/图形依赖；初始化仅执行一次。另逐项验证 GENERIC_SUFFIX_READERS 中所有 ASE 读取模块均已预导入。
- `startup_first_structure.json`：每次运行的原始耗时、模块新增清单、初始化状态及 OpenGL 检查。
- 可复现命令：`python tools/performance/benchmark_first_structure.py --baseline <旧版源码目录> --current . --repeats 3 --output result.json`。
