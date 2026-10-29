# LELE v1.10.0 验证记录

日期：2026-10-28

## 结果

| 检查 | 结果 |
|---|---|
| 最终全量回归 | 311 passed，72 subtests passed，17.48 秒 |
| 新增工作流测试 | 20 项，已包含在全量回归内 |
| 原始独立 A1：Gaussian 电荷/多重度 | 1 passed，0.53 秒 |
| 公开真实 ORCA 输出 | 13 份通过，覆盖 4.2、5.0、6.0、6.1 |
| 真实输出独立几何/能量对照 | 11 份与 ASE 核对；2 份 ASE 不支持的输出与最终源表核对 |
| 提供的真实 NEB/Hessian 文件 | 主输出、4 个路径配套文件及 Hessian 输出均核对通过 |
| 界面检查 | 查看 8 张真实 Qt 合成样例截图；无几何的 GOAT 也可打开分析窗口 |

环境：Linux，Python 3.12.14，PySide6 6.12.0，VTK 9.7.1 EGL，ASE 3.29.0。
Qt 使用 offscreen；界面测试运行真实 Qt 控件和 VTK 场景，截图为实际 Qt 对话框。
本环境未构建或实机验收 Windows EXE。

## NEB 与 Hessian 实文件核对

- 主输出分成反应物预优化、产物预优化、NEB、TS 精修四个阶段。
  产物优化 66 步后仍未收敛；其最后能量保持 −2883.822370414332 Eh，未被首个 TS 能量覆盖。
- `.NEB.log` 的 20 次快照（0–19）与 MEP XYZ 对应，每次 16 个 image，全部 320 个结构匹配。
  加上主输出参考/优化结构和明确打印的 CI 结构，共 437 帧。
- `.interp` 有 21 次快照（0–20），主输出有 21 条 NEB 迭代记录。缺失匹配结构的末次路径
  保持能量结果，未借用上一迭代结构；不同来源的路径分别保留。
- 文件树、实际表格选择和主窗口前后帧验证了“固定快照遍历 image”与“固定 image 遍历迭代”
  是不同的序列。GIF 导出接收到的帧同样限定在当前序列。
- 独立 Hessian 文件的初始优化 Hessian 有 57 个非零模式、2 个虚频；最终频率验证有
  57 个非零模式、1 个虚频。默认频率入口选中最终验证，没有把初始模式当作最终结果。
- 主 NEB 为 22 原子/电荷 0，Hessian 样本为 21 原子/电荷 +1，未互相接入数据。
- 合成回归另检验周期 1/3 的精确 Hessian、模型/读入及更新的区分；数值 Hessian 微位移
  的坐标、能量、轨道与偶极不覆盖优化母结构。

实文件仅用于本次本地核对；源码包不包含原始附件或其中的分子截图。
输入哈希及计数保存在 `qa_v1.10.0/private_v1100.json`。

## GOAT 与 SOC

- GOAT 合成样例检验 4 个构象、打印温度/简并度/布居、温度变化、布居归一化、重原子 RMSD、
  排序后的结构编号和 CSV 字段。直接 XYZ、缺少配套结构、主输出无几何及纯能量表均覆盖。
  尚无真实 GOAT 输出验收样本，支持范围以官方格式和这些回归为限。
- 公开 ORCA 5 `dvb_soc.log` 核对出 110 个复数耦合元、41 个 SOC 混合态、40 个修正跃迁；
  原自旋自由结果仍是 10 个单重态与 10 个三重态，没有被 SOC 表重复扩充。
- 合成回归检验 Z/X/Y 原始列顺序、复数符号、cm⁻¹/eV 转换、稀疏 H 的 Block/Root/S/Ms 标签、
  混合态原始组成、复数跃迁偶极，以及一次文件选择导出全部 SOC 表。
- 未打印的耦合保留缺失值；SOC 模长不解释为 ISC 速率；没有实现任意多组态稠密矩阵格式。

## 公开样本与界面证据

`qa_v1.10.0/orca_fixture_sources.json` 保存 13 份公开样本的仓库路径及 Git blob SHA；
`orca_real_v1100.json` 保存 SHA-256、帧数、模式/态计数和独立对照方式。
在此前 12 份样本基础上增加 cclib-data 的 `ORCA/ORCA5.0/dvb_soc.log`。
普通优化样例保留能量为空的初始参考几何，`dvb_gopt.out` 为 5 个结构、4 个有能量的优化点。
原始公开输出未打入源码包。

| 界面 | 截图 |
|---|---|
| NEB 路径 | [路径与力](../examples/v1100_neb_path.png) |
| 固定 image | [优化历史](../examples/v1100_neb_image_history.png) |
| NEB 收敛 | [能垒与 maximum/RMS 力](../examples/v1100_neb_convergence.png) |
| Hessian | [阶段与周期](../examples/v1100_hessians.png) |
| GOAT | [能量、布居与 RMSD](../examples/v1100_goat.png) |
| SOC 耦合 | [分量表与热图](../examples/v1100_soc_couplings.png) |
| SOC 混合态 | [能量与原始组成](../examples/v1100_soc_states.png) |
| SOC 吸收 | [修正光谱与复数偶极](../examples/v1100_soc_absorption.png) |

## 重复运行

```bash
QT_QPA_PLATFORM=offscreen \
VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests -q --tb=short
```

JUnit 报告在 `qa_v1.10.0/full_v1100.xml` 和 `a1_v1100.xml`。
Windows 构建脚本和 PyInstaller 配置继续保留，运行版本取自 `lele/__init__.py` 的 1.10.0。
发布 ZIP 保留前版所有成员；保存前核对成员 CRC 及每个成员与最终源码目录的字节一致性。
