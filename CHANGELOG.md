# 更新记录 / Changelog

## 4.5.0 · 2026-11-25

- 新保存的 `.lele` 项目为 UTF-8 JSON 文本。坐标、晶胞矢量、场网格及轨道系数以数值写入，复数按实部和虚部成对保存。用文本编辑器搜索 `"name": "positions"`，后面的 `values` 按原子列出 Cartesian 坐标（Å）。修改后可以重新打开。打开旧版二进制项目后，使用 **File → Save project as…** 可另存为文本。
- **Field → Planar slice…**、**Edit 标签页 → Fit selected plane** 和 **Edit 菜单 → Crystal tools… → HKL planes** 可设 1–100 个等高值，默认 7 个。开启等高线后，通过 **Contour levels** 调整数量，通过 **Show contour values** 控制是否在线上标注数值。等高值均匀分布在切面的取值范围内，开启固定色标后只使用与色标重叠的范围。每个 HKL 平面和拟合平面的设置随项目保存。
- 镜像、绕选中轴旋转、设定二面角、重设原点和坐标轴、修改真空层、拟合及对齐平面从 **Edit** 标签页操作。**Axes** 保留三种基底下的 ±45° 旋转，**Atoms** 保留框选按钮和 Ctrl+Shift+B 快捷键。**Files** 提供扫描曲线、几何参数曲线、轨迹对齐、振动模式和已有 NEB 路径。配位多面体分析位于 **Crystal tools… → Polyhedra**。主菜单已移除这些重复入口。
- Save projects as editable UTF-8 JSON and open earlier ZIP/NPY projects directly. Set contour levels and value labels for grid, Miller and fitted planes. Common editing, viewing and analysis operations now have one tab entry apiece.

[项目格式、切面与菜单验证](verification/v4.5.0/README.md)

## 4.4.0 · 2026-11-24

- Current selection 的 Free X/Y/Z 与 POSCAR 的 Selective dynamics 标记一致。T 表示放开，F 表示固定，— 表示该方向约束未知。面板注明 Direct 或 Cartesian 基底。
- 导出 Direct 或 Cartesian POSCAR 时，**Merge all** 按元素首次出现的次序合并原有原子，**Merge adjacent** 只合并相邻同元素。新增原子统一排在原有原子之后，按当前相对次序单独分组。分三次给 Fe₃O₄ 添加 O、O、H，两种方式都导出 `Fe O O H` 和 `3 4 2 1`。
- Field 页通过 **Select orbital…** 选择 FCHK、Molden 的分子轨道。弹窗按文件提供的自旋通道列出轨道编号、占据数和能量。WAVECAR 的 **Select band…** 在同一弹窗中按自旋和 k 点列出能带。可点击行或输入编号定位。
- **Fit selected plane** 使用带余量的矩形覆盖结构、显示晶胞及当前场网格的投影。有限网格内按场值着色，矩形的其余部分使用平面底色。

- Use POSCAR-style mobility flags in Current selection. Group original and added atoms separately on POSCAR export, including after editing atom indices or restoring a project.
- Choose molecular orbitals and WAVECAR bands in a spin-resolved table with k-point coordinates when available. Fitted planes have rectangular bounds in 3D and finite-field colors cover only the sampled region.

[导出、轨道选择与拟合面验证](verification/v4.4.0/README.md)

## 4.3.1 · 2026-11-24

- 中英文 README 精简为项目简介、手册、安装和项目链接。历版更新及相关验证资料集中在本文件。
- Axes 的旋转控件合并为一行，坐标轴位置和类型改为互斥按钮，XYZ 长度可输入或用滑杆调节。Labels、Boundary、Fragment、Atoms selection 和 Style 重排常用控件。
- Labels 和 Atoms 移除元素与 ORCA 编号的组合标签，保留单独的 ORCA 编号。Labels 保留内置字体，移除本地字体文件选择。旧项目中的组合标签和字体设置可继续显示。
- Files 并列提供几何和能量/RMS 曲线，保留扫描曲线。振动筛选、轨道能量及 NEB、GOAT、SOC 分析从 Analysis 菜单进入。Edit 保留净电荷、移至原点等控件，移除重复的选择和成键按钮。
- 周期结构的 Boundary 持续启用。Reset to one cell 恢复一个晶胞。旧项目中已关闭的 Boundary 按一个晶胞打开。
- Simplify both READMEs and collect release guides and validation references here.
- Compact the lower panels and the Style and Edit controls. Choose axis positions and types directly, and adjust Cartesian axis length with a slider or a numeric value.
- Keep the standalone ORCA atom index in both label selectors. Existing projects retain saved combined labels and font settings. New font selections use the built-in families.
- Open energy/RMS curves from Files and use Analysis for vibration search, orbital energies, NEB, GOAT and SOC. Boundary stays active for periodic structures, including after a one-cell reset.

[界面与项目兼容性验证](verification/v4.3.1/README.md)

## 4.3.0 · 2026-11-24

可沿屏幕轴、笛卡尔轴和晶轴以 45° 为步长旋转视图。Windows 文件窗口加入桌面、下载、文档及快速访问目录。ESP 色标宽度减半并居中。

- Center ESP color bars at half their previous width on mapped surfaces, field slices and image exports.
- Add Windows Desktop, Downloads, Documents and folders from Explorer Quick Access to the sidebar of open, save and folder dialogs. Explorer folders are read in the background when a picker opens.
- Rotate the current view in 45° steps from View or the Axes tab. Choose a screen axis, a Cartesian axis or a direct lattice vector. Each step turns about the displayed atom centroid and preserves the current zoom and projection.

## 4.2.3 · 2026-11-24

欢迎页绘制后预加载首个结构使用的画布和公共模块。小型 XYZ 分子采用有界成键搜索，渲染复用键长和配色计算。

- After the welcome page paints, prepare the native canvas and the modules used by the first structure. A queued file can open as soon as the common components are available, while optional reader imports yield to the request.
- Open small, plain XYZ molecules with a bounded pair search. Reuse edge lengths for bond occlusion and repeated palette conversions when building molecular and periodic scenes.

## 4.2.2 · 2026-11-23

默认启用前两盏灯并调低高光大小和亮度。等值面默认透明度为 0.50，画布和图片导出默认使用不透明的纯白背景。ESP 极值点入口按文件内容显示。

- Use the first two lights by default and start both highlight sliders at 47.
- Show **Add ESP extrema…** on ESP results and on documents with an ESP-mapped surface.
- Start basic positive/negative surfaces, ESP and electron–hole layers at 0.50 opacity.
- Default to opaque white for canvas captures, batch images, GIF frames and scientific plots. Preserve pure white during GIF palette quantization and restore the working view after export.

## 4.2.1 · 2026-11-23

ESP 极值点改为半径 0.08 Å 的金色小球，数值标签在旋转时始终正对视角。欢迎页新增在线手册入口。

- Keep ESP extremum values upright and facing the camera as their 3D anchors move across the view. Apply this to existing projects, picking and image exports.
- Reduce the extremum marker radius to 0.08 Å and use metallic gold.
- Add the online LELE Manual to the welcome page.

## 4.2.0 · 2026-11-23

支持从四列文本导入 ESP 极值点并编辑标签。ESP 初始色标范围设为 −0.03 至 +0.03，Style 支持删除已保存的样式。

- Delete a named user style from Style. Open documents retain their current appearance.
- Start ESP maps at −0.03 to +0.03 in the color field’s units. Omit the placeholder unit from color bars.
- Attach a four-column ESP extrema file from the Files context menu. Gold markers anchor editable one-decimal labels at the supplied points. Projects and image exports include both.

## 4.1.1 · 2026-11-23

根据 VMD 参考校准 Glossy 材质的高光与三盏灯，将高光亮度和大小改为独立控制。

- Calibrate the default Glossy material and three directional lights against the supplied VMD reference. Use neutral specular reflection and explicit per-instance diffuse RGB on atomic glyphs.
- Add an independent Highlight brightness slider to Style. Preserve brightness in style presets and projects. Older projects with the original default lights adopt the new defaults when opened. Custom light settings are retained.

[Three-light comparison with VMD](verification/v4.1.1/LELE_v4.1.1_Highlights.png)

## 4.1.0 · 2026-11-21

用 Ctrl+F 固定选中原子，Ctrl+Shift+F 清除固定，Ctrl+Alt+F 选中当前帧全部整原子固定的位点。POSCAR 和 Gaussian GJF 导出会使用这些属性。Analysis 菜单可直接选择两份本地体数据，绘制 ESP 或空穴–电子分布。[操作与格式说明](docs/FEATURES_v4.1.0_CN.md)

- Edit whole-atom optimization constraints on the current frame, select all fixed sites, and export the flags to POSCAR and GJF. Recover printed constraints from supported outputs.
- Open two local fields from Analysis to map ESP on density or display electron and hole surfaces. VASP ESP uses total charge density and the positive-probe scalar potential from an ionic + Hartree LOCPOT.

[Workflow and file formats](docs/FEATURES_v4.1.0_CN.md)

## 4.0.1 · 2026-11-20

最短像、周期邻居、短接触和片段展开按周期方向的独立晶格矢量计算，支持非周期晶矢为零或线性相关的一维和二维晶胞。首批科学验证集附结构文件、精确预期结果和独立复算脚本。[验证集](verification/scientific/README.md)

- Determine lattice validity from the periodic rows. Compute minimum images, neighbors, short contacts and fragment connectivity in valid one- and two-dimensional lattices with singular full cells.
- Preserve the source cell in boundary display, image picking, fragment supercells and Cartesian edits. Miller planes use the full-cell validity check.
- Add 12 redistributable periodic-geometry cases with exact reference results and an independent calculator.

[Scientific reference data](verification/scientific/README.md)

## 4.0.0 · 2026-11-20

加快大体积 CUBE、OUTCAR、AIMD 轨迹和 WAVECAR 的读取与显示。长轨迹保留全部帧和双精度坐标，编辑帧与计算源记录彼此独立。[实测数据和使用说明](verification/v4.0.0/README.md)

- Read common CUBE scalar blocks with an optional x64 C++ parser. Size the import budget from available memory, share the VTK scalar buffer and reuse contours when field content and levels match.
- Index OUTCAR records and stream numeric tables and shielding sections. Locate a WAVECAR companion's last complete structure while retaining printed lattice, energy and source-line associations.
- Parse standard XDATCAR and XYZ coordinates as float64 in native code. Large trajectories use file-backed, independent source and editable coordinates. Update visible coordinate rows during playback and populate the Atoms tab when opened.
- Validate full-complex WAVECAR bases in bounded vectorized blocks, reuse matching spin and k-point layouts and reduce FFT temporaries. Coefficients remain accessible by band.

[Performance measurements](verification/v4.0.0/README.md)

## 3.18.0 · 2026-11-20

普通右键拖动绕全部原子的几何中心旋转，Alt＋右键绕移动片段的几何中心旋转。Edit → Mirror selected fragment 可按 YZ、XZ 或 XY 平面镜像所选原子。Style → Highlight size 可调节高光大小。File → Apply new coordinates 可浏览本地 POSCAR、CONTCAR 和其他计算输入，预览写回路径与差异。目标文件的 Selective dynamics 按行保留，新增行补 T T T，减少时从末尾截断。

- Mirror selected atoms across a Cartesian plane through the selection centroid or the origin. YZ is the default plane.
- Roll the full view about the arithmetic mean of all atomic positions. Alt + right drag uses the moving atoms' own centroid.
- Adjust specular highlight width in Style with live updates. Presets, projects and image exports use the same material.
- Browse local files in Apply new coordinates. The dialog shows the coordinate source and the input to update, supports either direction and keeps a backup. POSCAR and CONTCAR targets retain per-row selective dynamics, append all-free rows or truncate from the end.

## 3.17.0 · 2026-11-18

可手动关联 CP2K 优化、AIMD 和 xTB 优化轨迹，点曲线查看对应结构。Results / info 支持复制，底部原文页和原子索引说明已移除。[更新说明](docs/FEATURES_v3.17.0_CN.md)

