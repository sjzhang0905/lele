# LELE

**Local Environment and Lattice Explorer — 局域环境与晶格探索工具**

**v3.5.2**：修复 CHGCAR 重命名后被误识别为 POSCAR 的问题，并加快 VASP 体数据读取。见[修复与性能报告](docs/CHGCAR_v3.5.2_CN.md)。

v3.5.1：加快启动、大 cube 和长步数 AIMD 文件读取；保留 v3.5.0 的全部功能。性能对比、适用范围与复现方式见[性能与验证报告](docs/PERFORMANCE_v3.5.1_CN.md)。

v3.5.0：选中原子可独立选择 Space filling、Sticks 等显示方式；Atoms 按文件中元素首次出现的顺序排列并默认折叠，双击 Coordinates 的原子名称可展开定位。新增 NMR 屏蔽常数表、参考化学位移谱和 CSV/PNG/SVG 导出。底部左侧为 Axes/Labels/Field/Boundary，右侧为 Coordinates/Input-output/Results；Crystal、Dipole 从 View 菜单打开。保留 v3.4.0 的 ESP 映射与等值面叠加。见[使用说明](docs/FEATURES_v3.5.0_CN.md)与[验证记录](docs/VALIDATION_v3.5.0.md)。

**v3.4.0**：修复 v3.3.0 验收发现的三项问题；新增跨数据场等值面叠加、在电子密度等值面上映射已导入的 ESP/电势，以及色标、工程保存和 PNG/GIF 导出。见[使用说明](docs/FEATURES_v3.4.0_CN.md)与[复验记录](docs/VALIDATION_v3.4.0.md)。

**v3.0.1**：统一 OUTCAR 的 Step 命名，点击前后保持一致；多帧文件打开及点击文件总节点时默认显示最后一个可用结构；默认勾选 **Enable boundary display**，初始范围仍为一个原始晶胞。见[修复与验证记录](docs/VALIDATION_v3.0.1.md)。

**v3.0.0**：保存 PNG 默认采用 **4 倍分辨率 + Smooth edges（平滑边缘）**。见[发布验证记录](docs/VALIDATION_v3.0.0.md)。

v2.13.6 修复验收报告中的两项坐标轴问题：原画布的 **Z/c 等角落字母被裁切**，以及 **3×/4× 平滑 PNG 中坐标轴截短**。见[修复与验证记录](docs/VALIDATION_v2.13.6.md)。

v2.13.5 将默认 Ball and stick 的 **Bond thickness 改为 7**，Default 配色的 **H 显示半径增加 15%**，当前默认元素色再混入 **5% 白色**。保存 PNG 增加分辨率和边缘平滑选项，默认 **3 倍输出 + 平滑边缘**。见[使用与验证记录](docs/VALIDATION_v2.13.5.md)。

v2.13.4 将 Atom colours 中的 **Sibyl** 更名为 **Default**；整套默认元素色混入 10% 白色，默认 Atom size 从 60% 降至 50%，Bond thickness 从 11 降至 9。见[验证记录](docs/VALIDATION_v2.13.4.md)。

v2.13.3 修复选中原子后测量输入框撑高底栏、挤压画布的问题；选中或清空选择时底栏与画布高度保持一致。默认背景统一为纯白 **#FFFFFF**。见[验证记录](docs/VALIDATION_v2.13.3.md)。

v2.13.2 修复全量验收中的 **PQR 元素误读/拒绝导入**和 **负网格计数 CUBE 无法打开**。
PQR 的元素和坐标采用一致的空白字段或固定列宽记录；CUBE 的原子、原点、体素和晶胞共享单位处理。
见[修复说明](docs/FIX_PQR_CUBE_v2.13.2_CN.md)和[复验记录](docs/VALIDATION_v2.13.2.md)。

v2.13.1 修复增量验收中的 **全部五项问题**：斜晶胞 CIF 晶面坐标、高精度占据率往返、追加原子后的既有身份、重复 POSCAR 元素块，以及混占 CIF 的原始组分行顺序。见[修复说明](docs/FIX_DELTA_v2.13.1_CN.md)和[复验记录](docs/VALIDATION_v2.13.1.md)。

