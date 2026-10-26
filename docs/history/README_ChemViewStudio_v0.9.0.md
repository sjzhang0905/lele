**v0.9.0 新功能（2026-10-24），见 `RELEASE_NOTES_v0.9.0.md`。**

- 选择至少三个非共线原子，自动生成最小二乘拟合平面；在 `Edit → Best-fit selection plane` 查看方程及拟合偏差。
- `Align fitted plane to XY` 通过旋转矩阵同步旋转原子、晶胞和附带网格；可选沿 Z 平移使拟合平面位于 z=0，支持 Ctrl+Z 撤销。
- 周期结构可选择最近周期镜像，或按输入晶胞中的原始坐标拟合。
- `Ctrl+I` / `Invert selection` 反选当前帧原子。
- `Delete` / `Delete selected atoms` 删除选中原子，Ctrl+Z 恢复；在坐标输入框内按 Delete 仍用于编辑文字。
- 附带示例 `examples/selection_plane_demo.POSCAR`：先选择前四个 Cu 原子，再拟合和对齐平面。

**v0.8.1 验收修复（2026-10-23），见 `RELEASE_NOTES_v0.8.1.md`。**

- 元素颜色现在属于显示预设；手动编辑后自动进入 `Custom (manual)`，保存、重启加载与切换恢复均包含颜色。
- 内置预设恢复各自的默认配色，旧版 v0.8.0 自定义预设仍可读取；旧文件中从未保存的元素颜色需要重新编辑并保存一次。
- `Display bonds` 同时控制普通键和周期片段键，并适用于球棍、棍状和线框模式。空间填充模式仍不绘制共价键。
- 切换 `Thin wireframe` 后保留已开启的原子标签、字号和颜色；选择 `None` 仍可关闭标签。
- 本版交付为源码包。Windows 启动与重新打包方式不变，启动后核对标题 `ChemView Studio 0.8.1`。

**v0.8.0 新功能见 `RELEASE_NOTES_v0.8.0.md`。**

- 左侧 `Style` 标签加入 9 种显示预设，一键切换模型、原子与键颜色、大小、背景和光照。
- 手动调整这些显示参数后自动切换 `Custom (manual)`，可保存自定义预设。
- 切换预设不改变晶胞、原子坐标、已编辑的键、成键距离阈值、标签和氢键开关。
- Windows 自定义预设保存到 Qt 的应用配置目录中，不写入结构文件，也不需要重新打包。

**v0.7.1 新功能见 `RELEASE_NOTES_v0.7.1.md`。**

- 底部显示电子数奇偶（含净电荷）、距离小于 0.60 Å 的原子对。
- Style 标签增加氢键虚线开关，默认关闭。
- Ctrl+G 对跨周期边界的有限分子进行最小镜像成键判断，额外显示相邻晶胞，并用扩展晶胞外框完整包围片段；不会修改原始坐标。无限周期网络会给出提示。
- Edit 标签可以设定用于电子奇偶判断的净电荷。

**最新补充说明：v0.6.1 固定晶胞坐标编辑行为请先阅读 `RELEASE_NOTES_v0.6.1.md`。以下为历史版本说明。**

# ChemView Studio 0.5 — 计算化学三维可视化原型

**项目类型：Windows 桌面 GUI 源码原型（不是已经完成的 Windows EXE）。**

本项目以用户提供的 `ChemStructConverter 1.1.0` 为读取与导出后端，新增 VTK 原生三维渲染和 PySide6 GUI。整体交互方式参考 Chemcraft 的文件树 / 计算步骤 / 3D 视图组织方式，不使用 Chemcraft 的源代码、界面素材或任何私有实现。

## v0.5：左侧标签布局与坐标表同步（2026-10-20）

