# LELE v3.4.0 验证记录

日期：2026-11-05。基线：LELE_v3.3.0_20261105.zip，SHA256 为
`30ffef3f553eac039e02c7650b5a843519e71bc5b1bb3d6855fe521bea920593`。

## 最终结果

| 检查 | 结果 |
|---|---|
| 完整测试集 | **1263 passed, 12 skipped, 78 subtests passed**；0 失败，0 错误 |
| 修复、映射、旧视图及 WAVECAR 定向测试 | **55 passed**，已包含在全量测试中，不重复相加 |
| 原 v3.3.0 独立验收用例 | **9/9 通过**，同样包含在全量测试中；基线为 5 失败 / 4 通过 |
| 新映射专项测试 | **15/15 通过**，包含在全量测试中 |
| wheel 构建 | `lele_explorer-3.4.0-py3-none-any.whl` 构建成功 |
| 示例工程 | mapped.lele 与 overlay.lele 均通过主窗口工程加载入口打开 |
| 图像与界面 | 实际 EGL 渲染、PNG/GIF 颜色检查、Qt 对话框截图人工检查通过 |

环境：Linux，Python 3.12.14，NumPy 2.3.5，ASE 3.29.0，PySide6 6.12.0，VTK 9.7.2，pytest 9.2.0。
测试环境变量：`QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`。

测试中的主窗口使用 Qt 离屏控件与包内 HeadlessCanvas 适配器；使用真实主窗口回调、科学数据模型、VTK 几何和相机。PNG/GIF 使用独立 EGL 窗口真实渲染。这不等同于 Windows 桌面、显卡驱动及单文件 EXE 的实机验收；本次未进行后者。

## 覆盖内容

- A1：FCHK、无频率 Molden 的解析→加载→轨道按钮，以及历史缺阶段工程的兼容处理。
- A2：首次轨道网格的相机适配与裁剪；保持普通结构文件原有视图；WAVECAR 生成/取消路径。
- A3：Boundary 扩展与偏移、斜晶胞、非零网格原点、周期端点舍入、非周期场不复制。
- 解析线性势在不同分辨率斜网格上的表面取样，逐顶点对比解析值；红白蓝零点、负/正两端；刚性变换；跨场层绑定与文件切换。
- 非周期网格部分覆盖灰色提示/完全无覆盖省略；结构、原子顺序、晶胞与占据检查；失败不部分追加网格。
- 界面导入→保存工程→删除外部来源→重新读取→渲染；几何编辑脱离场后的隐藏；设置对话框确认与取消。
- PNG/GIF 像素检查排除底部色标区域，验证表面本身确有映射颜色；导出包含色标。

完整日志、JUnit XML、截图和机器可读结果位于 `verification/v3.4.0/`。
12 个跳过用例的原始原因见 SUMMARY.json 与 full_final.xml；不计入通过数。
VTK 9.7 对 vtkTransformPolyDataFilter 给出弃用提示，仍可执行；保留该类以兼容声明支持的 VTK 9.3 起始版本。

## 复现

安装 requirements.txt、pytest；轨道求值相关可选测试还需要 PySCF。执行：

```bash
python -m pytest -q
python -m pytest tests/test_acceptance_regressions_v340.py tests/test_field_mapping_v340.py -q
python -m build --wheel --no-isolation
```

新功能步骤和科学数据边界见 `docs/FEATURES_v3.4.0_CN.md`。演示网格为明确标注的人工解析数据，不是新增电子结构计算结果。
