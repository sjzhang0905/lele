# LELE v3.5.1：启动与大文件读取优化

日期：2026-11-09。基于用户提供的 v3.5.0 NMR / atom styles 完整源码包。

## 改动

- **启动**：欢迎页仍先绘制，随后在后台准备三维组件。ASE 完整格式注册、SciPy 空间分析和 Pillow 图片导出组件延迟到实际需要时导入。已有功能保持可用，第一次使用相关功能时才承担相应导入开销。
- **Windows 启动脚本**：首次成功验证依赖后保存验证状态；后续启动检查解释器、requirements、安装元数据和模块/原生库文件信息。环境变化或上次启动异常时重新验证，避免每次都启动一个独立进程重复导入所有依赖。设置 `LELE_VERIFY_DEPENDENCIES=1` 可强制检查。该缓存依据文件元数据，不是逐字节完整性校验。
- **CUBE**：改为约 1 MiB 文本块的 NumPy 批量数值转换，避免对每行创建 Python 浮点列表和微小数组；超长单行也分块读取。保留 Fortran D 指数、UTF-16、轨道多通道、轴顺序、负网格计数的单位约定以及 CASTEP 重复边界处理。
- **XYZ / XDATCAR**：较大原子表使用批量解析，小体系和特殊格式保留兼容路径。XDATCAR 复用当前表头的元素和计数信息，同时继续支持中途更新晶胞、Cartesian 坐标和缩放系数。
- **VASP / CP2K 输出**：减少对无关输出行反复执行正则匹配；数值表采用适用的批量路径。完整输出文本按块解码，在一次加载内供多个分析模块复用。
- **NMR**：先分块检查完整文件是否存在相关标记，未找到时跳过逐行属性解析；文件后部追加的 NMR 结果仍会被检查和读取。

## 性能测量范围

以下为相同 Linux / Python 3.12 环境、合成测试文件和热操作系统文件缓存下的实测中位数。每次使用新的 Python 进程。它们用于比较代码路径，不代表 Windows EXE、网络盘或所有真实计算输出的固定耗时。

启动取 7 次；文件读取取 3 次。CUBE 和 CP2K stdout 表为原生读取器计时，排除模块导入，CP2K 包含帧收集。轨迹表为 `load_document` 完整文档读取计时，包含该路径首次触发的延迟导入，排除预先导入基础读取模块的时间。不包含文件树附加、等值面生成或 GPU 绘制。

| 测试 | v3.5.0 | v3.5.1 | 对比 |
|---|---:|---:|---:|
| 欢迎页首次绘制 | 0.255 s | 0.246 s | 基本不变 |
| 后端就绪、隐藏三维画布已创建 | 0.986 s | 0.557 s | 用时减少 43.5% |
| CUBE：224³，160.78 MiB，常规换行 | 7.318 s | 0.948 s | 7.72 倍 |
| CUBE：128³，30.00 MiB，单个超长数据行 | 0.515 s | 0.178 s | 2.89 倍 |
| CP2K stdout：6,000 步 × 128 原子，50.75 MB | 3.081 s | 2.017 s | 1.53 倍 |

| 完整文档读取（每帧 128 原子） | 文件大小 | v3.5.0 | v3.5.1 | 加速比 |
|---|---:|---:|---:|---:|
| 普通 XYZ，10,000 帧 | 48.79 MB | 1.269 s | 1.028 s | 1.23 倍 |
| CP2K XYZ，10,000 帧 | 49.04 MB | 1.404 s | 0.884 s | 1.59 倍 |
| XDATCAR，10,000 帧 | 51.47 MB | 1.422 s | 0.752 s | 1.89 倍 |
| OUTCAR，3,000 帧 | 59.48 MB | 3.210 s | 1.755 s | 1.83 倍 |

常规换行 CUBE 的进程峰值内存约为 105.3 → 110.2 MiB，增加约 5 MiB 的有界缓冲；超长单行 CUBE 则从约 325.3 降至 75.7 MiB。CP2K stdout 内存基本不变。不能据此声称所有大文件都降低内存。

## 数据和功能验证

- 完整测试：**1,378 项通过、78 个子测试通过，12 项跳过**。跳过项需要包内未附带的私人 POSCAR、CIF、QE、WAVECAR 等外部样例。无失败。
- 对比原版与新版读取的 **37 个随包示例**：完整文档内容一致，包括数组、晶胞、能量、结果记录、元数据和 NMR。
- 新构建的 v3.5.1 wheel 与源码逐文件核对一致，并从解包 wheel 独立读取相同 37 个示例，与原版结果一致。
- CUBE 基准的全部 float32 网格数值 SHA-256 一致；CP2K 基准的每帧坐标、晶胞、元素、周期性、能量、信息及步骤关联摘要一致。轨迹基准同样比较全部帧和结果记录摘要。
- 新增检查覆盖：分块边界、不同换行与编码、D 指数、非有限值、截断/多余数据、多通道、重复晶胞、扩展 XYZ 回退、取消操作，以及编辑显示帧不改变原始计算记录。
- 延续原有坐标 float64、体场 float32 表示；不抽帧、不降采样。轨迹仍无应用级帧数上限；现有体场 64,000,000 标量值配置上限保持不变。
- 长轨迹仍把全部帧保存在内存中；大型 stdout 仍需要保留解码文本进行多属性分析。此次没有引入磁盘缓存或按需从磁盘读取轨迹的模式。

## 使用

源码运行：进入解压后的 `LELE` 目录，Windows 使用 `start_windows.bat`，已有环境也可运行 `python -m lele`。第一次安装依赖的时间不属于上表的启动时间。

已有 Windows EXE 需要用本版源码重新运行 `build_windows.bat`；替换 Python 源码不会更新已经生成的 EXE。本包提供源码及 v3.5.1 wheel，不含在 Linux 上无法生成并验证的 Windows EXE。

## 复现

解压原版和新版，准备一个可写的临时输出目录，在已安装 `requirements.txt` 依赖的 Python 环境中执行：

```bash
python tools/performance/benchmark_startup.py --baseline /path/to/old/LELE --current /path/to/new/LELE --repeats 7 --output /path/to/bench/startup.json
python tools/performance/benchmark_cube.py --baseline /path/to/old/LELE --current /path/to/new/LELE --directory /path/to/bench/cube --repeats 3
python tools/performance/benchmark_trajectory.py --baseline /path/to/old/LELE --current /path/to/new/LELE --directory /path/to/bench/trajectory --repeats 3
python tools/performance/benchmark_cp2k.py --baseline /path/to/old/LELE --current /path/to/new/LELE --directory /path/to/bench/cp2k --repeats 3
```

测试脚本会生成几百 MB 的合成输入，请使用有足够空间的目录。计时应顺序进行，避免同时构建、运行测试或执行其他耗 CPU 的任务。启动测试默认使用 Qt offscreen，只测首屏/后端准备；Windows 实际桌面和 GPU 首帧应在目标机器补测。

原始性能记录与完整测试 XML 位于 `verification/v3.5.1/`。