1. **左侧界面**：移除旧版右侧长设置栏，将所有控制选项放到左侧 `Files / Style / Axes / Labels / Field / Edit` 六个标签页。左侧总宽度默认约 355 像素，可在 295–475 像素之间由拖动分隔线调整；中央区域包含 3D 视图和底部三项数据标签，绘图区不再受右边栏挤压。
2. **坐标表同步**：移到原点、双原子对齐 X/Y/Z/a/b/c、以及手动编辑单个坐标之后，统一从当前内存 Frame 读取所有原子位置，重绘底部的 Coordinates (editable) 表格，保持已选择的原子并切换到该表格。更新时暂时屏蔽表格编辑信号，避免填表意外修改计算结构；Ctrl+Z 恢复旧 Frame 后同样会重建坐标表。
3. **数据来源**：`Coordinates (editable)` 显示编辑后结构；`Input / output text` 始终显示原始输入文件的文本预览，不会因编辑而覆盖磁盘源文件。需持久保存修改的坐标时请使用 Export structure。
4. **测试**：共 36 项，其中 32 项通过、4 项因当前环境缺少 ASE 而跳过；新增真实表格刷新代码的替身控件测试、原点平移前后坐标、X 与非正交 b 轴对齐、控件布局检查。Windows PySide6 GUI 尚待本机验收。

**推荐验收方法**：打开含三原子以上的结构，在左侧 `Edit` 选择一个原子执行 Move to origin，检查底部 Coordinates 各行都发生对应平移；再选择两个原子，分别执行 Align X / Align Y，检查底部 X/Y/Z 数值变化；切换到 `Input / output text` 应仍然能看到原始文件文本。然后测试 Ctrl+Z 是否恢复表格坐标。

## v0.4：多原子选择、Ctrl+B 成键编辑、坐标对齐（2026-10-19）

1. **原子选择**：不限制为四个。单击球体添加/取消选择；底部坐标表支持多行选择。单击右键清空选择，右键拖动仍绕视线旋转。2/3/4 原子的几何测量保留，超过四个显示选择数量。
2. **手动成键（Ctrl+B）**：恰好两个原子时，不受自动成键距离限制，直接切换该键的有/无；三个或更多原子时，如选中集合内部已有可见键就全部清除，否则依照当前成键距离阈值恢复默认的内部键。选中集合和未选中集合之间的键不会被修改。每帧单独保存手工键覆盖，可 Ctrl+Z 撤销。**手工键属于视图状态，不会在导出 XYZ/POSCAR/CIF 时写出或持久保存到磁盘。**
3. **移到原点**：恰好选择一个原子后点击 `Edit` 标签页中的“Move selected atom to (0,0,0)”。平移当前帧全部原子，使该原子成为原点；晶胞基矢不改变。如附带 CUBE 数据，同步平移体素原点。
4. **对齐方向**：恰好选择两个原子后选择 X/Y/Z 或周期性 a/b/c，再点击“Align 1st → 2nd”。以先选的原子为旋转中心，使指向后选原子的矢量沿所选正方向，原子之间距离不变。XYZ 会同时旋转晶胞和附带 CUBE 体素方向；**abc 保持晶胞不动，只旋转原子坐标，这会改变原子相对于晶胞的方向**。附带体数据时禁用 abc 模式以避免密度网格和结构不一致。
5. **版本与验证**：窗口标题和打包 VERSION.txt 更新为 0.4。自动化测试 31 项中 27 项通过、4 项因为缺少 ASE 而跳过，包含结构变换、反平行 180° 旋转、无视距离成键以及右键单击/拖动区分。**Windows GUI 尚未实际验收**；需在 Windows 64 位 Python 3.12 环境验证。

**操作推荐**：先打开 `examples/water_trajectory.xyz` 测试选择、右键与移动到原点，再打开含晶胞的 POSCAR 检查 a/b/c 方向效果。每次编辑只影响当前帧的内存副本，原始输入文件不被改写。

## v0.3：Qt 原生交互修复与编号选项精简（2026-10-19）

本轮针对 Windows 实际使用时反馈的 **Frame 方向键不更新视图、点击球体无法选中、右键拖动仍在缩放** 三个缺陷进行了事件处理层改造。