v2.13.0 默认采用 **Sibyl.tcl 配色和 Glossy 光泽**；移除欢迎页的打开按钮及拖放提示；周期结构自动显示 **abc 晶矢**，非周期分子显示 XYZ。各结构导出格式均保留当前原子顺序，新增原子按添加顺序追加到末尾，旧转换接口也不再按元素排序。见[使用说明](docs/FEATURES_v2.13.0_CN.md)和[验证记录](docs/VALIDATION_v2.13.0.md)。

v2.12.1 修复独立验收中的 **A1–A3、B1–B4 全部七项问题**：等价晶位混占组分、POSCAR 固定标记及原子顺序、跨帧原子身份、真空未变及小真空回读、底部自动对齐和 Chemcraft 恒等操作 CIF 导入。见[修复说明](docs/FIX_A1_B4_v2.12.1_CN.md)和[复验记录](docs/VALIDATION_v2.12.1.md)。

v2.12.0 增加 **CIF 分数占据扇区显示、右击原子重编号/交换编号、保持笛卡尔坐标的 slab 真空层修改**；底部摘要左侧与 Coordinates 窗口对齐，选中原子改为绿色粗虚线外轮廓。见[使用说明](docs/FEATURES_v2.12.0_CN.md)和[验证记录](docs/VALIDATION_v2.12.0.md)。

v2.11.0 修复周期结构重设方向：**XYZ 对齐同步旋转原子与晶胞**。新增 **Edit → Reorient complete structure / crystal…**，可一次设置原点、X 提示和 Z 方向，自动生成正交旋转矩阵，也可粘贴分析脚本的行向量矩阵。支持最近周期像、体数据同步变换、撤销和项目保存。见[使用说明](docs/FEATURES_v2.11.0_CN.md)和[验证记录](docs/VALIDATION_v2.11.0.md)。

v2.10.1 修复独立验收发现的 **A1–A3**：QE 优化状态必须有明确收敛证据；CP2K 晶胞扩展与原子重复分别读取；支持 `ANGLES` 别名及显式角度单位，保留斜晶胞。见[修复说明](docs/FIX_A1_A3_v2.10.1_CN.md)和[复验记录](docs/VALIDATION_v2.10.1.md)。

v2.10.0 完善 **QE 输入、PWSCF 变胞优化、PHONON 频率及 matdyn 模式导入**。模式文件可明确关联参考结构和 alat，支持非 Γ 点的周期振动相位、箭头、GIF、q 点 CSV 和项目保存。见[QE 使用说明](docs/FEATURES_v2.10.0_CN.md)和[验证报告](docs/VALIDATION_v2.10.0.md)。

v2.9.0 默认使用 **GaussView 风格配色（取自 Chemcraft 兼容预设）**、**Chemcraft 普通键距离上限**及 **VESTA space-filling 半径**。Space-filling 默认 Atomic、100%，可切换 Ionic / van der Waals，尺寸独立保存。配色尚未取得 Gaussian 原始完整 RGB 表；成键采用默认表提取的距离，不承诺复现其他软件的完整算法。见[参数来源和范围](docs/display_reference_data.md)。
详见 [v2.9 使用说明](docs/FEATURES_v2.9.0_CN.md)和[验证报告](docs/VALIDATION_v2.9.0.md)。

v2.8.0 增加 **CP2K/Molden `.mol` 振动导入**，支持模式选择、动画、箭头及 GIF，保留固定原子的零位移。
**View → Atom legend…** 改为独立图例窗口，画布仅显示各元素样本和符号，可单独保存 PNG。
详见 [使用说明](docs/FEATURES_v2.8.0_CN.md)和[验证报告](docs/VALIDATION_v2.8.0.md)。

