# LELE 3.14.0 验证记录

日期：2026-11-13。基于 3.13.0，完成本次六项修改，保留此前的扫描、批处理、选择语法、非模态弹窗和启动预加载功能。

## 结果

- 全量回归：**2260 passed，16 skipped，78 subtests passed**，198.64 秒，无失败。见 `full_pytest.log`。
- 最后补充的旧项目扫描编号迁移及相关集成回归：**48 passed**，9.11 秒。见 `final_integration.log`；其中包含扫描、项目读取、坐标表及侧栏菜单验证。
- 旋转预览、绕轴/二面角编辑、非模态窗口规则：**72 passed**。见 `rotation_preview_regression.log`。
- 布局、欢迎页、首次绘制与预加载：**32 passed**。见 `layout_startup_regression.log`。
- 安装 wheel 的全部 **179 个 Python 模块**与打包源码逐字节一致；最终 ZIP 做 CRC 检查并逐文件比对。

16 项跳过包含缺少可选 PySCF，以及未提供给本环境的外部 CIF、POSCAR、CHGCAR、CP2K Molden、QE、WAVECAR、配色和旋转参考样例；与上一版的外部条件相同。警告主要来自 ASE/NumPy、VTK、Qt/Matplotlib 的弃用接口，不是失败记录。

## 关键检查

1. ORCA 从 0 开始的编号只保留为原子标签模式。其他通用表格、编辑器、选择输入、工具提示和生成的扫描标题采用从 1 开始的原子编号。扫描解析器内部编号及源文件正文不修改；旧项目的派生扫描说明在载入时刷新。
2. 实际鼠标拖动释放前，角度框及渲染场景已同步更新。反复拖动不累积误差，轴上原子固定，Cancel 不改变结构，Rotate 仅写入一次撤销记录。切换文档、修改坐标或成键规则后，过期预览不能提交。
3. 默认大小滑杆为 Atom 45、Bond 5；成键阈值保持 0.88。Size scale 支持多选、独立撤销、项目往返、周期副本和真实 PNG 导出。
4. 菜单与侧栏等宽；画布顶部与菜单顶部对齐，调整侧栏宽度后关系不变。坐标表只含 Atom、X、Y、Z。
5. 两侧交替扩胞保留原坐标和原子顺序，覆盖非正交晶胞、负方向副本、周期键/氢键、混合占据、选中样式、Undo 和导出。边界轮廓、体场裁剪及平面范围使用对应的显示晶胞原点；原有项目可保持旧 Boundary 行为。

## 图像和环境

`sidebar_atoms.png` 是实际 Qt 控件布局截图，画布使用测试桩；`rotation_slider_dialog.png` 是实际 Qt 弹窗。`rotation_preview_before_after_cancel.png` 使用真实 VTK EGL 离屏渲染；取消后的 framebuffer 与预览前逐像素相同。

环境为 Linux、CPython 3.12.14、PySide6 6.12.0、VTK 9.7.2，Qt 使用 offscreen。没有运行 Windows 原生窗口或构建 Windows EXE，也没有声称完成 Windows 重启后的冷缓存性能测试。包中提供完整源码、wheel 和原有 Windows 启动/构建脚本。