- Associate CP2K geometry/cell optimization or MD outputs with position trajectories from the loaded-files menu. Link xTB optimization cycles, gradient norms and orbitals to their XYZ geometries.
- Retain sparse trajectory mappings in curve selection, CSV export and portable projects.
- Copy the selected text or the whole Results / info panel with Ctrl+C. Remove the raw source text panes and the global-index explanation in Atoms selection.

[Release notes](docs/FEATURES_v3.17.0_CN.md)

## 3.16.0 — 2026-11-18

加快 Alt＋右键片段旋转，支持 DIM-GROUP 周期结构和 XSF 三维等值面。调整 11 种常用元素的默认配色，将 Style 三条滑杆的默认值置于中点，主窗口标题栏改为灰色。[更新说明](docs/FEATURES_v3.16.0_CN.md)

- Reuse VTK atom and bond geometry during fragment rotation, including periodic images. Coalesce pointer paints and retain the final mouse displacement.
- Read DIM-GROUP XSF structures and named real-space 3D grids, with skew bases, endpoint sampling, multiple datasets and signed isosurfaces.
- Distinguish eleven common elements in the default palette and use the same palette for element selection swatches.
- Center the three Style sliders on their default physical values while retaining their previous ranges and per-document settings.
- Apply a neutral gray main-window title bar.

[Release notes](docs/FEATURES_v3.16.0_CN.md)

## 3.15.0 — 2026-11-17

修复分子 CUBE 周期性误判和 electron/hole 第二图层；新增 VMD 式静电势配色和集成实时颜色范围控件；修复 Scan 步选择、跨晶胞测距；新增已加载文件右键操作、记忆裁剪导出；毛毛虫图继承主画布外观；弹窗只置于 LELE 前方。

- Correct molecular CUBE periodicity and preserve selected Boundary images for measurements.
- Embed live VMD-style field mapping controls in the surface-layer editor; correct out-of-range source switches and simplify scalar bars.
- Select the final optimization frame for Scan step parents.
- Add loaded-document rename, unload and open-folder context actions.
- Remember cropped PNG export choices and omit scene axes while cropping.
- Inherit main-canvas appearance in NEB caterpillar surroundings while preserving path atom styling.
- Use owner-relative dialog stacking instead of global topmost windows.

[update notes](docs/FEATURES_v3.15.0_CN.md)

## 3.14.0 — 2026-11-13

ORCA index 仅保留为原子标签模式；绕轴旋转增加实时滑杆预览；默认原子和键尺寸分别减两格、一格，选中原子可独立设置 Size scale；菜单移到左侧栏上方；Boundary 和真实扩胞支持沿正负方向交替复制并保持原结构坐标。

- Confine zero-based ORCA atom indices to Label / Atom labels modes; use one-based atom indices in coordinate tables, editors, selection controls, tooltips and exported analysis tables.
- Add a synchronized angle slider and live, non-destructive canvas preview for selected-axis rotation. Cancel preserves source geometry; Rotate commits one undoable edit, and changed sources invalidate an open preview.
- Reduce the default atom-size slider from 47 to 45 and bond thickness from 6 to 5. Add selected-atom size multipliers that persist through projects, replication and image export.
- Place the application menu above the left sidebar, returning the remainder of that row to the canvas.
- Add alternating periodic copies in 0, +1, −1, +2, −2 order. Boundary remains display-only; Build supercell adds real atoms and enlarges the cell, with preserved source coordinates, origin-aware outlines, connectivity and undo.

[update notes](docs/FEATURES_v3.14.0_CN.md)

## 3.13.0 — 2026-11-13

Current selection 去掉 ORCA 列；Atoms selection 新增元素、编号、距离和逻辑组合表达式，Help 提供语法说明；功能弹窗改为非模态置顶；完整欢迎页显示后自动预加载读取依赖并预热三维渲染。

- Remove the ORCA-number column from Current selection while retaining it in other index tools.
- Add documented atom-selection expressions for elements, index ranges, booleans and nearest-selected-atom distance, including periodic minimum images, cancellation and undo.
- Present menu forms, help, file/color pickers and analysis windows as topmost modeless dialogs. Guard source-dependent acceptance against changed documents, geometry, selection and nested editor lifetimes.
- Wait for the complete visible welcome paint, automatically preload common readers/ASE/SciPy dependencies, then warm the hidden VTK context and common rendering pipelines before Ready.

[update notes](docs/FEATURES_v3.13.0_CN.md)

## 3.12.0 — 2026-11-12

多文件导入按自然文件名排序；支持拖入文件夹；新增 Convert all、Export PNG all；修复切换文件后视角缓存未刷新的跳变。

- Sort each multi-file import batch by Windows logical filename ordering on Windows, with a natural numeric fallback on other platforms; preserve the resulting order in the Files tree.
- Discover supported scientific files recursively in dropped folders, with cancellation, deduplication and bounded format probes off the GUI thread.
- Add File → Convert all and Export PNG all for remembered per-document frames/views, unique output filenames and cancellation/failure summaries.
- Explicitly invalidate the active VTK camera after restoring its fields, preventing cached matrices from rendering the previously viewed document until the next mouse gesture.
- End interrupted native drags on focus loss and file switches; file headings restore the last viewed frame while explicit geometry nodes retain their selected frame.

[update notes](docs/FEATURES_v3.12.0_CN.md)

## 3.11.0 — 2026-11-12

增加从 0 开始的 ORCA index、全局编号选择、Current selection 一键复制坐标、绕选定轴转动片段与设置二面角；ORCA scan 按扫描点分组并显示最终能量扫描曲线，支持多坐标同步扫描。

- Remove the redundant Selected labels buttons; retain all modes in the atom appearance Label dropdown.
- Add explicit zero-based ORCA atom numbering to labels, atom/coordinate/selection views and atom-index controls, alongside existing one-based indices.
- Add global-index and ORCA-index range selection to Atoms selection; combine filled rows without duplicate atoms.
- Copy the selected coordinates as an XYZ body with original Cartesian positions and no header or recentering.
- Rotate connected fragments around an atom-defined axis, or set a selected four-atom dihedral, with undo and preserved connectivity.
- Group ORCA relaxed scan optimization histories by scan step; plot final endpoint energies separately and support simultaneous coordinate paths, incomplete-point markers, source-geometry navigation and CSV export.

[update notes](docs/FEATURES_v3.11.0_CN.md)

## 3.10.0 — 2026-11-11

Current selection 改为对齐的纯文本；启动自动最大化；View 新增 a/b/c 方向；进度条上方添加按进度前进的乐乐走路动画；默认成键阈值改为 0.88。

此前 16 个跳过记录已补齐，展开的 19 个测试全部通过。

- Replace Current selection's table with copyable, space-aligned monospace plain text; retain occupancy, coordinates and constraints, and defer hidden-panel formatting.
- Open the application maximized while retaining normal window restoration.
- Add View → a/b/c along the displayed direct lattice vectors, including oblique cells and trajectory display rotation; disable these views without a valid periodic cell.
- Show the original walking Lele artwork above every existing import, processing and export progress bar. Its horizontal position follows reported progress; unknown-duration work walks in place.
- Lower the default Chemcraft bond-distance multiplier from 1.00 to 0.88, synchronizing slider and numeric input while retaining explicitly saved project settings and manual bonds.

[update notes](docs/FEATURES_v3.10.0_CN.md) · [supplemental validation](docs/EXTERNAL_VALIDATION_v3.10.0_CN.md)

## 3.9.1 — 2026-11-11

原子选中标记改为实线；POSCAR 导出自动添加 `POSCAR` 文件名前缀，并询问是否合并相同元素。

- Draw selected atoms with continuous closed green rings, retaining their existing width and camera-facing behavior.
- Prefix POSCAR export filenames with POSCAR, normalizing existing prefix case without duplicating it; check overwrite after filename normalization.
- Ask whether to group equal elements for Direct and Cartesian POSCAR export. Group only an export copy in stable first-appearance order after occupancy projection, retaining per-atom constraints; No preserves existing species blocks and atom order.

[update notes](docs/FIXES_v3.9.1_CN.md)

## 3.9.0 — 2026-11-11

新增电荷密度加减运算、按元素内部编号选择原子，以及画布数字片段快捷键。

- Add scalar-field addition and subtraction with explicit channel selection, compatible-grid validation, source provenance and derived-field project/export support.
- Rename Selection to Current selection and add Atoms selection after Fragment. Element-local one-based indices/ranges select atoms across element rows, including mixed-occupancy sites.
- Add canvas-only 1–9 fragment slots: Ctrl replaces a slot, a plain digit recalls it, and Shift adds selected atoms. Preserve existing fragment metadata, undo and atom-identity remapping.

[feature notes](docs/FEATURES_v3.9.0_CN.md)

## 3.8.0 — 2026-11-10

新增 PARCHG STM、结构粉末 XRD、可拖动旋转的三维文字、四方向灯光；统一 SVG 优先与可选分辨率/平滑出图，优化片段平移，调整默认外观，Field 移到左侧并取消 GBW 支持。

- Add PARCHG-based constant-height and constant-current isodensity STM maps, normal sampling for skew cells, spin channels, map repeats and scientific-data export.
- Simulate powder XRD from structures, including mixed occupancies, atomic scattering factors, explicit reflection multiplicities, LP/B factors and broadened profiles.
- Prefer SVG for plot exports; unify raster resolution and smoothing across plotting windows, legend and NEB illustrations.
- Add movable, rotatable world-space canvas text with undo, per-document project persistence and PNG/GIF export.
- Cache fragment geometry during Alt-middle translation, rebuilding the complete view only after the gesture.
- Move Field controls to the sidebar, block wheel changes to combo/spin editors, remove GBW loading and conversion, and append structure-export suffixes consistently.
- Adjust default atom/bond sizes and palette, use VMD lime/cyan3 surfaces at 90% opacity, thicken selected-atom halos and add four independently switchable directional lights (two initially enabled).

[feature notes](docs/FEATURES_v3.8.0_CN.md)

## 3.7.0 — 2026-11-10

新增等值面矩形贯穿隐藏与恢复、完整 HKL / 拟合面上的二维场切片，以及从已加载 VASP 输出构建 NEB 能量曲线和毛毛虫图。晶体工具统一移到 Edit；Isosurface signs 支持 None，保留数据和切面。

- Hide isosurface portions inside through-depth screen rectangles without changing sampled fields. Exact mesh subtraction handles crossing triangles, mapped colors and Boundary copies; masks follow model coordinates, remain per-document and support undo, restore and project persistence.
- Merge the three duplicate crystal menu entrances into Edit → Crystal tools. New HKL planes default to Show only, with opacity applied to faces, slices, contours and edges.
- Add Isosurface signs → None, including custom layers, while retaining loaded fields and independent planar slices.
- Extend fitted planes across the displayed cell/Boundary, finite field or full molecular extent. Sample the active scalar field on arbitrary HKL/fitted planes, with color ranges, ELF defaults, contour lines, legends and adjustable resolution.
- Assemble VASP NEB paths from several loaded outputs in explicit image order, consistently selecting printed final-frame E0 or TOTEN. Show energy/path tables, CSV and curve exports, plus interactive caterpillar views with specified atoms and a selectable surrounding reference frame.
- Validate fixed cells and atom sequences, reject invalidated final-frame energies, unwrap periodic displacement steps and keep trajectory guide lines separate from chemical bonds. Preserve existing source data and first-paint lazy startup.

[feature notes](docs/FEATURES_v3.7.0_CN.md)

## 3.6.0 — 2026-11-10

底部改为三栏，新增 Selection 明细和 Fragment 管理；支持片段整体调整原子顺序、统一固定方向信息，以及 File → Apply new coordinates 将当前结构应用到已加载的计算输入。替换前预览并验证，保留其他设置及原文件备份。