1. **Frame 树**：改为订阅 `QTreeWidget.currentItemChanged`，因此左侧树取得焦点后，鼠标选择或 ↑/↓ 方向键改变当前帧均调用 `change_frame`。播放、上一帧/下一帧、数字框也会反向同步树中当前项。若焦点在其他控件内，方向键仍遵循对应控件的默认操作。
2. **选择原子**：增加 `InteractiveVTKView`，直接在 Qt 的 `mousePressEvent/mouseReleaseEvent` 识别短按左键，生成 `atomClick` 信号。不再依赖可能被 VTK interactor style 消费的 `LeftButtonReleaseEvent` observer。引入 Qt 逻辑像素与 VTK 渲染窗口物理像素之间的比例换算，考虑 Windows 高 DPI 缩放。命中后高亮球体，并同步选择底部坐标表对应行。未命中时状态栏显示提示，可用来判断鼠标事件是否触发。
3. **右键拖动**：Qt 原生截获右键鼠标事件并执行 `camera.Roll`，禁止转发给 VTK 默认右键 dolly/zoom。向右拖动与向左拖动分别产生相反方向的绕视线旋转；左键拖动仍通过 VTK trackball 旋转，滚轮仍然缩放。
4. **标签选择框**：移除与普通 POSCAR 近似重复的 `Element + index (per element)`；保留 `VESTA (POSCAR groups)`，在重复元素组（如 `Li Li / 10 5`）时分别重置序号；对不包含 POSCAR 分组信息的其他格式，VESTA 模式自然退回按元素连续编号。

**测试**：全部 22 项回归测试中 18 项通过，4 项因本地缺少 ASE 跳过。新增测试直接调用 Qt 事件子类方法（使用替身控件，不是 Windows 图形环境），涵盖短按/拖动区分、右键 Roll 与禁用 dolly、屏幕坐标高 DPI 换算，以及事件绑定检查；VESTA 的分组读取还用上传的 POSCAR 实际头文件进行了核对。当前执行环境没有 PySide6，**Windows GUI 的实际鼠标与键盘操作尚未完成本地验收**。在 Windows 上仍需测试。

**避免误启动旧版**：解压 v0.3 到全新目录；启动后窗口标题必须出现 `ChemView Studio 0.3`。修改过源码后必须重新执行 `build_windows.bat` 并运行 `dist\ChemViewStudio\ChemViewStudio.exe`，旧目录中的 EXE 不会自动更新。打包脚本将输出 `dist\ChemViewStudio\VERSION.txt` 供核对。

## v0.2.1：POSCAR 分组编号修正（2026-10-19）

在 Appearance → Atom labels 里新增 **VESTA (POSCAR groups)**。

VASP5 POSCAR 中即使连续出现相同元素符号，也按**原始头文件定义的每个组**分别从 1 编号。用户实例：

```text
Li Li Fe Zr P O
10 5 14 1 16 64
```

对应前 10 个 Li 标记为 Li1–Li10，紧随其后的 5 个 Li **重新从 Li1 编号**，Fe1–Fe14 等各自编号。此前的按元素模式会产生 Li1–Li15；该模式已在 v0.3 的下拉框中移除，VESTA 模式仍正确保留原始 POSCAR 分组。

实现时直接从 POSCAR 头恢复分组边界，避免 ASE 读取后仅有原子化学符号而丢失原分组。对于没有 POSCAR 头信息的文件，此模式退回到按元素连续编号；不能从原子坐标推测独立位点组。注意：当前修改只修正**可视化标签**，导出时原转换器的 POSCAR 写出逻辑可能合并同种元素分组。

v0.2.1 当时仅修正标签规则，方向键、鼠标拾取和右键滚转的事件改造包含在 v0.3；但尚待 Windows 图形环境实际验收。

## v0.2 更新（2026-10-19）

已按照用户反馈新增与修复：

1. **坐标轴**：Appearance → Coordinate axes → Position 可以设为 Hidden / Bottom-left (VESTA style) / World origin (0,0,0)。后一种是真正的三维世界原点，不随摄像机移动；左下角方向器随视角旋转但始终贴在左下角。
   轴类型 XYZ (Cartesian) 或 abc (cell vectors)。abc 仅当输入中存在有效的周期性晶胞时可用；原点 abc 箭头就是完整晶胞矢量；左下角 abc 保留方向与夹角、长度归一以便观察。XYZ 原点箭头长度以 Å 为单位，默认 2.5 Å，可调整。XYZ 分别以红/绿/蓝显示。