v2.7.0 检查并改进各类多步输出读取，修复 CP2K、xTB、Quantum ESPRESSO、NWChem 的重复扫描；
处理/导出/项目操作增加延迟进度框。优化成功的对应帧显示 **converged**，
**View → Atom legend** 可添加随 PNG/GIF 导出的元素球图例，欢迎页并列显示两个邮箱。
详见 [使用说明（含 CP2K 频率输出组织）](docs/FEATURES_v2.7.0_CN.md)和[验证记录](docs/VALIDATION_v2.7.0.md)。

v2.6.0 更新：Bond cutoff 扩大到 0.10–5.00，支持精确输入并立即重新识别自动键；
底部信息行下移，扩大画布。选中 2/3/4 个原子后，可直接输入键长/键角/二面角，
按 Enter 或 Set 移动最后选中原子所在的末端片段，支持撤销；环或周期网络限制移动时弹窗提示。
ORCA 优化输出加速解析，输出文件后台加载，长加载弹窗显示阶段、阶段百分比、耗时并支持取消。
详见 [使用说明](docs/FEATURES_v2.6.0_CN.md)和[验证记录](docs/VALIDATION_v2.6.0.md)。

v2.5.0 取消程序固定帧数上限，并优化长轨迹加载：CP2K/普通 XYZ、XDATCAR 逐帧读取，
同一次导入的分析共用已解码输出；目录树按需展开，大文件后台解析并支持取消。
保留全部结构帧和能量记录。详见 [长文件使用说明](docs/FEATURES_v2.5.0_CN.md)和
[性能对比与验证](docs/VALIDATION_v2.5.0.md)。

v2.4.0 增加 **CP2K 独立读取**：输入/文本 restart、标准输出和 XYZ 轨迹均可单独打开。
支持已有结构、能量、优化收敛指标、按 k 点/自旋分组的轨道，以及 TDDFPT 跃迁、光谱和 CSV。
不搜索配套文件；没有结构或能量时保留实际可用的数据。详见
[CP2K 使用说明](docs/FEATURES_v2.4.0_CP2K_CN.md)和[验证记录](docs/VALIDATION_v2.4.0.md)。

v2.3.1 调整：VASP 结果、曲线和 CSV **只使用 E0**，即 OSZICAR 的 `E0=`、OUTCAR 的
`energy(sigma->0)`。没有 E0 时留空。详见 [说明与验证](docs/VASP_E0_v2.3.1_CN.md)。

v2.3.0 更新：加入三个最高优先级功能：**按元素对设置成键/配位规则**、
**多面体定量分析与轨迹曲线/CSV**、**.lele 项目保存与恢复**。
入口分别为 Crystal → Pair rules、Analysis → Coordination / polyhedron analysis…、
File → Save/Open project…。项目保留已加载的结构与计算结果、编辑后的键、逐原子样式、
各文件视角、HKL 切面和显示参数。详见 [v2.3.0 说明](docs/FEATURES_v2.3.0_CN.md)与
[验证记录](docs/VALIDATION_v2.3.0.md)。

v2.2.0 更新：增加 **(hkl) 晶面显示裁切**和 **Polyhedral 配位多面体样式**。
通过 **Crystal → HKL planes** 设置晶面、位置、保留方向和薄层厚度；支持多个切面、
斜晶胞和沿晶面法向观察。通过 **Crystal → Polyhedra** 设置中心/配位元素、距离、
透明度和棱线，补全跨晶胞配位，并保留各文件自己的显示设置。
详见 [v2.2.0 说明](docs/FEATURES_v2.2.0_CN.md)和[验证记录](docs/VALIDATION_v2.2.0.md)。

v2.1.0 更新：增加 **VASP OUTCAR / XDATCAR / OSZICAR** 独立读取，支持优化/MD
轨迹、离子步能量、力曲线、振动模式与虚频动画（自 v2.3.1 起只使用 E0）。只有能量时显示结果页，只有结构时
保留轨迹浏览，无需同目录其他文件。详见 [v2.1.0 说明](docs/FEATURES_v2.1.0_CN.md)
和[验证记录](docs/VALIDATION_v2.1.0.md)。