- Split the lower area into three resizable panes. Add a lazy Selection table with compact source indices, occupancy components, Cartesian/fractional coordinates and explicit fixed-axis flags.
- Save named fragments per frame; select, delete or stably move them to the beginning/end of atom order. Remap occupancies, constraints, appearances, bonds and source identities, refresh both coordinate tables and retain undo/project support.
- Read verified fixed-atom syntax across supported calculation inputs, with Cartesian/Direct basis and explicit unknown states. Preserve printed QE/xTB flags in existing output scans without another full-file pass.
- Add File → Apply new coordinates for loaded Gaussian, ORCA, NWChem, CP2K, QE, SIESTA and POSCAR inputs. Replace only structural text; preview and independently parse the result before an atomic write with a unique original-file backup and stale-preview checks.
- Preserve target settings and units, use a 30 Å cubic cell for molecular sources applied to periodic templates, and retain molecular target semantics. Reject unverified external/multi-job or atom-specific identity changes instead of rewriting parameters.
- Fix reader compatibility for Gaussian Cartesian freeze columns and numeric syntax, ORCA Bohr/%coords records, NWChem molecular Cartesian units and QE explicit lattice units. Preserve prior CIF/drop, CHGCAR, Boundary and performance fixes.

[feature notes](docs/FEATURES_v3.6.0_CN.md) · [constraint coverage](docs/CONSTRAINTS_v3.6.0_CN.md)

## 3.5.7 — 2026-11-10

兼容 CIF 中 `P2(1)/c` 等螺旋轴写法；拖放先返回再读入，文件错误提示不再阻塞拖动源窗口。

- Normalize legal CIF screw-axis parentheses/underscore typography such as P2(1)/c and P2_1/c before ASE database lookup. Preserve explicit symmetry operations, coordinates, cell settings and occupancies; do not substitute P1 for unknown groups.
- Return from native file-drop events before filesystem checks, parsing or rendering. Use copy-only file import and read CIFs in the background even when small.
- Present import failures with nonmodal messages after releasing active loader/progress state, allowing queued files to continue and preserving shutdown/cancellation behavior.

[fix notes](docs/FIXES_v3.5.7_CN.md)

## 3.5.6 — 2026-11-10

修复 CP2K restart 续行读取，补充输出 Summary；Atoms 各列支持手动调宽，颜色改为方形色块，底部操作按钮不再铺满整行。

- Read CP2K restart-writer continuation records correctly, including wrapped constraints, KIND aliases and fractional coordinates. Retain restart step/time and identify expanded XC functional settings without inventing a trajectory or energy.
- Complete CP2K output summaries with printed basis/potential and DFT+U settings, Quickstep/SCF parameters, MD setup and state. Preserve missing LOW-print metadata explicitly and associate printed MD records with the correct energy evaluation.
- Make every Atoms column manually resizable; widen Atom / show, use a compact Occ. % column, and retain manual column widths through refreshes. Replace hexadecimal color labels with square swatches throughout appearance controls and use American Color consistently in UI text.
- Keep all lower-panel action buttons at their natural width, including custom font selection and Boundary Apply/Reset; preserve color selections separately from button text.

[fix and validation notes](docs/FIXES_v3.5.6_CN.md)

## 3.5.5 — 2026-11-09

- Constrain all lower settings editors, including numeric spin boxes and hidden WAVECAR controls: 90 logical pixels for ordinary values and dropdowns, 140 for high-precision isovalues. Preserve native internal line editors and their buttons.
- Keep Boundary numeric columns grouped on the left and Apply next to the positive isovalue input; prevent forms from stretching regular fields while retaining the 265-pixel slider cap.
- Retain all 3.5.4 Boundary surface fixes and prior startup/large-file performance improvements.

[layout correction notes](docs/LAYOUT_v3.5.5_CN.md)

## 3.5.4 — 2026-11-09

- Repeat cell-sized finite CUBE isosurfaces with Boundary atom copies. Keep display instances separate from physical periodicity, without adding wraparound samples or changing the source grid.
- Repeat finite-surface color mappings in the source instance coordinates, so copied surfaces retain their colors. Preserve the existing periodic CHGCAR seam/clipping path.
- Cover actual Boundary Apply/Reset, both signs and custom layers, oblique/negative cell ranges, source-data preservation and mismatched-grid warnings.

[Boundary fix notes](docs/BOUNDARY_v3.5.4_CN.md)

## 3.5.3 — 2026-11-09

- Start the sidebar at its existing 295-pixel minimum and give window expansion space to the canvas; retain manual sidebar resizing.
- Keep sidebar and lower-tab combo boxes at 90 logical pixels, with full-width option popups and current-value hover text. Cap horizontal sliders at 265 pixels while allowing narrow form rows to shrink them.
- Wrap Style help text to keep the minimum-width sidebar free of horizontal overflow. Preserve v3.5.1 startup/large-file optimizations and v3.5.2 renamed-CHGCAR detection and reading speed.

[layout notes](docs/LAYOUT_v3.5.3_CN.md)

## 3.5.2 — 2026-11-09

修复 CHGCAR 重命名后被误识别为 POSCAR 的问题，并加快 VASP 体数据读取。

- Recognize VASP charge grids by POSCAR header, coordinates and grid records even after renaming. Keep ordinary structures and their velocity blocks distinct; support common copied filenames.
- Parse VASP scalar fields in bounded NumPy chunks, retaining augmentation boundaries, spin channels, grid ordering, units, malformed-data rejection and cancellation.
- Verify renamed loading with the supplied CHGCAR and add background-import/field-control regression coverage. Include a reproducible benchmark and validation report.

[fix and performance report](docs/CHGCAR_v3.5.2_CN.md)

## 3.5.1 — 2026-11-09

加快启动、大 cube 和长步数 AIMD 文件读取；保留 v3.5.0 的全部功能。性能对比、适用范围与复现方式见[性能与验证报告](docs/PERFORMANCE_v3.5.1_CN.md)。

- Delay ASE's full IO registry, SciPy spatial routines and image-export libraries until needed; keep first-paint-before-background-loading behavior. Cache successful Windows dependency verification and invalidate it when the installation changes or a launch fails.
- Parse CUBE scalar data in bounded NumPy blocks, including very long physical lines, with complete channel/axis/unit handling and strict invalid/truncated-data checks.
- Batch XYZ and XDATCAR coordinates through NumPy, retaining Fortran exponents, repeated/variable cells, source records, extended-XYZ fallback, cancellation and frame edit independence.
- Reduce unrelated regular-expression work in VASP and CP2K output readers. Decode shared output text in chunks and quickly exclude absent NMR tables after checking the complete source.
- Add performance reproductions and regression checks; preserve existing scientific precision, all trajectory frames, and the configured volumetric point limit.

[performance and validation report](docs/PERFORMANCE_v3.5.1_CN.md)

## 3.5.0 — 2026-11-09

选中原子可独立选择 Space filling、Sticks 等显示方式；Atoms 按文件中元素首次出现的顺序排列并默认折叠，双击 Coordinates 的原子名称可展开定位。新增 NMR 屏蔽常数表、参考化学位移谱和 CSV/PNG/SVG 导出。底部左侧为 Axes/Labels/Field/Boundary，右侧为 Coordinates/Input-output/Results；Crystal、Dipole 从 View 菜单打开。保留 v3.4.0 的 ESP 映射与等值面叠加。

- Add per-atom Global / Ball and stick / Space filling / Sticks / Wireframe styles in Atoms. Each ordinary bond half follows its endpoint. Preserve colour, opacity, labels, matching-frame updates, boundary images, undo and project snapshots.
- Order element groups by retained file/component occurrence, collapse on a newly activated document, and reveal the exact source atom when its Coordinates name is double-clicked.
- Move Axes, Labels, Field and Boundary to the lower left, and the three data tabs to the lower right. Open Crystal tools and Dipole from View in reusable windows; Enter in numeric editors no longer activates export buttons.
- Read NMR total shielding records from Gaussian, ORCA, NWChem, VASP CSA tables, CP2K SHIFT files and QE/GIPAW output. Keep multiple datasets and source numbering; distinguish VASP ISO_SHIFT and ISO_SHIELD and separate G=0/core variants. Property-only files need no invented geometry.
- Add element-specific NMR tables, full printed tensors, explicit reference shieldings, stick/Gaussian/Lorentzian spectra, descending chemical-shift axes, CSV and PNG/SVG export. Save references and results in projects; source-atom navigation requires a verified matching frame. Guard against undersampled narrow peaks and run large spectrum calculations with progress feedback.
- Retain all v3.4.0 acceptance fixes, field overlays and ESP colour mapping. Add synthetic NMR examples and regression coverage.

[Chinese guide](docs/FEATURES_v3.5.0_CN.md) · [validation](docs/VALIDATION_v3.5.0.md)

## 3.4.0 — 2026-11-05

修复 v3.3.0 验收发现的三项问题；新增跨数据场等值面叠加、在电子密度等值面上映射已导入的 ESP/电势，以及色标、工程保存和 PNG/GIF 导出。

- Fix FCHK / non-frequency Molden snapshots missing calculation stages, and tolerate stage-less legacy project metadata. Do not infer optimization convergence from a snapshot.
- Fit the first generated molecular/WAVECAR field and refresh camera clipping after scene changes.
- Repeat periodic isosurfaces with Boundary, including shifted ranges, oblique cells and translated grid origins; clip to the displayed cell range. Never periodically replicate a nonperiodic field.
- Add atomic attachment of compatible CUBE / VASP grids to the current document, multiple source fields per surface layer, and Cartesian trilinear scalar color mapping at surface vertices.
- Add red-white-blue / reversed / Viridis palettes, automatic symmetric or fixed limits, explicit source units, optional color scales and coverage warnings. Preserve mappings through transforms, document switching, projects, PNG and GIF export. The viewer samples imported fields; it does not compute ESP.
- Include independent acceptance regressions, analytical mapping tests and portable example projects.

[Chinese usage guide](docs/FEATURES_v3.4.0_CN.md) · [validation](docs/VALIDATION_v3.4.0.md)

## 3.1.0 — 2026-11-04

- Add a separate Occupancy % column to Atoms: ordinary components show 100%, and fractional occupancies are displayed as percentages. Remove bracketed multi-element compositions from the atom-name column.
- List every site component under its own element, including a minority element not present among the representative species. Mixed Mn/Sn components get separate Mn and Sn rows with their own palette colours, the same source-site index and identical coordinate tooltips.
- Refresh groups when components are added or removed, refresh percentages when only probabilities change, and preserve current component focus. Selection and existing per-site appearance controls deduplicate shared site IDs; source coordinates/counts, weighted composition and CIF/project/maximum-occupancy exports remain consistent.

[usage and validation](docs/VALIDATION_v3.1.0.md)

## 3.0.4 — 2026-11-04

- Show each mixed/partial site's components and vacancy in its Atoms row. Mark coordinate-table site names with `*` and show the complete occupancy in row tooltips, retaining the compact four-column layout, original coordinates and one row per source site. Include minority elements in the element-colour selector.
- Ask “使用最大占据元素” or “取消” before non-CIF mixed-site exports. With confirmation, export an ordered copy using the most occupied element at each site, full occupancy, stable tie handling and original site order. Ignore partial vacancy fractions and omit completely vacant sites; rebuild POSCAR species blocks and retain surviving selective-dynamics flags. Preserve the editable source model, its occupancies, selection and undo history.
- Keep CIF/project occupancy roundtrips unchanged. Cancellation does not open the save picker or write a destination. Programmatic exports retain the conservative default unless `occupancy_policy='maximum'` is explicit.

[usage and validation](docs/VALIDATION_v3.0.4.md)

## 3.0.3 — 2026-11-04

- Add an Element / occupancy tab to the atom right-click dialog, alongside the existing index and swap controls. Edit multiple element/fraction rows, add or remove rows, and display the total and remaining vacancy. Reject invalid elements, duplicate rows, non-finite/negative fractions and totals above one.
- Change only the clicked site in the active geometry frame, preserving positions, indices, other frames, appearance and existing bond topology. Update site composition, rendering and POSCAR species blocks. Clear calculated frame energy/force/spin values and detach an old volumetric grid; Ctrl+Z restores the original frame and grid.
- Preserve all components and vacancy fractions in CIF/project roundtrips. Retain the existing rejection of mixed/partial-occupancy POSCAR, XYZ and GJF export; a representative display/bonding element does not implicitly select an ordered export model.