2. **鼠标选择原子**：修正 vtk 鼠标屏幕坐标换算，按当前真实球半径在屏幕上的投影范围判定点击；若原子重合优先选朝向摄像机的较近者。点击后底部坐标表同步高亮所选原子；按住鼠标拖动仍负责旋转，而非点击。
3. **原子标签**：投影在每个球的中心；文字朝摄像机方向置于球表面前方，避免藏在球内部。可调字体（Arial、Times、Courier，或选择本地 TTF/OTF 文件）、8–72 pt 字号、颜色、粗体；编号包括纯元素、1..N、元素+全局序号、按每种元素独立编号（如 O1 O2 C1 C2）。外部字体文件不自动打包到 EXE，移机后需重新选择。

**验证**：`python -m pytest -q` → 10 passed, 4 skipped（跳过 ASE 格式读取测试，当前环境未安装 ASE）；涵盖 VTK 离屏渲染、世界坐标轴真实方向、角落方向器、标签文本生成、按投影半径拾取以及前后重叠原子的优先选择。PySide6 GUI 和 Windows EXE 尚未完成本地运行验收。

**打包启动**：仍然推荐在 Windows 64 位 Python 3.12 下先运行 `start_windows.bat`，之后执行 `build_windows.bat`。注意 PyInstaller 产物必须从 `dist\ChemViewStudio\ChemViewStudio.exe` 启动，**不得从 `build` 目录启动**，也不要把 exe 从 `dist` 目录单独搬出 `_internal`。

## 首版已经实现的功能（源码实现，不等于已在 Windows 验证）

- 通过 `ChemStructConverter` 的格式检测和结构解析逻辑，读取支持的孤立分子、晶体、计算输入与输出的几何结构。
- 原生三维视图，支持鼠标旋转 / 缩放 / 平移；球棍、空间填充、sticks、wireframe 模式。
- 自定义原子半径比例、键的粗细、成键距离阈值、原子标签、晶胞显示、背景颜色、指定元素的颜色。
- 颜色按照元素；成键为**距离阈值推断**，不是量子化学键级。
- 多帧浏览和播放（仅适用于 ASE 提供多帧读取接口的文件格式，例如多帧 XYZ、XDATCAR 等；不能保证所有计算输出都有完整轨迹）。
- 点击原子后，2 个原子测距、3 个测角、4 个测二面角。
- 下方编辑 X/Y/Z 坐标并撤销（Ctrl+Z）；不直接修改原始输入文件。
- 展示输入输出文件文本预览（前 180 KB）以及结构信息；若 ASE 解析器报告多帧能量，可查看 eV 数值和 Energy curve 轨迹图。
- 对 Gaussian CUBE 标量场显示正负等值面；可调整等值大小和透明度，支持斜交网格。
- 保存 PNG 截图（约 2 倍画布分辨率）；通过原转换器导出 XYZ / GJF / CIF / POSCAR Direct / Cartesian。
- PySide6 自动处理单/多文件拖拽到窗口。

## Windows 10/11 安装启动

1. 安装 **64 位 Python 3.12**（推荐），勾选 Add Python to PATH。也可以用 Python 3.11。
2. 解压源码包到普通英文路径，例如 `D:\ChemViewStudio`。
3. 双击 `start_windows.bat`。第一次运行时会新建 `.venv`，自动安装网络依赖；以后无需重复安装。
4. 进入软件后，点击 `Open…`，先尝试 `examples\water_trajectory.xyz`、`examples\Si_POSCAR`、`examples\artificial_signed_field.cube`。
5. 如果 bat 双击退出，先从 PowerShell 进入目录，再运行 `cmd /k start_windows.bat`，保留完整错误信息。