v2.0.3 更新：增加 **Ctrl+H**，在两个选中原子之间添加/移除虚线氢键，支持撤销；
Ctrl+B 继续操作普通键。切换已打开的文件时，各文件保留自己的视角、缩放、平移、
投影、配色及其他显示设置；频率和纯能量节点也使用同一恢复流程。
详见 [v2.0.3 说明](docs/FEATURES_v2.0.3_CN.md)和[验证记录](docs/VALIDATION_v2.0.3.md)。

v2.0.2 更新：修复强倾斜、非约化晶胞的短接触和最近周期像搜索；轨迹显示对齐时，
晶胞边框与 Boundary 原子、边框一起旋转和平移；删除 Windows 启动错误中的旧版本号。
Alt＋鼠标中键拖动片段、坐标编辑等操作保持原有键连接。Ctrl+B 明确成键/断键；
需要重新推断时使用 `Edit → Rebuild bonds from distances`，支持 Ctrl+Z。
详见 [v2.0.2 说明](docs/FEATURES_v2.0.2_CN.md)和[验证记录](docs/VALIDATION_v2.0.2.md)。

v2.0.1 更新：底部信息简化为 Composition、electrons even/odd 等短字段，省略冒号；
Short contacts 只显示数量，点击可查看原子对、距离及周期像平移。
周期性体系的 Results / info 增加晶胞体积。详见 [v2.0.1 说明](docs/FEATURES_v2.0.1_CN.md)。

v2.0.0 更新：按选中原子位移占比筛选振动、仅显示虚频、静态位移箭头；
增加多参数几何曲线、平面/向量参数、曲线点击跳帧、统计和 CSV；
增加全原子或指定骨架的轨迹显示对齐，保留原始坐标，PNG/GIF 跟随显示。
xTB 没有坐标的每一步能量均显示在左侧树中，可逐步点击查看，无需结构文件。
入口位于 Files 页和 Analysis 菜单。详见 [v2.0.0 使用说明](docs/FEATURES_v2.0.0_CN.md)。

v1.11.1 更新：结构与能量独立读取，文件不必配套。纯能量文件显示结果和曲线，不显示
结构视图或虚拟帧；纯结构文件可正常浏览、播放，不显示能量，也不提供空曲线。
详见 [独立读取说明](docs/FEATURES_v1.11.1_CN.md)。

v1.11.0 更新：增加 xTB/g-xTB 的几何优化、总能量及 HOMO/LUMO 支持。
主输出可核对并关联同目录的优化轨迹；能量曲线支持跳转到已有结构、单位切换和 CSV。
分数占据优先采用原文 HOMO/LUMO 标记，alpha/beta 分别显示。
详见 [v1.11.0 使用说明](docs/FEATURES_v1.11.0_CN.md)。

v1.10.0 更新：NEB/NEB-TS 按始末态预优化、NEB、TS 精修和 Hessian/频率阶段显示，
支持完整路径快照、固定 image 的优化历史及对应序列播放/GIF。
新增 GOAT 构象能量、布居、温度重算和 RMSD 分析，以及 SOC 复数耦合、混合态组成与修正吸收。
入口为 Files 页的 **NEB / GOAT / SOC…** 或 Analysis 菜单。
详见 [v1.10.0 使用说明](docs/FEATURES_v1.10.0_CN.md)。

v1.9.0 更新：HOMO/LUMO 改为点击 Files 页按钮或 Analysis 菜单后打开；底部 Short contacts
右侧同步显示选中原子的键长、键角或二面角。补齐常见 ORCA 4/5/6 输出的计算总览、
优化/扫描曲线、轨道能量、振动动画、IR/Raman/UV-Vis、偶极与跃迁组成。
详见 [v1.9.0 使用与 ORCA 支持说明](docs/FEATURES_v1.9.0_CN.md)。

v1.8.0 的框选累加、逐次撤销、原生高对比外框、Ctrl+A、同文件跨帧显示同步、计算总览及
主要跃迁组成继续保留；键比原子更快变透明。

