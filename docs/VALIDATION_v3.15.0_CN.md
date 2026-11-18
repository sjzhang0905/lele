# LELE 3.15.0 验证记录

日期：2026-11-17。基线：本次上传的 LELE 3.14.0 源码包。

## 结果

- 完整回归：**2288 passed，16 skipped，78 subtests passed**，进程退出码 **0**，用时 133.82 秒。
- 独立整合复核：42 项通过，进程退出码 0。
- Python 源码编译检查通过；新 wheel 内全部 **181 个 Python 模块**与源码逐字节一致。
- Qt 控件截图及真实 VTK/EGL 渲染图片已查看。

完整测试命令：

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow python -m pytest tests -q --junitxml=verification/v3.15.0/regression.xml
```

## 本次重点覆盖

| 改动 | 已检查内容 |
|---|---|
| 分子 CUBE | 不误设周期边界、不显示采样盒晶胞框；CASTEP 与明确周期元数据保留；向周期结构附加通用 CUBE |
| electron/hole 图层 | 第二行完整显示；切换非负源场时修正不适用的负等值面；超范围明确提示 |
| VMD 式颜色映射 | RWB/BWR 端点、中点、非对称范围；全网格自动范围；旧项目配色兼容；滑杆复用网格；单位保留 |
| 实时映射窗口 | 输入与滑杆立即预览；无独立弹出映射窗口；Cancel 恢复；切换源文档后不误写；关闭时释放对象 |
| Scan step | 父节点选择最后一帧；优化子步骤仍可单独选择 |
| 文件右键 | 显示名称随项目保存；卸载不删除源文件；树、撤销、振动引用重排；恢复其他文档视图；最后一个卸载后返回欢迎页 |
| Boundary 测距 | 正交及斜晶胞的实际副本距离/角度；同源原子两个副本；高亮匹配；切换选择、边界及保持原点模式时重置旧副本 |
| 裁剪导出 | 保存上次确认选择；隐藏原点/角落坐标轴；保留色标/标签；异常与正常结束均恢复画布；普通曲线保留数据坐标轴 |
| 毛毛虫图 | 静止结构继承主画布颜色、大小、单原子外观、灯光、Boundary、投影与相机；移动原子沿用路径显示；实际 PNG 导出 |
| 弹窗层级 | 所属窗口关系、非模态交互、无系统级 WindowStaysOnTopHint |

## 范围与限制

本次在 Linux、Python 3.12.14、PySide6 6.12.0、VTK 9.7.2 环境验证。未在 Windows 实机运行；Windows 的原生窗口堆叠及高 DPI 显示仍需实机确认。包中提供源码和 Python wheel，不含此次新构建的 Windows EXE。

16 项跳过来自未提供的外部私有 CIF、POSCAR、CHGCAR、CP2K/QE/WAVECAR 样例、原始旋转脚本和 Sibyl.tcl，以及可选 PySCF 依赖。逐项原因在 `verification/v3.15.0/skipped_checks.json` 中；这些项目不计入通过数量。

测试警告来自第三方依赖的弃用提示，未作为失败忽略。

## 验证材料

- `verification/v3.15.0/regression.xml`：最终完整回归 JUnit 结果。
- `verification/v3.15.0/release_manifest.json`：环境、源码哈希与 wheel 哈希。
- `verification/v3.15.0/changes.json`：本次源码改动列表。
- `verification/v3.15.0/surface_mapping_dialog.png`：双图层与内嵌映射控件。
- `verification/v3.15.0/surface_mapping_render.png`：实际映射渲染与简化色标。