[usage and validation](docs/VALIDATION_v3.0.3.md)

## 3.0.2 — 2026-11-04

- Add Labels / Indices / Both / Hide shortcuts in Atoms for the selected atoms. Preserve global label settings, matching-frame appearance, project persistence and undo.
- Show periodic atoms on both outer cell faces, four edge images or eight corner images. Keep source IDs, counts and coordinates unchanged; repeat bonds, manual hydrogen links, labels and Bloch displacements with the displayed images.
- Initialize each newly opened document with its own enabled one-cell Boundary. Restore an existing document's saved range when switching back, and preserve project settings.
- Parse SIESTA FIRE/CG/MD move records into calculation results and energy curves. Pair fractional coordinates with the lattice printed for that move, distinguish initial/final unrelaxed coordinates from evaluated structures, and retain unmatched energies as results without borrowing a geometry. Preserve printed E_KS and final total/free-energy provenance separately and use eV in results views.
- Add the VESTA atom-colour palette, derived from the official 3.5.8 RGB table, shared by atoms, element-coloured bonds, colour controls and legends.

[usage and validation](docs/VALIDATION_v3.0.2.md)

## 3.0.1 — 2026-11-04

统一 OUTCAR 的 Step 命名，点击前后保持一致；多帧文件打开及点击文件总节点时默认显示最后一个可用结构；默认勾选 **Enable boundary display**，初始范围仍为一个原始晶胞。

- Use one frame-tree formatter for initial creation and selection refresh. OUTCAR optimization records keep their printed Step numbers, energies and convergence status; plain trajectories keep Frame labels, and custom NEB/conformer labels are preserved.
- Open new multi-frame documents at the last available structure and use that structure when selecting the file node. Explicit frame selections and saved project frame indices remain available; long trajectories still expand only the required page.
- Enable boundary display by default in both rendering options and the checkbox. The initial range remains one original cell, and manually disabled settings persist across frame navigation.
- Keep world-origin crystal axes, explicit fragment previews, aligned cell outlines and saved camera clipping compatible with the default one-cell boundary.

[fix validation](docs/VALIDATION_v3.0.1.md)

## 3.0.0 — 2026-11-03

保存 PNG 默认采用 **4 倍分辨率 + Smooth edges（平滑边缘）**。

- Default PNG saving to 4× canvas resolution with Smooth edges enabled.
- Update application and package version to 3.0.0.

[release validation](docs/VALIDATION_v3.0.0.md)

## 2.13.6 — 2026-11-03

修复验收报告中的两项坐标轴问题：原画布的 **Z/c 等角落字母被裁切**，以及 **3×/4× 平滑 PNG 中坐标轴截短**。

- Fix high-resolution PNG corner axes shrinking or clipping at 3×/4× with smooth edges. Capture independent overlay renderers, actors and text properties so orientation-widget callbacks cannot reframe tiled exports or corrupt live billboard caches.
- Fit complete XYZ/abc corner labels inside their viewport with glyph-based pixel margins. Re-evaluate after camera rotation, font changes and canvas resizing, while keeping arrow geometry and scene bounds independent of text layout.
- Add rendered-image regressions for all 1×–4×/smoothing combinations, label margins at multiple fonts/rotations, and overlay restoration after failure.

[fix validation](docs/VALIDATION_v2.13.6.md)

## 2.13.5 — 2026-11-03

将默认 Ball and stick 的 **Bond thickness 改为 7**，Default 配色的 **H 显示半径增加 15%**，当前默认元素色再混入 **5% 白色**。保存 PNG 增加分辨率和边缘平滑选项，默认 **3 倍输出 + 平滑边缘**。

- Set default Ball and stick bond thickness to 7 and enlarge Default-palette H display radii by 15%, sharing the same radius between glyphs, labels, picking, selection and the legend.
- Mix a further 5% white into the current Default colors (approximately 14.5% white relative to the original palette).
- Add PNG resolution choices of 1×/2×/3×/4× or a custom width, with 3× and smooth edges enabled by default. Use supersampling, Lanczos downsampling, finer export meshes and scaled annotations. Restore the live scene after capture and replace an existing file only after a successful save.

[guide and validation](docs/VALIDATION_v2.13.5.md)

## 2.13.4 — 2026-11-03

将 Atom colours 中的 **Sibyl** 更名为 **Default**；整套默认元素色混入 10% 白色，默认 Atom size 从 60% 降至 50%，Bond thickness 从 11 降至 9。

- Rename the Atom colours palette from Sibyl to Default and soften its source colors by mixing in 10% white, consistently across atoms, element-colored bonds, legends and the color editor. Keep the original reference RGB table intact and accept the former palette name in saved presets and projects.
- Reduce default ball-and-stick atom size from 60% to 50% and bond thickness from 11 to 9; initialize sliders from the render options. Keep pure-white background and Glossy lighting.

[validation](docs/VALIDATION_v2.13.4.md)

## 2.13.3 — 2026-11-03

修复选中原子后测量输入框撑高底栏、挤压画布的问题；选中或清空选择时底栏与画布高度保持一致。默认背景统一为纯白 **#FFFFFF**。