v1.7.2 更新：左下角 XYZ/abc 字母持续正对镜头，箭头粗细固定，偶极 Scale 可手动输入，
激发态列表清理未知对称性占位符；**Ctrl+Shift+B** 切换无填充虚线框选。
Boundary 现在复制完整晶胞及原子，保留各单胞尺寸并显示内部边框。
详见 [八项显示与交互更新](docs/DISPLAY_UPDATES_v1.7.2_CN.md)。

当前版本：**3.5.2**。已在 v1.6.0 的真实扩胞功能之上，重新实现 v1.4.0 与 v1.5.0 的功能：高质量 GIF、保存目录、正对镜头的轴字母、能量显示单位、IR/Raman/UV-Vis 模拟光谱、普通/激发态/跃迁偶极与导出、成键修正、复制粘贴、框选、元素组折叠行为及 Boundary。保留先显示窗口再预加载、Gaussian 优化/频率分组、等值面精确输入及逐原子显示控制。项目采用 **MIT 协议**。

v1.7.1 修复跨晶胞片段选择：**Ctrl+G** 需要相邻晶胞时自动建立可撤销的真实超胞，Coordinates、Atoms 和原子编号同步增加，**Ctrl+I** 对扩胞后的全部原子反选。**Ctrl+Z** 可恢复扩胞前的结构与体数据。详见 [本次修复说明](docs/FIX_PERIODIC_FRAGMENT_v1.7.1_CN.md)。

这是对既有功能的重新实现，原 v1.4/v1.5 源码未找回。当前源码已包含恢复后的功能与扩胞，操作入口见 [v1.7.0 恢复说明](docs/RESTORED_FEATURES_v1.7.0_CN.md)。

## 当前功能

- 启动时显示纯白欢迎页：LELE、英文全称和版本号，横向走动的“乐乐”，以及快捷键说明。

- 分子、晶体、计算输入和输出的结构读取与格式转换，沿用 ChemStructConverter 后端及 ASE。
- 九种显示风格、自定义元素颜色、预设保存、标签、晶胞和 XYZ/abc 坐标轴。
- 左侧 **Atoms** 页按元素列出所有原子，可单独或批量调整显示、颜色、透明度、标签/编号或自定义文字，支持 Ctrl+Z 撤销。
- 底部左右分栏：左边保留紧凑的可编辑坐标表及原有文本/信息标签页，右边为空白预留区，分隔线可拖动。
- 多选、片段选择、反选、删除、撤销和坐标编辑；距离、键角和二面角测量。
- 移动、旋转和改坐标保持已有键；删除、粘贴及扩胞保留连接关系。Ctrl+B 明确修改键，`Edit → Rebuild bonds from distances` 主动重新推断，Ctrl+Z 恢复坐标与连接。
- Ctrl+H 在两个选中原子之间绘制/移除虚线氢键，与普通键独立，支持撤销及周期像。
- 每个文件独立记住本次会话中的相机和显示设置，切回时恢复配色、标签、晶胞、Boundary、偶极和等值面参数。
- `Edit → Build supercell…`：设置 a/b/c 扩胞倍数，预览真实原子数，扩大当前帧的晶胞。支持坐标包裹、显隐/颜色/透明度继承及撤销；[扩胞说明](docs/SUPERCELL_CN.md)。
- 选中三个及以上非共线原子后，点击 `Fit selected plane` 才拟合并显示平面；支持周期镜像和将完整结构、晶胞及附带网格刚性对齐到 XY。
- 支持的轨迹文件逐帧浏览和播放，包括 SIESTA 输出/ANI 历史；有相应能量数据时绘制能量曲线。
- xTB/g-xTB 优化主输出与轨迹：读取结构、总能量、优化状态和打印的 HOMO/LUMO；按文件核对轨迹，缺少结构的周期保留能量曲线，不代用其他计算的坐标。
- ORCA NEB/NEB-TS 分阶段浏览、路径能量/力曲线、固定 image 历史、Hessian 来源与周期；曲线点与匹配结构联动，播放/GIF 跟随当前序列。
- GOAT 构象集合的相对能量、原始/重算布居、温度与简并度、全原子/重原子对齐 RMSD、构象跳转和 CSV。
- SOC 复数矩阵元与分量热图、混合态能量/组成、SOC 修正后的吸收与复数跃迁偶极，和普通激发态结果分别显示。
- Gaussian/ORCA 同一输出中的几何优化与频率结果分别列在 Files 树中，选择任意振动模式即可播放，虚频单独标注，支持查看 IR 强度。
- 原子总数、晶胞组成/分子式、考虑净电荷的电子奇偶性、几何氢键候选、短距离检查、CUBE 正负等值面和 PNG 截图。
- 几何优化/普通轨迹和当前选中振动模式可保存为 GIF，保留当前视角、配色和标签，支持进度显示与取消。
- Gaussian/ORCA IR/Raman/UV-Vis 模拟光谱、偶极类型选择与箭头、原始跃迁表和偶极 CSV 导出；IR/Raman 强度显示在频率后。
- 分子软件的能量以 kcal/mol 显示，周期软件以 eV 显示；内部保留 ASE eV 单位。PNG/GIF 和曲线/表格默认保存到输入文件目录。
- Boundary 按完整晶胞复制显示，保留各单胞大小和内部边框；Ctrl+Shift+B 切换无填充虚线框选，Ctrl+C 复制与 Ctrl+V 后单击粘贴支持跨文件。

