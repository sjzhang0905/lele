# LELE v1.11.1 验证记录

日期：2026-10-28

| 检查 | 结果 |
|---|---|
| 最终全量回归 | 347 passed，72 subtests passed，19.38 秒 |
| 新增独立数据回归 | 10 项，已包含在全量结果中 |
| 实文件派生核对 | 去除 `opt2.log` 坐标块后：175 个能量点、0 个结构、Alpha/Beta 轨道仍可用 |
| 实文件派生核对 | 去除 `xtbopt.log` 能量/gnorm 字段后：37 个结构、0 个能量、无曲线 |
| 界面检查 | 查看 3 张合成数据的真实 Qt 截图 |

环境：Linux，Python 3.12.14，PySide6 6.12.0，VTK 9.7.1 EGL，ASE 3.29.0；Qt offscreen。
当前环境未构建或实机验收 Windows EXE。

新增检查包括：没有配套文件的能量结果；附近存在同能量轨迹时仍不补造未知坐标；
纯结构的能量与曲线缺失；单个能量结果；无结构页面、总览、CSV/曲线与坐标的独立性；
切换文件时不保留旧结构/旧能量；无结构时的播放和帧快捷键；不请求创建原生 3D 画布；
以及无坐标的 HOMO/LUMO 浏览。此前所有 xTB 与 Gaussian/ORCA/NEB/GOAT/SOC 回归均保留。

实文件派生测试仅在临时副本中删除对应数据，原附件未修改，派生的真实结构文件未打包。
核对摘要与输入哈希见 `qa_v1.11.1/independent_real_v1111.json`。
JUnit 报告为 `qa_v1.11.1/full_v1111.xml`。

界面证据：[纯能量结果页](../examples/v1111_energy_only.png)、
[纯能量曲线](../examples/v1111_energy_only_curve.png)、
[纯结构帧浏览](../examples/v1111_structure_only_files.png)。

重复运行：

```bash
QT_QPA_PLATFORM=offscreen \
VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests -q --tb=short
```

源码与构建版本为 1.11.1，保留前版全部源码包成员；ZIP 保存前核对 CRC 和逐文件字节一致性。