- Keep the footer at its native editor height while measurement controls are hidden, so selecting two to four atoms or clearing selection never changes the canvas size. Derive the height from polished Qt control size hints for the active font/style.
- Use pure white (#FFFFFF) for new render options, the default Classic ball and stick preset, and the Light background button.

[validation](docs/VALIDATION_v2.13.3.md)

## 2.13.2 — 2026-11-03

修复全量验收中的 **PQR 元素误读/拒绝导入**和 **负网格计数 CUBE 无法打开**。 PQR 的元素和坐标采用一致的空白字段或固定列宽记录；CUBE 的原子、原点、体素和晶胞共享单位处理。

- Parse PQR ATOM/HETATM whitespace fields consistently, with optional chain IDs, tabs, large coordinates and a separate fixed-column fallback. Preserve elements and coordinates from the same record layout; report malformed atom rows instead of silently losing atoms. Distinguish common biomolecular atom labels from ion element names.
- Share normalized CUBE header input between legacy atom conversion and native field loading. Support all-negative Angstrom grid counts without rewriting source files; use consistent units for atoms, origin, voxel vectors and cell. Preserve scalar field values, signed atom-count labels, ASE field ordering and CASTEP boundary-plane handling.
- Retain valid CUBE geometry when the field is incomplete, too large or multi-channel, with an explicit availability note. Reject invalid/mixed grid units and propagate cancellation.
- Add PQR/CUBE regression and export/project checks; retain the full-acceptance independent assertions. See docs/VALIDATION_v2.13.2.md for current results and reproduction.

[fix details](docs/FIX_PQR_CUBE_v2.13.2_CN.md)

## 2.13.1 — 2026-11-03

修复增量验收中的 **全部五项问题**：斜晶胞 CIF 晶面坐标、高精度占据率往返、追加原子后的既有身份、重复 POSCAR 元素块，以及混占 CIF 的原始组分行顺序。

- Fix skew-cell CIF import at periodic faces: keep wrapped matching coordinates strictly inside the KD-tree's half-open [0,1) box when floating-point remainder rounds to 1. Do not move source Cartesian coordinates.
- Write native CIF site components with double-precision round-trip occupancies and coordinates. Preserve minority-component source row order, including interleaved rows, and append new component rows after existing ones. Keep strict overoccupancy validation and P1 symmetry-expanded export.
- Preserve surviving atom identities on paste; assign fresh identities to added atoms and supercell replicas. Geometry monitors and appearance synchronization use partial validated identity mappings so an unrelated deleted/replaced atom does not redirect an O–H monitor. Selected alignment/vibration/coordination atoms use the same mapping, while missing identities remain unavailable.
- Preserve original per-atom POSCAR block membership when reindexing; independent adjacent blocks of the same element stay separate. Carry block and CIF component-row metadata through projects, deletion, reindexing, clipboard operations and supercells.
- Retain the independent 11-case delta acceptance unchanged and add 31 regressions. Full Linux suite: 912 tests and 78 subtests pass with private examples enabled. Recheck production Qt/VTK defaults, axes, index dialogs, vacuum, footer and selection outlines.

[fix details](docs/FIX_DELTA_v2.13.1_CN.md) · [validation](docs/VALIDATION_v2.13.1.md)

## 2.13.0 — 2026-11-02

默认采用 **Sibyl.tcl 配色和 Glossy 光泽**；移除欢迎页的打开按钮及拖放提示；周期结构自动显示 **abc 晶矢**，非周期分子显示 XYZ。各结构导出格式均保留当前原子顺序，新增原子按添加顺序追加到末尾，旧转换接口也不再按元素排序。

- Default to Glossy lighting and the 111-element H–Rg palette extracted from the supplied Sibyl.tcl. Share palette lookup between native atom/bond rendering, legends and the color editor, including before a 3D view exists. Keep existing explicitly saved palettes, finishes and atom overrides.
- Remove the welcome-page Open a file / Ctrl+O button and the drop-a-structure hint. Retain File → Open, Ctrl+O, drag/drop, the parrot animation and shortcut table.
- Add an automatic axes basis, defaulting to true abc cell vectors for valid periodic structures and XYZ for molecules or invalid cells. Support explicit choices, per-document switching, native render exports and project persistence.
- Preserve current atom order in all five structure export formats and remove element sorting from both legacy POSCAR writers. Appended atoms retain addition order; explicit reindexing still defines the current row order. Preserve the prior selective-dynamics and species-block fixes.
- Add 18 regressions and update startup/style assertions for the requested UI/default changes. Full suite: 870 tests plus 78 subtests pass with private examples enabled. Verify actual startup, periodic/molecular axis switching, the supplied RGB values and export order with the production Qt/VTK path.

[guide](docs/FEATURES_v2.13.0_CN.md) · [validation](docs/VALIDATION_v2.13.0.md)

## 2.12.1 — 2026-11-02

修复独立验收中的 **A1–A3、B1–B4 全部七项问题**：等价晶位混占组分、POSCAR 固定标记及原子顺序、跨帧原子身份、真空未变及小真空回读、底部自动对齐和 Chemcraft 恒等操作 CIF 导入。

- Fix A1: rebuild CIF site probabilities from each input species' unique symmetry orbit, merging periodic aliases and equivalent orbit representatives without losing minority species or double-counting redundant representatives. Preserve compositions and probabilities on CIF round trips; reject conflicting equivalent occupancies.
- Fix A2: retain per-atom, per-axis VASP selective-dynamics flags through import, edits, reindexing and projects. Write both Direct and Cartesian POSCAR without sorting atoms, preserving consecutive species blocks and constraints.
- Fix A3: share validated source-identity mappings across geometry curves, appearance synchronization, display alignment, vibration selections, coordination trajectories and dipole fitting. New monitors capture their reference identities in projects; unmappable targets leave gaps or are skipped.
- Fix B1: confirming the existing vacuum is a true no-op, preserving energy, convergence and undo history. Keep the original precision when the dialog's rounded value is untouched.
- Fix B2: retain confirmed slab surface projections after changing vacuum, so an external gap smaller than internal layer spacings can be reopened and edited. Store this evidence in projects and recognize matching v2.12.0 vacuum records.
- Fix B3: queue summary alignment from actual window/status-bar layout events and apply pending layout geometry before calculating corrections.
- Fix B4: infer P1 when an unnamed CIF explicitly supplies only identity operations, including Chemcraft input without occupancy columns. Report unnamed nonidentity symmetry without guessing a group.
- Retain the independent 12-case acceptance assertions and add 34 regressions. Full Linux suite: 852 tests and 78 subtests pass with the supplied private examples; native window/click/dialog checks pass. Preserve the unfilled green dashed selection outline.

[fix details](docs/FIX_A1_B4_v2.12.1_CN.md) · [validation](docs/VALIDATION_v2.12.1.md)

## 2.12.0 — 2026-11-02

增加 **CIF 分数占据扇区显示、右击原子重编号/交换编号、保持笛卡尔坐标的 slab 真空层修改**；底部摘要左侧与 Coordinates 窗口对齐，选中原子改为绿色粗虚线外轮廓。

- Preserve CIF fractional and mixed-site occupancies through symmetry expansion, projects, Boundary, supercells, deletion and the native clipboard. Render species-proportional sphere sectors and a pale vacancy sector; include minority species in the legend, weighted composition and an unknown integer-electron parity. Preserve occupancy in CIF export and reject silent conversion to fully occupied calculation inputs.
- Add right-click atom index dialogs with 1-based move-to-index and two-selection index swap. Reorder coordinates, species, occupancies, force vectors, appearance and ordinary/hydrogen-bond indices together; preserve current-frame scalar results and atom order in POSCAR export. Empty-space right-click still clears selection; right-drag still rolls the camera.
- Detect slab outermost atomic planes and the largest periodic vacuum gap along the three cell normals. Adjust only the chosen cell vector's normal component, preserving all Cartesian coordinates, in-plane components and the other two cell vectors. Reject boundary-split slabs that cannot meet the fixed-coordinate requirement; support undo and clear invalidated calculation data.
- Dynamically align the bottom summary with the coordinate-pane left edge as the window layout changes.
- Replace the selected-atom wire mesh with an unfilled, thick green dashed camera-facing outline. Preserve atom colors and center labels; use explicit line gaps across native VTK backends.

[guide](docs/FEATURES_v2.12.0_CN.md) · [validation](docs/VALIDATION_v2.12.0.md)

## 2.11.0 — 2026-11-02

修复周期结构重设方向：**XYZ 对齐同步旋转原子与晶胞**。新增 **Edit → Reorient complete structure / crystal…**，可一次设置原点、X 提示和 Z 方向，自动生成正交旋转矩阵，也可粘贴分析脚本的行向量矩阵。支持最近周期像、体数据同步变换、撤销和项目保存。

- Fix periodic XYZ pair alignment: use the nearest periodic bond and rotate coordinates and lattice together. Keep the first atom fixed and co-rotate attached volume grids. Clearly label a/b/c as fixed-cell relative-geometry edits.
- Add origin/X/Z crystal reorientation with automatic proper rotation and Z-priority Gram–Schmidt axes matching the supplied rotation script. Accept a pasted row-vector rotation matrix, preview its values and reject collinear axes, scale, shear and reflection.
- Center periodic atom representatives around the selected origin with the complete lattice metric; remap frozen ordinary/hydrogen-bond image shifts, preserve scalar energies and convergence for rigidly equivalent periodic structures, and rotate available QE force vectors.
- Preserve reorientation matrices in frame information and projects, support undo of cell/coordinates/grids, process nearest-image centering with background progress, and preserve atom order in reoriented POSCAR exports.
- Add synthetic geometry, live GUI, project/export round-trip, supplied-script convention and actual POSCAR1/POSCAR2 compatibility regressions. Retain the v2.10.1 acceptance fixes.

[guide](docs/FEATURES_v2.11.0_CN.md) · [validation](docs/VALIDATION_v2.11.0.md)

## 2.10.1 — 2026-11-02

修复独立验收发现的 **A1–A3**：QE 优化状态必须有明确收敛证据；CP2K 晶胞扩展与原子重复分别读取；支持 `ANGLES` 别名及显式角度单位，保留斜晶胞。

- Fix A1: require explicit QE BFGS convergence, with failed/max-step/error exits taking priority within their PWSCF job. Keep normal process completion separate from optimization status and retain convergence only on matching final-coordinate reprints.
- Fix A2: independently read CP2K CELL and TOPOLOGY MULTIPLE_UNIT_CELL. Use the original unit cell for fractional coordinates and replica translations; preserve CP2K's X-fastest replica order, atom kinds and periodic axes. Explain mismatched repeated-topology input compatibility in the import note.
- Fix A3: support CP2K ANGLES as an ALPHA_BETA_GAMMA alias, including explicit degree/radian units. Report invalid angles instead of silently showing an orthogonal or degenerate cell.
- Retain the independent acceptance expectations as permanent regressions, correct the old QE success fixture, and extend coverage to failure priority, separate jobs, oblique cells, unequal repeats, invalid geometry and project round trips.

[fix details](docs/FIX_A1_A3_v2.10.1_CN.md) · [validation](docs/VALIDATION_v2.10.1.md)

## 2.10.0 — 2026-10-30

完善 **QE 输入、PWSCF 变胞优化、PHONON 频率及 matdyn 模式导入**。模式文件可明确关联参考结构和 alat，支持非 Γ 点的周期振动相位、箭头、GIF、q 点 CSV 和项目保存。

- Add dedicated QE PW input/results objects. Preserve parsed namelists, species, cells and source Rydberg energies; retain variable-cell ionic histories and distinct final SCF evaluations, Cartesian force summaries and confirmed geometry convergence. Keep ASE-compatible unit conversion and the existing linear trajectory API.
- Recognize PHONON stdout independently of PWSCF, including nonstandard suffixes; retain each q-point frequency set and its available reference without inventing displacement vectors. Keep frequency-only results usable when geometry is absent.
- Import normalized matdyn .modes as standalone results. Add explicit reference-structure, frame and alat association. Keep all q-point occurrences and complex vector components, without additional mass weighting. Do not merge PHONON and matdyn frequency sets.
- Animate phonons with Bloch phase across Boundary cells; support polarization arrows, participation analysis, q-labeled frequency trees/CSV, project persistence and native PNG/GIF export. Keep reference coordinates and source results intact.
- Add synthetic and supplied-file coverage. Do not redistribute the four private input files; include their acceptance record and production rendering.

[QE guide](docs/FEATURES_v2.10.0_CN.md) · [validation](docs/VALIDATION_v2.10.0.md)

## 2.9.0 — 2026-10-30

默认使用 **GaussView 风格配色（取自 Chemcraft 兼容预设）**、**Chemcraft 普通键距离上限**及 **VESTA space-filling 半径**。Space-filling 默认 Atomic、100%，可切换 Ionic / van der Waals，尺寸独立保存。配色尚未取得 Gaussian 原始完整 RGB 表；成键采用默认表提取的距离，不承诺复现其他软件的完整算法。

- Use Chemcraft's built-in GaussView-style compatibility palette as the new default, with its actual source named in the UI. A Gaussian-authored full RGB table remains unavailable; no claim of exact native GaussView matching is made.
- Use ordinary-bond upper limits extracted from Chemcraft b816bt, excluding hydrogen-bond records. Share pair lookup across finite and periodic connectivity, fragment operations and edits. Default distance multiplier is 1.00; explicit pair rules, manual bonds and frozen edited graphs remain authoritative. Offer the earlier covalent-radius model separately.
- Use VESTA 3.5.8 Atomic radii for space filling, with Ionic and van der Waals alternatives. Space-filling size is independent of ball-and-stick size and defaults to 100%. Store these choices per document and in projects/presets; restore legacy projects with their previous covalent-radius search model.
- Document numeric provenance, coverage and the limits of compatibility. Distribute extracted numeric facts and a reproducible extractor, without upstream application binaries or configuration files.

[2.9.0 guide](docs/FEATURES_v2.9.0_CN.md) · [validation](docs/VALIDATION_v2.9.0.md) · [配色、成键及半径的参数来源](docs/display_reference_data.md)

## 2.8.0 — 2026-10-30

增加 **CP2K/Molden `.mol` 振动导入**，支持模式选择、动画、箭头及 GIF，保留固定原子的零位移。 **View → Atom legend…** 改为独立图例窗口，画布仅显示各元素样本和符号，可单独保存 PNG。

- Import independent CP2K-compatible Molden vibration files by content, preserving reference coordinate units, mode numbers/frequencies and frozen zero vectors. Integrate animation, mode arrows, selection participation, GIF and project persistence. Keep standard MDL .mol reading separate.
- Replace the main-canvas atom-legend overlay with a nonmodal window containing only unbonded element samples and labels; add independent PNG export and explicit refresh from the current structure. Legacy project flags remain readable without restoring the overlay.
- Preserve source units for optional Molden INT values and use the actual intensity unit in frequency tooltips.

[2.8.0 guide](docs/FEATURES_v2.8.0_CN.md) · [validation](docs/VALIDATION_v2.8.0.md)

## 2.7.0 — 2026-10-30

检查并改进各类多步输出读取，修复 CP2K、xTB、Quantum ESPRESSO、NWChem 的重复扫描； 处理/导出/项目操作增加延迟进度框。优化成功的对应帧显示 **converged**， **View → Atom legend** 可添加随 PNG/GIF 导出的元素球图例，欢迎页并列显示两个邮箱。

- Remove repeated history scans in CP2K, xTB, Quantum ESPRESSO and geometry-free NWChem module continuations; retain complete frame and scientific records. Add parsing/cancellation phases for other supported outputs and streaming trajectories.
- Add delayed progress for project I/O, structure/CSV/PNG export, spectra, geometry curves, mode/coordination analysis and large view/table updates. Keep Qt/VTK work on the GUI thread with cooperative checkpoints.
- Show converged on identified successful geometry optimization frames; clear stale status after structural edits and retain it through undo.
- Add View → Atom legend: one unbonded visible sample per element, fixed camera overlay, PNG/GIF support and per-document/project persistence.
- List both contact emails side by side on the welcome page. Document CP2K primary/replica logs and Molden vibration output organization.

[2.7.0 guide](docs/FEATURES_v2.7.0_CN.md) · [validation](docs/VALIDATION_v2.7.0.md)

## 2.6.0 — 2026-10-30

Bond cutoff 扩大到 0.10–5.00，支持精确输入并立即重新识别自动键； 底部信息行下移，扩大画布。选中 2/3/4 个原子后，可直接输入键长/键角/二面角， 按 Enter 或 Set 移动最后选中原子所在的末端片段，支持撤销；环或周期网络限制移动时弹窗提示。 ORCA 优化输出加速解析，输出文件后台加载，长加载弹窗显示阶段、阶段百分比、耗时并支持取消。

- Bond cutoff now supports 0.10–5.00 with a precise numeric field. Explicit changes rebuild automatic/frozen bonds for the active document, retaining manual ordinary/dashed overrides and element-pair rules.
- Move the atom/composition/contact summary and selection measurement into one bottom status strip; use the freed space for the structure canvas.
- Edit selected distances, angles and dihedrals numerically (Enter/Set). Move the last-selected terminal bonded fragment rigidly; reject rings, extra fixed-atom paths and infinite periodic networks without partial edits. Preserve image shifts and support undo; clear stale non-rigid geometry energies.
- Parse scientific outputs in a cancellable worker even below 4 MiB. Long imports display phase, phase percentage and elapsed time; structure/view attachment stays on the GUI thread.
- Speed up long ORCA optimizations with gated metadata matching, block coordinate conversion, indexed source-line/geometry lookup, optional-section checks and shared load-local source text. Retain all frames and original scientific values.

[2.6.0 guide](docs/FEATURES_v2.6.0_CN.md) · [validation](docs/VALIDATION_v2.6.0.md)

## 2.5.0 — 2026-10-30

取消程序固定帧数上限，并优化长轨迹加载：CP2K/普通 XYZ、XDATCAR 逐帧读取， 同一次导入的分析共用已解码输出；目录树按需展开，大文件后台解析并支持取消。 保留全部结构帧和能量记录。

- Remove the default 750-frame cap across native CP2K, VASP, Gaussian/ORCA,
  xTB, SIESTA and generic multi-image imports. Also remove cumulative xTB/NEB
  trajectory-record limits. Explicit caller-supplied API limits remain optional;
  the application supplies none. All loaded frames remain editable in memory.
- Stream native CP2K/plain XYZ and XDATCAR blocks with array-based numeric
  conversion. Preserve variable cells, Fortran exponents, incomplete-tail
  handling, source record mapping and extended-XYZ metadata through ASE.
- Share decoded output lines only within one load; skip absent optional
  property sections. Scan VASP tags/species once and avoid repeated regex work
  on irrelevant CP2K SCF rows. Keep VASP E0-only and CP2K FORCE_EVAL policies.
- Replace per-leaf copies/hashes of whole frame sequences with shared indexes.
  Build long frame/energy tree entries on expansion in 256-record pages,
  retaining numeric navigation, playback, stage/NEB sequences and projects.
- Parse scientific files of 4 MiB or larger in a cancellable background worker.
  GUI/VTK updates remain on the main thread; queued files retain their order,
  and cancelled imports do not attach partial documents.
- Add 22 long-file regressions. Full Linux suite: 605 tests plus 78 subtests
  pass. Eight supplied CP2K/VASP documents remain value-for-value identical to
  2.4.0. Include reproducible synthetic parser benchmarks and validation notes.

[long-file guide](docs/FEATURES_v2.5.0_CN.md) · [validation and benchmarks](docs/VALIDATION_v2.5.0.md)

## 2.4.0 — 2026-10-30

增加 **CP2K 独立读取**：输入/文本 restart、标准输出和 XYZ 轨迹均可单独打开。 支持已有结构、能量、优化收敛指标、按 k 点/自旋分组的轨道，以及 TDDFPT 跃迁、光谱和 CSV。 不搜索配套文件；没有结构或能量时保留实际可用的数据。

- Add independent CP2K input/text-restart, stdout and standard XYZ readers.
  Read inline coordinates, cells/units/periodicity, KIND aliases, charge and
  multiplicity. Preserve settings-only inputs when coordinates are external
  or unsupported; do not open referenced files or evaluate executable input.
- Retain all printed FORCE_EVAL energies and optimization gradients/steps with
  their thresholds and source units. Link only available coordinates; keep
  geometry-free energy/gradient records and structure-only records. Separate
  concatenated CP2K runs. Do not infer trajectory cells from adjacent files.
- Convert standard CP2K XYZ E comments from Hartree to internal eV, preserving
  printed step/time metadata. Keep the last printed MO table per SCF evaluation,
  with separate k-point/spin channels rather than merged orbital indices.
- Add final TDDFPT energies, oscillator strengths, printed moment form, optional
  excitation amplitudes and raw k-point auxiliary fields. Component magnitudes
  from KERNEL NONE output remain magnitudes: no invented arrows, phase or
  excitation coefficients. Preserve unknown/Berry forms as labeled source data.
- Add CP2K record curves and CSV, source-aware transition tables/CSV, results-only
  spectrum/export controls and portable project serialization for CP2K results.
- Add synthetic fixtures/project, inspected Qt previews and 32 CP2K regressions.
  Full Linux validation: 583 tests and 78 subtests passed. The five supplied
  files pass isolated single-file loads, GUI/CSV and project round-trip checks.
  VASP E0-only behavior and prior features remain covered.

[CP2K guide](docs/FEATURES_v2.4.0_CP2K_CN.md) · [validation record](docs/VALIDATION_v2.4.0.md)

## 2.3.1 — 2026-10-30

VASP 结果、曲线和 CSV **只使用 E0**，即 OSZICAR 的 `E0=`、OUTCAR 的 `energy(sigma->0)`。没有 E0 时留空。

- Use only VASP E0: OSZICAR E0= and OUTCAR energy(sigma->0). Remove fallback
  to TOTEN/F or energy without entropy, and remove energy-kind selection.
- Label result pages, overview columns and curves as E0. Curve CSV contains one
  energy column, energy_E0_eV, alongside frame/source-line and force fields.
  Missing E0 remains blank in CSV and a gap in the plotted curve. A structure
  without E0 keeps its geometry and any available force records.
- Open old .lele snapshots using the same E0-only policy, including saved mode
  references. Preserve energies already cleared by geometry editing. Retain
  original output text and source metadata independently of displayed energy.
- Add 9 E0 regressions; full Linux validation: 551 tests and 78 subtests passed.
  See docs/VASP_E0_v2.3.1_CN.md for actual-file and project-roundtrip checks.

## 2.3.0 — 2026-10-29

加入三个最高优先级功能：**按元素对设置成键/配位规则**、 **多面体定量分析与轨迹曲线/CSV**、**.lele 项目保存与恢复**。 入口分别为 Crystal → Pair rules、Analysis → Coordination / polyhedron analysis…、 File → Save/Open project…。项目保留已加载的结构与计算结果、编辑后的键、逐原子样式、 各文件视角、HKL 切面和显示参数。

- Add Crystal → Pair rules: element-specific minimum/maximum distances,
  wildcards, enabled rows, separate ordinary-bond and directed coordination
  controls, and an optional only-listed mode. More specific rows win, then the
  last row. Explicit Apply rebuilds all document frames, keeps manual bond
  overrides and supports undo; geometry editing still preserves frozen bonds.
- Add coordination/polyhedron analysis: CN, periodic ligand distances/image
  shifts, hull volume, Baur distortion, Hoppe ECoN, and applicable tetrahedral/
  octahedral quadratic elongation and angle variance. Export summaries, ligands
  and frame-linked trajectory curves to CSV, retaining zero coordination and
  gaps when atom sequences or metric applicability differ.
- Add portable .lele project snapshots with all loaded structures and parsed
  scientific results, edited topology, atom appearance, per-document display
  options/cameras, cuts, alignment, geometry parameters and paused active modes.
  Retain source-text previews up to 180 KB. Source files are optional on restore.
  Open appends restored documents, preserving work already in the session.
- Use atomic writes and a fixed data-class registry with JSON and numeric NPY
  arrays; loading does not use pickle or extract files. Validate before updating
  the open session. Preserve existing PNG shortcuts.
- Fix transient out-of-range frame access during settings synchronization when
  changing from a long trajectory to a shorter file; keep the text preview in
  sync for programmatic document changes.
- Add a portable two-document example, native/Qt previews and 45 regressions.
  Full Linux validation: 542 tests and 78 subtests passed. Actual VASP snapshot
  checks preserve all coordinates, cells, energies and modes without source
  files; the synthetic saved/restored native view is pixel-identical.

[2.3.0 guide](docs/FEATURES_v2.3.0_CN.md) · [validation record](docs/VALIDATION_v2.3.0.md)

## 2.2.0 — 2026-10-29

增加 **(hkl) 晶面显示裁切**和 **Polyhedral 配位多面体样式**。 通过 **Crystal → HKL planes** 设置晶面、位置、保留方向和薄层厚度；支持多个切面、 斜晶胞和沿晶面法向观察。通过 **Crystal → Polyhedra** 设置中心/配位元素、距离、 透明度和棱线，补全跨晶胞配位，并保留各文件自己的显示设置。

- Add Crystal → HKL planes with Miller indices, signed offsets in d or Å,
  below/above cuts, finite-thickness slabs, multiple-plane intersections,
  translucent plane faces/edges, automatic centering and normal camera views.
- Use reciprocal-cell normals for skew lattices. Clip atom glyphs, ordinary
  bonds, polyhedra and scalar isosurfaces in the same display coordinates,
  including Boundary copies and trajectory alignment. Filter labels and atom
  selection by the retained center region. Source coordinates/exports stay intact.
- Add Polyhedral style and a VESTA-inspired preset. Search explicit central/
  ligand elements using covalent radii or a distance range; complete periodic
  ligand shells and repeat center polyhedra with Boundary. Render translucent
  hull faces, true face edges and optional corner atoms with original atom IDs.
- Render planar ligand shells as polygons; omit collinear shells. Exclude
  coplanar triangulation diagonals from edges. Use center atom colours and retain
  ordinary manual/frozen bonds in every style, independently of coordination rules.
- Keep crystal controls Qt-only until preload. Restore cut and polyhedron
  settings per open document, and include them in PNG/GIF rendering.
- Add synthetic SrTiO3 examples, native preview images and 32 crystal regressions.
  Full Linux validation: 497 tests and 78 subtests passed. See the validation
  report for real-input checks and Windows acceptance limitations.

[2.2.0 guide](docs/FEATURES_v2.2.0_CN.md) · [validation record](docs/VALIDATION_v2.2.0.md)

## 2.1.0 — 2026-10-29

增加 **VASP OUTCAR / XDATCAR / OSZICAR** 独立读取，支持优化/MD 轨迹、离子步能量、力曲线、振动模式与虚频动画（自 v2.3.1 起只使用 E0）。只有能量时显示结果页，只有结构时 保留轨迹浏览，无需同目录其他文件。

- Add standalone VASP OUTCAR, XDATCAR and OSZICAR readers, including renamed
  OUTCAR_opt/OUTCAR_freq files. Do not read neighbouring calculation files.
- Retain ionic structures, cells, species blocks (including repeated elements),
  Cartesian force metrics, σ→0 energies, TOTEN and energies without entropy.
  Exclude electronic SCF summaries from ionic records and preserve source lines.
- Open energy-only output in the results page, preserve geometry-only navigation,
  and never match missing coordinates/energies to unrelated records.
- Read real and imaginary VASP modes with their printed reference geometry.
  Convert dynamical-matrix eigenvectors using POMASS; prefer the already divided
  table when printed. Distinguish finite-displacement structures from optimization.
- Add an energy-definition selector and CSV export retaining all three VASP
  energy values, source records and optional geometry links. Support variable-cell
  XDATCAR headers and retain complete frames from partially written files.
- Add 28 dedicated parser/UI regressions and synthetic example files. Validate
  the three supplied real files against ASE independently; see validation notes.

[2.1.0 guide](docs/FEATURES_v2.1.0_CN.md) · [validation record](docs/VALIDATION_v2.1.0.md)

## 2.0.3 — 2026-10-29

增加 **Ctrl+H**，在两个选中原子之间添加/移除虚线氢键，支持撤销； Ctrl+B 继续操作普通键。切换已打开的文件时，各文件保留自己的视角、缩放、平移、 投影、配色及其他显示设置；频率和纯能量节点也使用同一恢复流程。

- Add Ctrl+H and Edit-page/menu controls for an undoable dashed hydrogen bond
  between two selected atoms. Keep Ctrl+B and covalent fragment connectivity
  independent. Manual links work without enabling automatic candidates.
- Avoid duplicate automatic/manual lines and allow Ctrl+H to suppress an
  existing automatic candidate. Preserve manual image paths during edits,
  deletion, copy/paste, Boundary display, alignment and supercell construction.
- Retain an independent camera and full RenderOptions for each open document.
  Restore view direction, zoom, pan, projection, colours, labels, axes, fields,
  dipoles, Boundary and preset/custom state together with their controls.
- Route geometry, frequency, result-navigation and energy-only entries through
  the same document activation. Fit a new file once; returning to a file no
  longer resets its saved camera. Settings remain session-local.
- Add 16 regressions covering manual bonds and multi-document round trips.
  Full Linux regression: 437 tests and 72 subtests passed. Deliver the full
  source archive; Windows EXE requires a rebuild.

[2.0.3 guide](docs/FEATURES_v2.0.3_CN.md) · [validation record](docs/VALIDATION_v2.0.3.md)

## 2.0.2 — 2026-10-29

修复强倾斜、非约化晶胞的短接触和最近周期像搜索；轨迹显示对齐时， 晶胞边框与 Boundary 原子、边框一起旋转和平移；删除 Windows 启动错误中的旧版本号。 Alt＋鼠标中键拖动片段、坐标编辑等操作保持原有键连接。Ctrl+B 明确成键/断键； 需要重新推断时使用 `Edit → Rebuild bonds from distances`，支持 Ctrl+Z。

- Search non-reduced periodic lattices using Minkowski reduction and a
  cutoff-derived neighbor list; map image shifts back to the input basis.
  Correct minimum images for fully and partially periodic structures.
- Apply display rotation and translation to unit-cell outlines, Boundary
  copies and fragment preview geometry without changing source coordinates.
- Remove the obsolete hardcoded version from the Windows Python error.
- Capture connectivity before geometry edits. Fragment gestures, coordinate
  changes, deletion, copy/paste and supercell construction preserve the graph;
  undo restores it. Periodic bonds retain their original image connection.
- Keep Ctrl+B as an explicit bond command and add Edit → Rebuild bonds from
  distances for an undoable rebuild with the current cutoff and manual overrides.
- Retain the seven independent acceptance probes and add 23 regressions.
  Full Linux regression: 421 tests and 72 subtests passed. The unchanged
  external acceptance probes also passed (7/7). No Windows EXE was built.

[2.0.2 guide](docs/FEATURES_v2.0.2_CN.md) · [validation record](docs/VALIDATION_v2.0.2.md)

## 2.0.1 — 2026-10-29

底部信息简化为 Composition、electrons even/odd 等短字段，省略冒号； Short contacts 只显示数量，点击可查看原子对、距离及周期像平移。 周期性体系的 Results / info 增加晶胞体积。

- Compact the footer: Composition for periodic cells, electrons even/odd,
  concise atom/formula fields and measurements without colons. Keep detailed
  charge/parity provenance in the footer tooltip.
- Show only the short-contact count in a clickable footer control. Its dialog
  lists the source atom pairs, distances and periodic image translations,
  with a clearly identified geometry snapshot and an explicit empty state.
- Share one distinct-pair minimum-image contact enumeration between counts
  and details; image translations refer to the original coordinates.
- Add periodic cell volume as the absolute determinant in Å³ to Results / info,
  updating with frame changes while omitting it for nonperiodic structures.
- Retain all 2.0.0 features. Windows EXE still requires a Windows rebuild.

[2.0.1 guide](docs/FEATURES_v2.0.1_CN.md)

## 2.0.0 — 2026-10-28

按选中原子位移占比筛选振动、仅显示虚频、静态位移箭头； 增加多参数几何曲线、平面/向量参数、曲线点击跳帧、统计和 CSV； 增加全原子或指定骨架的轨迹显示对齐，保留原始坐标，PNG/GIF 跟随显示。 xTB 没有坐标的每一步能量均显示在左侧树中，可逐步点击查看，无需结构文件。 入口位于 Files 页和 Analysis 菜单。

- Find normal modes by selected atoms' squared Cartesian displacement share;
  filter imaginary modes and share thresholds, play modes, export shown rows,
  and render static displacement arrows with selected-atom and length controls.
- Monitor multiple distances, angles and dihedrals over stage-local trajectories,
  NEB paths or image histories. Add plane/vector angles and point-to-plane/line
  distances, explicit periodic images, dihedral unwrapping, statistics and CSV.
  Curve points navigate to the correct source frame and preserve the sequence.
- Align trajectory display to a reference using all atoms or a selected scaffold.
  Apply translation and proper rotation without changing source coordinates,
  cells, energies or structure exports; PNG and GIF reflect the aligned view.
  Disable alignment before coordinate/bond edits; incompatible atom orders are
  displayed unchanged with an explanatory note.
- Show every coordinate-free xTB energy record in the Files tree. Selecting a
  record shows its cycle, energy in Eh/eV/kcal/mol and source line; it never
  substitutes an unrelated final structure or a placeholder frame.
- Retain all previously delivered Gaussian/ORCA/xTB and NEB/GOAT/SOC features.
  Add 33 selection-analysis regressions. Full Linux regression: 380 tests and
  72 subtests passed; a real 175-cycle energy-only xTB file was checked in UI.

[2.0.0 guide](docs/FEATURES_v2.0.0_CN.md)

## 1.11.1 — 2026-10-28

结构与能量独立读取，文件不必配套。纯能量文件显示结果和曲线，不显示 结构视图或虚拟帧；纯结构文件可正常浏览、播放，不显示能量，也不提供空曲线。

- Load xTB energies/orbitals independently of coordinates. Energy-only documents
  have no placeholder geometry; show a results/source page with available data.
- Keep coordinate-only files usable without energy. Disable empty curve entries
  while retaining structure navigation, playback and exports.
- Stop requiring geometry for calculation overviews and file status. Safely
  handle frame shortcuts and switching between data-only and structure files.
- Keep verified trajectory association optional; do not fill missing structures
  from an unrelated or unanchored neighboring file.
- Add ten independent-data regressions and examples. Full regression:
  347 tests and 72 subtests passed.

[1.11.1 guide](docs/FEATURES_v1.11.1_CN.md)

## 1.11.0 — 2026-10-28

增加 xTB/g-xTB 的几何优化、总能量及 HOMO/LUMO 支持。 主输出可核对并关联同目录的优化轨迹；能量曲线支持跳转到已有结构、单位切换和 CSV。 分数占据优先采用原文 HOMO/LUMO 标记，alpha/beta 分别显示。

- Read xTB/g-xTB optimization stdout, explicit final structures and Xmol
  optimization trajectories, including Hartree energies in XYZ comments.
- Match same-directory trajectory companions by the full cycle-energy sequence,
  atom order and final coordinates; keep unmatched cycles energy-only.
- Add xTB energy curves with cycle navigation, source energy units and complete
  CSV export, including cycles without coordinates. Keep ANC/gradient norms
  separate from Cartesian maximum/RMS convergence metrics.
- Preserve explicit HOMO/LUMO labels for fractional occupations, blank virtual
  occupations, original MO numbers, and separate alpha/beta tables and gaps.
  Retain the printed summary gap independently, merge repeated final tables,
  and continue opening orbitals only on request.
- Distinguish optimization convergence, Finished run and explicit normal
  termination; preserve precise final single-point and trajectory energy values.
- Verify all three supplied real xTB files and add 26 regressions plus synthetic
  examples and Qt previews. Full regression: 337 tests and 72 subtests passed.

[1.11.0 guide](docs/FEATURES_v1.11.0_CN.md)

## 1.10.0 — 2026-10-28

NEB/NEB-TS 按始末态预优化、NEB、TS 精修和 Hessian/频率阶段显示， 支持完整路径快照、固定 image 的优化历史及对应序列播放/GIF。 新增 GOAT 构象能量、布居、温度重算和 RMSD 分析，以及 SOC 复数耦合、混合态组成与修正吸收。 入口为 Files 页的 **NEB / GOAT / SOC…** 或 Analysis 菜单。

- Separate ORCA reactant/product preoptimization, NEB, TS refinement and final
  frequency stages; retain each stage's convergence and prevent later energies
  from overwriting an endpoint. Ignore warning banners when collecting input.
- Distinguish exact/model/read Hessians and optimizer updates, preserve parent
  cycles, and exclude numerical displacement coordinates/energies/properties
  from optimization histories. Separate optimization modes from final checks.
- Add source-labelled NEB path snapshots, fixed-image histories, force curves,
  CI and refined-TS access, energy units and CSV export. Match MEP XYZ to printed
  energy vectors and leave unmatched snapshots energy-only.
- Group result sequences in Files; navigation, playback and GIF export follow
  the current stage, path, image history or conformer ensemble.
- Add GOAT final-ensemble and XYZ reading, printed populations/degeneracies,
  Boltzmann populations at a chosen temperature, aligned same-order RMSD,
  conformer navigation and CSV export, including energy-only results.
- Add common TDDFT complex triplet/singlet SOC and printed sparse scalar SOC,
  component heatmaps, mixed-state coefficients, SOC-corrected absorption and
  CSV export while preserving separate spin-free TD/TDA results.
- Add synthetic examples, twenty workflow regressions and Qt screenshots;
  verify actual NEB/Hessian attachments and thirteen public ORCA outputs.

[1.10.0 guide](docs/FEATURES_v1.10.0_CN.md)

## 1.9.0 — 2026-10-28

HOMO/LUMO 改为点击 Files 页按钮或 Analysis 菜单后打开；底部 Short contacts 右侧同步显示选中原子的键长、键角或二面角。补齐常见 ORCA 4/5/6 输出的计算总览、 优化/扫描曲线、轨道能量、振动动画、IR/Raman/UV-Vis、偶极与跃迁组成。

- Open HOMO/LUMO only from the Files-page button or Analysis menu.
- Repeat the current selection measurement beside Short contacts, updating on
  selection, frame changes and coordinate edits.
- Extend common ORCA 4/5/6 outputs to isolated geometry histories, job and
  compound-job metadata, occupations, SCF cycles, spin and frequency summaries,
  convergence and clickable frame mapping.
- Read ORCA Cartesian normal modes, imaginary frequencies, IR/Raman tables and
  distinguish legacy printed T² from integrated km/mol intensities.
- Read permanent/state dipoles and classic/new electronic, velocity and magnetic
  transition-moment tables; retain signed contributions and printed weights.
- Match spin-local transition labels to global STATE numbers without duplicating
  triplets; preserve original labels in CSV and prevent cross-job property reuse.
- Accept UTF-8 BOM and Windows UTF-16 redirected text output.

[v1.9.0 使用与 ORCA 支持说明](docs/FEATURES_v1.9.0_CN.md)

## 1.8.0 — 2026-10-28

保留框选累加、逐次撤销、原生高对比外框、Ctrl+A、同文件跨帧显示同步、计算总览及 主要跃迁组成，键比原子更快变透明。

- Accumulate successive box selections and undo each completed addition through
  the shared selection/edit history; add Ctrl+A without overriding text editors.
- Draw a high-contrast unfilled dashed outline in a native VTK overlay layer.
- Fade connected bonds faster than atom spheres using squared endpoint opacity.
- Propagate atom colour, opacity, visibility and labels to compatible geometry
  frames and vibration references in the same file. Undo restores display maps
  independently of positions/bonds and remains valid after geometry undo.
- Read Gaussian/ORCA calculation segments, printed orbital occupations/energies
  and maximum/RMS convergence. Keep Gaussian charge/multiplicity per segment,
  including identical geometries belonging to different charge states (A1).
- Open molecular HOMO/LUMO summaries automatically when printed orbital tables
  are found; default to eV and show alpha/beta channels separately.
- Add calculation overviews and energy/convergence plots with point-to-frame
  navigation, scan-endpoint filtering, source thresholds and CSV export.
- Read signed excited-state orbital contributions, preserve forward/backward
  rows and printed ORCA weights, and expose them in tables and CSVs.
- Add synthetic Gaussian/ORCA examples and actual Qt/VTK rendering previews.

## 1.7.2 — 2026-10-28

左下角 XYZ/abc 字母持续正对镜头，箭头粗细固定，偶极 Scale 可手动输入， 激发态列表清理未知对称性占位符；**Ctrl+Shift+B** 切换无填充虚线框选。 Boundary 现在复制完整晶胞及原子，保留各单胞尺寸并显示内部边框。

- Render bottom-left XYZ/abc letters directly as billboards in the overlay
  renderer, keeping their anchors and marker size stable during camera gestures.
- Hide Gaussian's unknown-symmetry `-?Sym` placeholder in the excited-state
  table while retaining real symmetry labels and the original CSV description.
- Let dipole Scale accept typed decimals; commit on Enter or focus loss and
  preserve unfinished input during redraws.
- Keep axis and dipole shaft/head widths fixed when vector lengths change.
- Replace platform-dependent filled rubber bands with masked, transparent,
  dashed selection outlines; add Ctrl+Shift+B to toggle and Esc to exit.
- Verify atom/bond transparency linkage through the real appearance editor,
  undo and Boundary copies; clarify the lower-endpoint opacity rule.
- Change Boundary from fractional clipping to full-cell integer ranges. Repeat
  every atom in each original-sized cell and draw the internal unit-cell edges.
  Keep source coordinates, cell vectors and source IDs unchanged.
- Add GUI, native-rendering and geometry regressions plus synthetic previews.

[display-controls guide](docs/DISPLAY_UPDATES_v1.7.2_CN.md)

## 1.7.1 — 2026-10-28

修复跨晶胞片段选择：**Ctrl+G** 需要相邻晶胞时自动建立可撤销的真实超胞，Coordinates、Atoms 和原子编号同步增加，**Ctrl+I** 对扩胞后的全部原子反选。**Ctrl+Z** 可恢复扩胞前的结构与体数据。

- Make Ctrl+G build a real, undoable supercell when completing a finite
  cross-boundary fragment. Map each selected periodic image to its own atom ID.
- Refresh Coordinates, the Atoms panel and atom counts from that expanded
  frame; Ctrl+I, coordinate edits, copy/paste, deletion and export use its atoms.
- Reuse the existing supercell rules for skew cells, partial periodicity,
  per-atom display settings, manual bonds, charge, energy and volume detachment.
- Preserve the original frame, selection and attached field for Ctrl+Z; leave
  other trajectory frames unchanged and avoid repeating an already complete
  fragment. Selection wholly inside a cell still creates no geometry edit.
- Update the coordinate-table test double for the shared element-list refresh
  introduced by the previous A2/A3 repair.

[fragment-selection fix](docs/FIX_PERIODIC_FRAGMENT_v1.7.1_CN.md)

## 1.7.0 — 2026-10-27

在真实扩胞功能之上重新实现高质量 GIF、保存目录、轴标签朝向、光谱、偶极、成键、复制粘贴与 Boundary 等功能。

- Reimplement the missing 1.4/1.5 feature set while retaining 1.6.0 real supercells.
- Restore 2× supersampling/Lanczos, shared sampled palettes and optional GIF
  dithering; preserve atomic cancellation, timing and live camera/playback.
- Restore source-directory save defaults and camera-facing corner-axis letters.
- Preserve ASE eV internally; display molecular-program energy in kcal/mol and
  periodic-program energy in eV. Clear stale energy after nonrigid edits.
- Restore Gaussian Raman activities, IR/Raman/UV-Vis simulated spectra and raw
  transition tables, distinct from sampled spectrum curves.
- Read length/velocity/magnetic transition tables separately; distinguish SCF,
  excited permanent and electric transition moments. Add typed arrows, PNGs,
  dipole CSVs and transition CSVs with units and oscillator-strength checks.
- Filter occluded long automatic bonds while preserving rings and manual links.
- Restore cross-file atom clipboard/paste placement, native rectangle selection,
  disclosure-only atom-group expansion and fractional Boundary displays with
  source atom IDs, styles, periodic bonds, picking, PNG and GIF exports.
- Add synthetic examples, native rendering evidence and regressions. Source is
  a verified reimplementation, not a byte-for-byte recovery of the lost files.
- Post-acceptance repair: atom paste now detaches stale volumetric fields while
  preserving them for Undo, and immediately refreshes the Edit-page element
  selector when pasted atoms introduce a new element.

[restored feature guide](docs/RESTORED_FEATURES_v1.7.0_CN.md) · [supercell guide](docs/SUPERCELL_CN.md)

## 1.6.0 — 2026-10-27 (rebuild from 1.3.0)

- Rebuild from the available 1.3.0 source after the intervening local sources
  became unavailable. The missing 1.4.0/1.5.0 changes are not included.
- Add Edit → Build supercell: repeat the current periodic frame along a/b/c,
  enlarge the actual unit cell, and export the resulting full structure.
- Support skew lattices, optional periodic coordinate wrapping and partial PBC.
  Preview the new atom count and cap interactive supercells at 50,000 atoms.
- Preserve atom colours, visibility, transparency, labels and POSCAR block
  metadata. Map manual bonds to their actual periodic image paths.
- Scale known cell charge; clear source energy and unestablished multiplicity.
  Detach the old volume and restore it with coordinates and metadata on Undo.
- Keep other trajectory frames unchanged. Add backend, export round-trip,
  native-rendering and Qt workflow checks plus a Chinese supercell guide.

## 1.3.0 — 2026-10-27

- Add File → Export animation GIF for geometry/optimization trajectories and
  the selected vibration mode, using the current camera, colours and labels.
- Let users set output width, FPS and looping; retain the canvas aspect ratio.
  Add trajectory frame range, stride and forward/backward playback, and
  vibration amplitude and cycle duration controls.
- Render one complete vibration cycle without a repeated final pose. Avoid
  repeated trajectory endpoints during forward/backward looping and distribute
  GIF timing ticks to avoid accumulated frame-rate rounding errors.
- Use a separate native offscreen canvas and stream frames to a temporary file.
  Show cancellable progress, preserve existing files on cancellation/error,
  and restore live playback without changing source coordinates or camera.
- Add Pillow as an explicit dependency, preload its encoder after first paint,
  and verify updated dependencies in Windows launch/build helpers.
- Add decoded-image/native-rendering regressions, options-dialog checks and
  synthetic export previews. Advance application and package to 1.3.0.

## 1.2.0 — 2026-10-27

- Read Gaussian harmonic frequencies, IR intensities, reduced masses, force
  constants and Cartesian normal-mode vectors alongside the geometry history.
  Associate each frequency calculation with its own printed orientation,
  including combined Opt+Freq and multiple Link1 jobs.
- Group geometry/optimization frames and frequency calculations in the Files
  tree. List every printed mode, mark imaginary frequencies, and start a
  reversible vibration preview when a mode is selected with mouse or keyboard.
- Add pause/resume, stop/reset, amplitude and visual speed controls. Retain
  reference connectivity, camera orientation and source coordinates during
  animation; show reference coordinates in the table and structure exports.
- Keep incomplete modes visible with animation disabled. Separate reference
  geometry from editable optimization frames, and stop vibration on frame/file
  changes or application closing. Retain per-atom appearance and undo.
- Add a synthetic Opt+Freq example, an animation preview and regression tests.
  Update application, welcome page, package and launcher version to 1.2.0.

## 1.1.1 — 2026-10-27

- Accept precise decimal and scientific-notation isovalues with up to 12
  decimal places, instead of the four-decimal input limit. Allow values down
  to 1e-12 while retaining the existing arrow step.
- Commit typed values on Enter, Apply or focus loss so intermediate digits do
  not trigger isosurface reconstruction. Keep keyboard/clipboard editing and
  the up/down controls available, with an input hint beside the field.
- Update the application, welcome page, package and launcher notices to 1.1.1.

## 1.1.0 — 2026-10-27

- Advance application, welcome page, package metadata and launcher notices to
  1.1.0 for the feature release containing the following UI/startup changes.

- Add an Atoms sidebar tab with element groups, original atom indices, per-atom
  visibility, colour, transparency, label modes and custom text. Support applying
  settings to multiple atoms or an entire element group.
- Keep display overrides on their owning frame, preserve them through undo and
  reindex them when atoms are deleted. Apply them consistently to periodic
  replicas, bond/hydrogen-bond drawing, labels, highlights and mouse picking.
- Split the lower inspector into two resizable equal columns. Keep compact,
  editable coordinates and the existing text/info tabs on the left; reserve a
  blank panel on the right. Keep the atom/composition/parity summary across both.

- Show the welcome window before importing NumPy, SciPy, ASE or VTK, then
  automatically preload libraries/readers in a worker thread after first paint.
  Prepare the hidden 3D canvas on the GUI thread and report readiness in the
  status bar; welcome animation and menus remain available during imports.
- Queue files selected during startup, including command-line files, and open
  them when ready. Preserve display settings and reuse the prepared backend.
- Keep imports alive safely through application shutdown, handle loading
  failures and retries, and avoid creating canvases after a window is closed.
- Test first-paint ordering, worker/GUI thread separation, responsiveness,
  file queues, early closing, settings transfer and backend reuse.

## 1.0.1 — 2026-10-26

- Switch original LELE source, documentation, assets and author-distributed
  binaries to the MIT License. Update package metadata and distribution
  notices, and archive the superseded binary-only terms as historical text.
- Add a selectable, clickable GitHub repository URL below the contact email
  on the welcome page.
- Set the application, package and Windows launcher version to 1.0.1.
- Include the MIT license and source/distribution notice in Windows build outputs.

## 1.0.0 — 2026-10-26

- Display sjzhang0905@hotmail.com immediately below the welcome version;
  support copying the address and opening the user's email application.
- Set the application and package version to 1.0.0 and include the author
  email in package metadata.
- Bring the white welcome page, four-frame step animation, grouped menus,
  X/Y/Z views, manual plane fitting, atom count, electron parity and standing
  parrot icon into the GitHub source release, retaining the proprietary license.

## 0.9.5 — 2026-10-26

- Repeat the four-frame standing / left leg / standing / right leg gait,
  dropping the redundant trailing standing pose. Keep 800 ms per frame and
  use 32 steps (25.6 seconds) per canvas pass so both loop boundaries remain
  aligned to complete gaits. Regenerate the animation-only GIF preview.
- Restore electron parity and the frame-specific net-charge control. Display
  Odd/Even and the charge assumption, without showing the total electron count.
- Extract the first standing pose into a transparent multi-size Windows icon.
  Set the application/window icon and Windows taskbar identity; embed the ICO
  through both local and GitHub Actions Windows builds. Include it in wheels.
- Print the actual built version from VERSION.txt instead of a stale hardcoded
  version in the Windows build script.

## 0.9.4 — 2026-10-26

- Replace the wide command toolbar with File, Edit, View, Analysis and Help
  menus, preserving existing keyboard shortcuts.
- Replace Front/Top/Side commands with X/Y/Z views from each positive axis.
  Move orthographic/perspective projection choices into View > Projection
  and keep their checked state in sync with the camera.
- Put the current frame's total atom count before its cell composition/formula.
  Remove electron-count display and its charge-counting control from the UI.
- Generate a best-fit plane only through the Fit selected plane button or
  menu command. Invalidate it after selection, fitted-coordinate, cell,
  periodic-image option or frame changes. Keep explicit XY alignment and undo.

## 0.9.3 — 2026-10-26

- Change the parrot walk to discrete steps: every 800 ms, pose and position
  update together. Keep the bird stationary between frames.
- Remove the overhead 乐乐 badge; retain the caption below the animation.
- Update timing regression checks and regenerate the welcome previews.

## 0.9.2 — 2026-10-26

- Replace the empty black startup canvas with a pure-white welcome page.
- Show the centralized application name, full name and version above the
  supplied parrot, named 乐乐, and the currently supported shortcut reference.
- Animate five right-facing poses at 800 ms per pose with smooth, looping
  left-to-right travel across the canvas. Stop both clocks when hidden.
- Keep the empty Files tree document-free; switch to the 3D view and data
  inspector only after a file loads. Defer VTK initialization until then.
- Support the welcome open button, existing Ctrl+O and file drops. Reflow
  shortcut columns and allow vertical scrolling in smaller windows.
- Include the artwork in source, wheel and PyInstaller distributions.

## 0.9.1 — 2026-10-26

- Rename the application to **LELE — Local Environment and Lattice Explorer**.
- Rename the Python package to `lele` and the main window to `LELEWindow`.
- Update the launcher, help title, default screenshot name and Windows build
  output to use LELE. Centralize the runtime name and version.
- Set a stable Qt application name and import valid legacy display presets
  without overwriting LELE settings.
- Add Python packaging metadata, English/Chinese READMEs, Git rules and GitHub
  Actions definitions for tests and manual Windows builds.
- Archive earlier release notes and validation records under `docs/history`.
- Establish the `sjzhang0905/lele` source repository and add proprietary,
  all-rights-reserved source licensing alongside the existing binary terms.

The source tree continues the fitted-plane, selection, deletion, undo and
appearance features of 0.9.0. Surface/heterostructure builders and automated
AIMD analysis remain planned extensions.

## 3.2.0

Added Gaussian FCHK, Molden wavefunction, CUBE multi-dataset and VASP volumetric import and visualization, plus WAVECAR metadata and ORCA GBW conversion support. See docs/FORMAT_SUPPORT_V3.2_CN.md for limits.

## 3.2.1

Validated full-complex scalar WAVECAR reconstruction against real output; added orbital-field selection and explicit GBW companion-output fallback.

## 3.3.0

Added independent isosurface styles and multiple levels on the active dataset, grid-aligned planar slices and CUBE field export.