轨迹帧数、能量等内容取决于文件本身及读取器。结构编辑只作用于当前帧；保存修改后的坐标请使用 `Export structure`。

详见[单原子显示与底部左右分栏说明](docs/ATOM_CONTROLS_CN.md)，包含操作方法和界面截图。

## 欢迎页与乐乐

未指定文件启动时，左侧 Files 列表保持为空，中央显示完整的白色欢迎页。点击 `Open a file`、按 `Ctrl+O` 或把文件拖入窗口即可开始；成功读取后自动显示三维画布和坐标表，取消打开或读取失败时保留欢迎页。通过命令行指定结构文件时，窗口先显示，预加载完成后自动打开指定结构。

启动流程为：**先显示窗口 → 自动后台预加载 → 就绪**。欢迎页标题首次绘制后，后台线程自动加载 NumPy、ASE 基础模块、VTK 和核心读取模块；完整 ASE 格式注册、SciPy 空间分析和图片导出依赖按需加载，随后由界面线程准备隐藏的三维画布，状态栏显示 `Ready`。加载期间欢迎页动画和菜单仍可使用；此时选中的文件会排队，准备好后自动打开，无需打开结构来触发加载。欢迎页上修改的显示设置会保留到结构视图。**更新源码后须重新运行 `build_windows.bat`，旧 EXE 不会自动获得此优化。** 参见[当前启动性能验证](docs/PERFORMANCE_v3.5.1_CN.md)。

欢迎页从上到下分为三部分：

1. **LELE / Local Environment and Lattice Explorer / Version 2.6.0**，版本号正下方显示 **sjzhang0905@hotmail.com**。邮箱可选择复制，点击可打开系统邮件客户端；邮箱下方显示可点击、可复制的仓库地址 **https://github.com/sjzhang0905/lele**。
2. **鹦鹉“乐乐”**：从原始帧图中使用前四帧，以“**站立→左腿→站立→右腿**”重复，不再使用末尾多余的站立帧。每 **0.8 秒**姿态与横向位置同步瞬间切换，帧间保持不动；四帧步态周期为 **3.2 秒**，每 **25.6 秒**完成八个完整步态周期、横穿画布并重新从左侧开始。
3. **目前已支持的快捷键**，按文件编辑、原子与片段、鼠标与导航分组。

鹦鹉头顶不再显示“乐乐”名牌。画布下方保留 `Meet 乐乐 · LELE's little explorer`。中文采用系统字体回退。

小窗口自动减少快捷键列数，并允许纵向滚动；欢迎页隐藏后停止动画。原始帧图随源码、wheel 和 Windows 打包一起包含，无需额外下载或安装 GIF 组件。

