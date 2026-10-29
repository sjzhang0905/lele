# LELE v1.9.0 验证记录

日期：2026-10-28

## 检查结果

| 检查 | 结果 |
|---|---|
| 全量回归 | 291 passed，72 subtests passed，15.21 秒 |
| 最后一次底部标签排版调整后的相关 GUI 回归 | 12 passed，3.36 秒；已包含在上述测试范围内 |
| 原始独立 A1：Gaussian 多段电荷/多重度 | 1 passed，0.43 秒 |
| 公开真实 ORCA 输出 | 12 份通过，覆盖 4.2、5.0、6.0、6.1 |
| 真实输出的独立几何/能量比对 | 10 份与 ASE 输出读取器对照；2 份 ASE 不支持的输出与最终源表对照 |
| 界面截图 | 查看了 6 张合成 ORCA 示例的真实 Qt 控件/窗口截图；底部测量在正常窗口宽度下保持单行 |

检查环境：Linux，Python 3.12.14，PySide6 6.12.0，VTK 9.7.1 EGL，ASE 3.29.0。
Qt 使用 offscreen，界面测试使用真实 Qt 控件和 VTK 场景。
Windows EXE 未在当前环境构建或实机验收。

## 针对本次需求的检查

- 打开 Gaussian/ORCA 文件后没有新增轨道窗口；点击 Files 页按钮后才出现默认 eV 的轨道表。
- 2/3/4 原子分别显示键长、键角和二面角；清空选择、切帧和振动参考构型保持正确更新。
- ORCA 的电荷、多重度、能量、收敛指标、轨道与模式均按各自计算段和几何关联。
- 实际 Matplotlib 点击事件可跳转能量点关联的几何帧。
- Restricted/Alpha/Beta 占据、ORCA 零起始轨道编号及空轨道能量保留打印数据。
- 模式列按 3N 行完整性检查，不完整或含非法数值的列不产生动画。
- 新版 IR 取 Int 列，未混用 eps、T² 或跃迁分量；旧版 T² 明确标出源单位。
- 谐振动模式不二次按原子质量加权；零频且无运动的刚体模式不占振动列表。
- 经典合并自旋表和 ORCA 6 自旋局部编号表均对应原始 STATE 行，未重复增加三重态。
- 保留打印的跃迁系数正负、自旋、权重和来源表标签；NTO 占据不混入主要轨道跃迁系数。
- 电偶极从原子单位转换为 Debye；速度和磁偶极保留原子单位，永久/激发态永久偶极各自标识。
- UTF-8 BOM、UTF-16 LE/BE 的结构、结果与原始文本预览可读取。
- 缺失参考几何的后续计算段不借用上一段的模式或偶极参考。

## 真实输出样本

完整源路径、Git blob SHA 和本地 SHA-256 见 `qa_v1.9.0/orca_fixture_sources.json`、
`qa_v1.9.0/orca_real_v190.json`。原始公开计算输出未打入本源码包。

| 样本组 | 样本与核对内容 |
|---|---|
| cclib-data / ORCA4.2 | dvb_gopt、dvb_raman、dvb_td、dvb_scan_unrelaxed：4 个优化帧、54 个可动画振动模式、5 个单重态与 5 个三重态、12 个普通扫描帧/偶极 |
| cclib-data / ORCA5.0 | ADBNA_Me_Mes_MesCz：10 个单重态、10 个三重态、打印的系数和跃迁矩 |
| cclib-data / ORCA6.0 | 1618：两个 compound 段、独立方法/基组和电荷/多重度 |
| cclib-data / ORCA6.1 | 1509：50 个激发态、新版 Transition 表及打印组成 |
| cclib / basicORCA5.0 | dvb_raman：54 个模式和新版 IR Int 列 |
| cclib / basicORCA6.0 | dvb_raman、dvb_td、dvb_sp_un_dft、water_hf_solvent_smd：54 个模式、按自旋分组的跃迁表、开壳层占据及溶剂 |

真实优化与普通扫描输出已核对；带约束的特殊多维扫描、SOC 混合态、专用多组态组成及
非零初态 DOTRANS 不据此宣称已完整适配。支持范围见 [功能说明](FEATURES_v1.9.0_CN.md)。

## 可重复运行的本地回归

```bash
QT_QPA_PLATFORM=offscreen \
VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests -q --tb=short
```

JUnit 原始报告保存在 `qa_v1.9.0/full_v190.xml`、`ui_v190.xml` 和 `a1_v190.xml`。
本版源码保留此前 1.8.0 的所有源文件，版本号、README、变更记录和 Windows 生成的版本标记
均使用 1.9.0；ZIP 在保存前检查了成员 CRC 和逐文件内容一致性。
