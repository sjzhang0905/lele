# LELE 3.9.0 验证记录

验证日期：2026-11-11。环境：Python 3.12、PySide6 6.12、VTK 9.7，Linux Qt offscreen / EGL。

## 回归结果

完整测试 **1947 passed、16 skipped、78 subtests passed**，耗时 108.30 秒。日志与 JUnit 结果见 `verification/v3.9.0/full_suite_final.log` 和 `full_suite_final.xml`。跳过项取决于可选环境；现有弃用警告主要来自 VTK 接口与测试插件。

执行命令：

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --timeout=45 --tb=short
```

## 本轮重点

- 场数据：多项加减、不同原子组成的同网格参考片段、已知单位换算、未知单位声明、拒绝错位／网格／周期／量纲不匹配、非有限数与溢出、后台取消以及提交前状态检查。
- 持久化：源数据保持不变，衍生网格与公式随项目保存；CUBE 导出、回读及重新导入保留数值、几何和来源。旧项目缺少新来源字段时正常读取。
- 实际 `PARCHG+0.3`：168×168×480 网格；`A−A` 非零网格点为 **0**，`A+A−A` 与原始 float32 网格逐位相同。两项计算分别约 0.280 与 0.416 秒，仅供本环境参考。记录见 `parchg_arithmetic.json`。
- 原子选择：真实 Qt Enter 联动主窗、坐标表与选区；范围、中文逗号、混合占据、错误输入不提交、文档切换和原子重排；编辑框获焦暂停播放，Ctrl+Z 恢复选区。
- 大结构：100,000 原子的未变化刷新复用映射，不重复扫描全体原子；粘贴、删除、重排、改变元素与混占时正确失效。
- 快捷键：真实 Qt 画布事件、1–9 槽位覆盖／追加／调用、输入框焦点隔离、Shift 标点和模拟 Windows/XKB 键码、忽略自动重复、阻止 VTK 原有数字 3 立体显示快捷键；保持旧快捷键、撤销及项目往返。
- 启动：新面板在未加载结构时保持 Qt-only，首帧绘制后再预加载科学计算模块；原启动响应测试通过。
- 发布：165 个 Python 模块语法检查通过；3.9.0 wheel 构建成功，包含新增模块与资源，归档完整性检查通过。新版源码包只附带当前版本 wheel。

本次没有 Windows 实机交互验证；Windows 键码逻辑已通过模拟事件测试。UI 布局已检查，Qt offscreen 验证不等同于 Windows 驱动环境的实机测试。