![欢迎页标题、联系邮箱与仓库地址](examples/welcome_preview.png)

## 后续规划

表面、碳材料和异质结构构建，更多旋转矩阵工具，以及 AIMD 自动分析、科学绘图和 SVG 出图属于后续开发内容，**本版尚未集成**。

## Windows 启动与打包

1. 使用 64 位 Python 3.12，或 3.11，解压完整源码目录。
2. 双击 `start_windows.bat`，自动建立环境、安装依赖并启动。
3. 窗口标题应为 `LELE 2.6.0 - Local Environment and Lattice Explorer`。
4. 首次成功启动后，可运行 `build_windows.bat`。新程序位于 `dist\LELE\LELE.exe`，分发时保留整个 `dist\LELE` 文件夹及其 `_internal`、`LICENSE` 和 `SOURCE_NOTICE.md` 内容。

从已配置好的开发环境也可执行：

```text
python -m pip install -e ".[test]"
python -m lele
python -m pytest tests -q
```

`build_windows.bat` 与 GitHub Actions 的 Windows 构建均已指定 `lele/assets/lele.ico`。
图标取自欢迎动画的第一帧站立姿势，与动画一样朝右，透明背景，包含 16、24、32、48、64、128、256 像素版本；程序窗口使用相同图标。
**需要重新运行 `build_windows.bat` 才会生成带新图标的 EXE**；源码更新不会改写之前已经打包好的 EXE。本次源码包内已包含所需图标，无需另外转换或设置路径。

## 常用操作

| 操作 | 方式 |
|---|---|
| 打开结构 | Ctrl+O，或拖入文件 |
| 原子多选 | 三维画布逐个单击，或在坐标表选择多行 |
| 全选原子 | Ctrl+A；输入框内仍为全选文字 |
| 反选 | Ctrl+I |
| 删除选中原子 | Delete；输入框内仍用于删除文字 |
| 撤销结构编辑 | Ctrl+Z |
| 选中相连片段 | Ctrl+G |
| 切换选中原子之间的成键 | Ctrl+B |
| 切换框选模式 | Ctrl+Shift+B；每次拖框累加，Ctrl+Z 撤销本次，Esc 退出 |
| 拟合最佳平面 | 选择至少三个非共线原子，点击左侧 Edit 页或 Edit 菜单的 `Fit selected plane` |
| 沿 X/Y/Z 观察 | View → X / Y / Z，从相应正轴方向朝结构观察 |
| 导出结构 | Ctrl+Shift+S |
| 保存截图 | Ctrl+S，当前为 PNG |

## Gaussian 优化与频率

打开同时包含优化和频率计算的 Gaussian `.log` / `.out` 后，左侧 **Files** 树会分为：

- **Geometry / optimization**：原有结构帧和能量，保留逐帧浏览与播放。
- **Frequencies**：全部已打印的振动模式及波数（cm⁻¹），负频率标为 **imaginary**（虚频）。

点击频率立即播放该模式，上下键也能切换。树下的 **Vibration** 区提供暂停/继续、
**Stop / reset**（停止并恢复参考构型）、**Amplitude**（最大原子位移，Å）和
**Speed**（演示速度，周期/秒）。可用 **Analysis → Vibrational frequencies** 进入首个模式。

每组频率使用该次计算对应的参考构型及坐标方向；多个 Link1 频率计算分别列出。
动画期间坐标表和结构导出使用参考构型，优化轨迹坐标保持完整。选择优化帧后可继续编辑坐标。
缺少完整位移向量的频率仍会列出，并提示动画不可用。

可用 `examples/synthetic_opt_freq.log` 试用；该示例中的频率、强度和位移为明确标记的人工测试数据。
详见[Gaussian 频率与振动动画说明](docs/GAUSSIAN_VIBRATIONS_CN.md)。

![频率列表与振动播放控件](examples/gaussian_vibrations_preview.png)

## 保存 GIF 动画

使用 **File → Export animation GIF…**：