也可以手动：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m chemview examples\water_trajectory.xyz
```

**不要把本压缩包当成已生成 EXE。** 在有 Windows 的电脑上，初步 GUI 测试通过后运行 `build_windows.bat`，PyInstaller 将生成 `dist\ChemViewStudio\ChemViewStudio.exe`。VTK 和 Qt 较大，首版建议使用 `--onedir` 而不是单文件打包。

## 格式支持说明（沿用用户原有转换器）

**结构与计算输入输出：** XYZ（含多帧）、GJF/COM、Gaussian LOG/OUT、CIF、POSCAR/CONTCAR、OUTCAR、XDATCAR、vasprun.xml、ORCA 输入/输出、NWChem 输入/输出、CP2K 输入/输出、Quantum ESPRESSO 输入/输出、SIESTA FDF/输出/XV。

**更多结构文件：** PDB、PQR、MOL、MOL2、SDF、XSF、Gaussian CUBE、DFTB+ GEN、CFG、GRO、G96、ASE TRAJ、RES、XSD、XTD、WIEN2k STRUCT、VASP 格式等。

这里的**“支持”意味着有现成结构读取路径，而不意味着格式中所有计算属性都能可视化。** 特别是 CP2K、自定义输出解析器目前只得到最后的几何结构；计算轨迹读取覆盖率需要继续提升。

## 目前明确未实现的功能

- Gaussian/ORCA 的振动频率与动画、IR/Raman、TDDFT 光谱、轨道系数重建。
- 直接读取 VASP CHGCAR/PARCHG、LOCPOT/ELFCAR 并映射表面；DOS / PDOS / band structure 绘图。
- 磁矩、Bader、电荷、自旋密度/原子力矢量的批量提取。
- 跨晶胞周期成键 / 超胞显示 / slab 的 PBC 可视化（当前只画单晶胞的内部连线）。
- 自动显示多重键、键级、氢键或金属配位的化学正确性。
- 通过交互鼠标拖动原子直接修改几何；已有坐标表编辑器。
- SVG/EPS 矢量输出、高清透明背景、视频导出；目前只提供 PNG。
- 几何优化和分子动力学轨迹的真正懒加载，当前轨迹长度初始上限 750 帧；超过上限会尽力退回到原解析器的最后结构。
- 很大的 CUBE 体数据（目前默认体素数上限 200 万），多数据集 CUBE。

## 研发建议：下一个版本的优先任务

P1：完整结构轨迹读取与周期性晶胞连键、超胞显示（对 VASP、CP2K 和 MD 重要）。

P2：单独开发计算结果适配器：Gaussian / ORCA / CP2K / VASP 的能量、力、频率、SCF / 优化曲线。

P3：高性能三维标量场（CUBE、CHGCAR、LOCPOT）、MO/ESP 显示、截面和映射着色。

P4：结构编辑器增强、相机与场景预设、出版级绘图、图像/视频导出。

## 验证记录与限制

- 当前工作环境已运行核心几何单元测试和无界面的 VTK 3D/正负等值面渲染，测试通过。
- 当前环境**未安装 ASE/PySide6，且无法访问安装服务**，所以无法在本环境运行完整 Windows GUI，也无法完成 ASE 读取器集成测试。源码已经通过 Python `compileall` 语法检查，但 GUI 运行功能应在目标 Windows PC 上验收。
- 附件 `Chemcraft_b816bt_win64.zip` 的字节文件在此次会话的运行容器中不可读取（再次获取时返回权限错误）。因此参考的是 Chemcraft 官方展示与说明，不声称分析或修改了它的二进制程序。

## 许可证与分发注意

ChemView Studio 新增部分用于用户个人项目；`chemview/legacy_converter.py` 是用户上传的原转换器源码副本。Chemcraft 不作为项目依赖，未打包、链接或复制 Chemcraft 二进制文件。正式公开发布前应确认所有第三方依赖、ASE、VTK、Qt 和原转换器源文件各自的授权要求。

## v0.1.1 Windows 安装修复（2026-10-19）

上一版 `start_windows.bat` 在找不到 Python 3.12 时退回 `py -3`，可能意外调用 Python 3.13+ 或 32 位解释器，导致 pip 找不到对应的 `vtk` Windows wheel。

修复版：

1. 优先选择 64 位 Python **3.12**，其次选择 64 位 **3.11**。不再退回使用未经检查的 `py -3`。
2. 检查已有 `.venv` 的 Python 版本和位数。如果它不兼容，将其**重命名备份**为 `.venv_incompatible_...` 并重建；不会直接删除旧环境。
3. 如果找不到正确 Python，将明确提示安装，而不是持续尝试 pip。
4. 新增 `diagnose_windows.bat`，显示 Python 安装位置、位数、虚拟环境及 pip 镜像设置。
5. 如果 Python 版本正确，但 `vtk` 仍显示 `from versions: none`，检查是否使用了不完整的镜像源。可尝试从官方 PyPI 安装：

```powershell
.venv\Scripts\python.exe -m pip install --only-binary=:all: --index-url https://pypi.org/simple "vtk>=9.3,<10"
```

此修复只针对启动与依赖安装问题，没有声称已在 Windows GUI 中完成实机验收。如果仍失败，请通过 `diagnose_windows.bat` 提供输出，以判断是否为 ARM64 Windows、网络/镜像配置或其他兼容性问题。


## v0.6 等轴测视图与片段编辑

- 打开结构时默认等轴测平行投影，也可点击工具栏 Isometric 按钮。
- 选中一个或多个原子，使用 Ctrl+G（或 Edit 标签中的按钮）扩展选中整个成键连通片段。
- Alt + 左键拖动：只旋转当前片段；Alt + 右键拖动：只让当前片段在屏幕平面内旋转；Alt + 按住鼠标中键拖动：仅平移当前片段。
- 普通鼠标操作仍控制相机。右键单击依然清空选择。
- 片段操作每次拖动仅建立一条撤销记录，松开鼠标后更新 Coordinates 表；Ctrl+Z 撤销。
- 片段以当前**可见成键图**的连通分量为准，包含 Ctrl+B 人为增加或删除的键。暂不包含跨周期边界的镜像键。如果吸附物与基底成键，需要先用 Ctrl+B 去掉连接键，才能单独移动吸附物。
- 片段变换保持非选中原子、晶胞、CUBE 标量场不动。对周期体系请注意，这将改变片段与晶胞的相对位置。
- Windows GUI 行为仍需实际运行验收。

## v0.7.0 新功能

- **Isometry / Perspective**：工具栏可以切换正交等轴测和透视模式；Isometry 使摄像机沿 Cartesian `[1,1,1]` 方向观察，不会修改晶胞和原子坐标。按 `Isometry` 可以恢复等轴测方向。
- **SIESTA 优化轨迹**：打开 `.out` 优先读取所有明确打印的结构；如果只有部分结构，寻找同名 `.ANI`（或同目录唯一且原子组成一致的 `.ANI`）恢复更多帧。与帧数严格对应的 `Etot` 或 `.MDE` 可以显示在帧树、结果信息和 Energy curve 中。`.ANI` 通常不包含晶胞；若从 `.out` 复用晶胞，应核对变胞计算。
- **底部组成/自旋摘要**：随当前帧显示元素总计数，例如 `C1H20Cl9`。周期体系标为 cell composition；未成对电子只在可靠的自旋/多重度信息存在时明确判断，否则显示 Unknown。单重态不能排除开壳层单重态。

### SIESTA 输出说明

新版本支持 `.out` 和 `.ANI` 的几何轨迹读取，`.MDE` 读取仅针对包含 `# Step T ... E_KS ... E_tot ...` 列标题的常见格式，不对未知列次序进行猜测。程序只有在结构数量与能量记录数一致时才逐帧配对，不会将 SCF 电子迭代误认为原子优化步骤。`.ANI` 仅含坐标；若 `.out` 缺乏对应变胞轨迹，不能自动恢复每一步真实晶胞。

若旧计算仅输出最后结构且没有 `.ANI` 等历史文件，无法恢复不存在的轨迹。新计算建议在 `.fdf` 设置 `WriteCoorStep true`、`WriteCoorXmol true`，如需 `.MDE` 还可以启用 `WriteMDHistory true`。保存的不同历史文件应来自同一次计算，避免自动配对混杂。

Python 3.12 x64；运行 `start_windows.bat`，打包后从 `dist/ChemViewStudio/ChemViewStudio.exe` 启动。此版本未在 Windows 图形桌面上实际验收。
