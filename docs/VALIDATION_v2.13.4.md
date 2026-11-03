# LELE v2.13.4 外观调整与验证

日期：2026-11-03。基于 v2.13.3 源码包修改。

## 调整结果

| 项目 | 原值 | 新值 |
| --- | --- | --- |
| Atom colours 默认选项 | Sibyl | Default |
| 默认 Atom size | 60% | 50% |
| 默认 Bond thickness 滑块值 | 11 | 9 |
| 默认元素颜色 | 原 RGB | 原 RGB 混入 10% 白色 |

默认颜色对各 RGB 通道使用 `round(0.9 × 原通道值 + 0.1 × 255)`。例如 C 从 `#8E8E8E` 变为 `#999999`，O 从 `#E50000` 变为 `#E81A1A`，H 从 `#CCCCCC` 变为 `#D1D1D1`。H–Rg 使用原 Sibyl 参考色；超出该表的元素对其原有回退色做相同调整，D 随 H。

原子、按元素着色的键、元素配色编辑器和独立图例使用相同的默认颜色。原始 RGB 参考表保持完整，用户指定的元素色和单原子色继续按保存值使用。

旧预设和 `.lele` 项目中的 `Sibyl` 名称兼容映射为 `Default`。旧项目明确保存的原子大小、键粗细和自定义颜色可继续恢复；新建显示设置和默认 Classic ball and stick 预设使用本次新默认值。Space filling 的独立比例仍为 100%。纯白背景和 Glossy 光泽继续保留。

## 验证

- 完整回归：**981 项测试及 78 个子测试全部通过，零失败、零错误、零跳过**。已有测试中与本次要求直接相关的旧名称、旧颜色和旧大小断言已更新；原始 111 种元素的 TCL/RGB 对照检查继续保留。
- 对 **118 种元素及 D，共 119 项**逐项检查：新颜色各通道不变暗、总亮度增加；原子、元素色键、编辑器颜色入口和图例颜色一致。
- Qt 默认控件显示为 `Default`、Atom size `50`、Bond thickness `9`，Atom colours 下拉菜单不再显示旧名称。
- 配色对话框读取新的 O 默认色 `#E81A1A`；自定义元素色和单原子色保持准确。
- 包含旧 `Sibyl` 名称的项目和预设可正常载入；旧项目明确保存的 60% / 11 以及自定义 O 色均正常恢复。
- 实际生产 Qt/VTK 窗口复验：选中与清空原子时画布尺寸一致，键长编辑和撤销正常，背景渲染为 RGB `(255,255,255)`。

证据位于 `qa_v2.13.4/`：

- `full_retest.log`、`full_retest.xml`：完整回归日志。
- `palette_consistency.json`、`palette_consistency.log`：控件、119 项颜色、旧项目和旧预设兼容检查结果。
- `default_palette_colors.csv`：119 项颜色的原值与新值。
- `native_window.json`、`white_default_render.png`：本次实际窗口结果和渲染图片。

完整回归的环境变量和私有真实样例沿用 `VALIDATION_v2.13.2.md`；用户私有输入文件不随源码重新分发。实际窗口复验入口沿用 `qa_v2.13.3/check_native.py`。

环境：Linux、Python 3.12、PySide6 6.12.0、VTK 9.7.1；Qt offscreen 与 VTK EGL。交付为源码包，Windows EXE 未构建或实机验证。