- **Geometry / optimization trajectory**：导出优化或普通轨迹，可选起止帧、抽帧间隔及往返播放。
- **Current vibration**：先在 Files 中选择一个频率，再导出该模式的完整周期，可设置振幅和周期时长。

两种导出均可设置宽度、FPS 和循环播放，输出高度按当前画布比例自动计算。
导出只包含三维画面，保留当前相机、颜色和标签；原始坐标及主窗口播放状态保持完整。
取消时保留原有文件。详见 [GIF 导出说明](docs/GIF_EXPORT_CN.md)。

## 等值面精确输入

打开 CUBE 文件后，在左侧 **Field → |Isovalue|** 输入框中点击数值，按 Ctrl+A 后直接输入，
例如 `0.01234567` 或科学计数法 `1.25e-5`。按 **Enter**、点击 **Apply** 或移开焦点后更新等值面，
输入到一半时不重绘。支持最多 12 位小数，范围为 `1e-12` 至 `10000`；上下箭头仍按 `0.005` 调整。

## 菜单与底部统计

| 菜单 | 功能 |
|---|---|
| File | 打开文件、导出结构、保存 PNG、导出 GIF 动画 |
| Edit | 撤销、选择片段、反选/清空选区、删除原子、切换成键、拟合平面及对齐到 XY |
| View | 适配窗口、等轴测、X/Y/Z 视角、Projection 正交/透视投影 |
| Analysis | 计算总览、HOMO/LUMO、能量/收敛曲线、频率/光谱、NEB/NEB-TS、GOAT、SOC、Hessian 历史 |
| Help | 帮助与快捷键 |

顶部不再为每个命令单独占用工具栏按钮，原有快捷键保持可用。X/Y/Z 仅改变观察方向，不修改原子坐标或晶胞；切换投影会保留当前观察方向。

底部统计示例：`Atoms: 5 | Cell composition: Cu4O1 | Electron parity: Even (assumed charge 0) | Short contacts <0.60 Å: None`。`Atoms` 是当前帧的原子总数，与选中数量无关；非周期结构显示 `Formula`。电子奇偶性显示为 `Odd`（奇数）或 `Even`（偶数），不显示电子总数。默认使用文件中的净电荷；未知电荷时明确标注 `assumed charge 0`。可在左侧 Edit 页修改 `Net charge` 来调整奇偶性判断。

只选中原子不会生成最佳平面。改变选区、参与拟合的坐标、晶胞或周期镜像选项后，旧平面会清除；再次点击 `Fit selected plane` 才重新生成。`Show fitted plane` 仅控制已经生成的平面是否可见，不会自动启动拟合。随后点击 `Align fitted plane to XY` 可将完整结构、晶胞和网格一同旋转，支持 Ctrl+Z 撤销。

本次检查结果与环境限制见 [v1.11.1 验证记录](docs/VALIDATION_v1.11.1.md)。

## 配置与版本历史

LELE 使用独立、固定的 Qt 应用配置目录。首次运行时会尝试从原 ChemViewStudio 或旧启动入口目录复制有效的显示预设；已有 LELE 配置优先，旧文件保留。

历史说明和旧验收结果已归档到 `docs/history`。转换后端继续使用 ChemStructConverter 的原名称。

## GitHub 准备

源码仓库为 [sjzhang0905/lele](https://github.com/sjzhang0905/lele)。本目录包含标准 Python 项目元数据、Git 忽略规则、换行规则，以及 GitHub Actions 测试和 Windows 打包定义。详细操作见 [开发与发布说明](docs/GITHUB_PREPARATION_CN.md)，实际工作流状态请在仓库的 Actions 页面查看。

## 许可

从 **1.0.1** 起，LELE 原创源码、文档、素材和作者分发的可执行程序采用 **MIT 协议**，见 [LICENSE](LICENSE)。第三方组件和依赖保留各自许可及版权声明，见 `SOURCE_NOTICE.md`。

旧的 binary-only 协议已归档至 `docs/history/BINARY_ONLY_LICENSE_pre_v1.0.1.txt`，仅供历史参考，不适用于 1.0.1 及以后版本。
