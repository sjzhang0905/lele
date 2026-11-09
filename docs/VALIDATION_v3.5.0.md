# LELE v3.5.0 验证记录

日期：2026-11-09。基线为 `LELE_v3.4.0_ESP_overlay_20261105.zip`，SHA256：
`e7d708d75aa9abe954a9104196479e18cb8e46291af997c904cd3611e471c5fc`。

## 结果

| 检查 | 结果 |
|---|---|
| 最终完整测试集 | **1289 passed, 12 skipped, 78 subtests passed**，0 失败、0 错误 |
| 新增 v3.5.0 用例 | **26 项**，包含在完整测试集内，不重复相加 |
| NMR 图像/表格 | 实际导出 PNG、SVG、CSV；检查峰位置、横轴方向、空参考值、张量与排序后的原子定位 |
| 官方 GIPAW 真实样例 | quartz-nmr.out 解析出 1 组、9 个核；首个 Si 的 Total sigma 为 431.33 ppm |
| 原有 ESP / 等值面回归 | 原 v3.3.0 验收问题、v3.4.0 映射与叠加测试全部保留并通过 |
| wheel | `lele_explorer-3.5.0-py3-none-any.whl` 构建成功，包含三个 NMR 模块 |
| 界面检查 | 主窗口布局、独立原子样式实际 EGL 渲染、NMR 对话框、Crystal 和 Dipole 窗口 |

环境具体版本及 12 个跳过原因见 `verification/v3.5.0/SUMMARY.json`。跳过不计入通过数。现有 VTK 9.7 弃用提示等保留在日志中；没有为消除警告改变旧版 VTK 兼容路径。

## 关键覆盖

- 选中原子的样式不改变其他原子和整体 Style；不同端点的普通键半段；Global 恢复；跨帧、撤销和工程往返。
- 元素首次出现顺序、混合 CIF 原始组分顺序；默认折叠、单击不展开、双击坐标原子定位及重绘后展开状态。
- 四个设置页移到底部左侧，三个数据页移到右侧；页脚对齐；Crystal/Dipole 反复打开与输入框回车行为。
- Gaussian 多计算块、Fortran D 数字及非有限记录；Gaussian XYZ 标签的张量顺序。
- ORCA 的 0 起始编号、只计算部分核、完整总张量但摘要被截断的情况。
- CP2K 总项与分项区分；GIPAW Total 区段；NWChem 总屏蔽。
- VASP ISO_SHIFT 取负号、ISO_SHIELD 原样保留、BDIR 列转为 XYZ 张量、核贡献及 G=0 分组。
- 参考值按元素保存，缺参考时不生成化学位移；参考差值、等面积展宽、窄峰欠采样保护、CSV 来源与张量；原子导航不跨错计算块；无坐标结果可单独载入。

## 验证边界

测试使用 Linux/Python 3.12、Qt 离屏控件与现有 HeadlessCanvas 适配器。界面截图中的画布嵌入了单独真实 EGL 渲染的图像，用于检查布局和几何；它不是原生窗口嵌入的实机截图。未进行 Windows 桌面、显卡驱动或单文件 EXE 实机验收。

NMR 解析主要使用遵循官方格式的人工数值用例，另使用官方 QE/GIPAW quartz 输出验证。没有在本轮重新运行六种电子结构程序，也没有宣称覆盖它们全部历史版本。谱图范围与科学假设见 `FEATURES_v3.5.0_CN.md`。

## 复现

```bash
python -m pytest -q
python -m pytest tests/test_nmr_v350.py tests/test_ui_v350.py -q
python -m build --wheel --no-isolation
```

Linux 离屏验证使用：
`QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`。

完整日志、JUnit XML、构建日志、截图、谱图及文件改动清单位于 `verification/v3.5.0/`。
