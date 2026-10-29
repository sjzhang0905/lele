# LELE v1.11.0 验证记录

日期：2026-10-28

## 结果

| 检查 | 结果 |
|---|---|
| 最终全量回归 | 337 passed，72 subtests passed，18.59 秒 |
| 新增 xTB 回归 | 26 项，已包含在全量结果中 |
| 提供的真实文件 | `xtbopt.log`、`opt1.log`、`opt2.log` 全部通过 |
| 独立几何核对 | ASE plain XYZ 读取轨迹的全部 37 帧，逐帧比较元素与坐标 |
| 真实能量/轨道核对 | 与源文件最终 TOTAL ENERGY、HOMO/LUMO 标记、HL-Gap 和汇总 gap 比较 |
| 真实 GUI 联动 | 37 步完整轨迹跳帧、175 步能量曲线的缺失结构点处理、两个自旋通道 |
| 界面检查 | 查看 4 张合成 xTB/g-xTB 数据的真实 Qt 窗口截图 |

环境：Linux，Python 3.12.14，PySide6 6.12.0，VTK 9.7.1 EGL，ASE 3.29.0。
Qt 使用 offscreen；当前环境未构建或实机验收 Windows EXE。
读取 xTB 文件没有启动外部 xTB 进程或增加新的运行依赖。

## 三份实文件

- `xtbopt.log`：37 帧，329 原子，第一条能量 −445.874762835742 Eh，
  最后轨迹能量 −445.876151974662 Eh；几何单位保持 Å。
- `opt1.log`：GFN2-xTB，37 个周期与轨迹一一匹配，最终单点能量 −445.876152027688 Eh。
  HOMO/LUMO 416/417，Energy/eV 为 −18.3417/−17.9534，汇总 gap 0.388346320974 eV。
  分数占据未使 LUMO 被重新当作 HOMO；初始和最终轨道表分开，最终重复表合并。
- `opt2.log`：g-xTB，175 个周期，123 原子的最终结构；174 个更早周期没有配套坐标，
  曲线仍有 175 个能量点，未套用 329 原子的轨迹。
  最终能量 −5345.882504897930 Eh，Alpha 209/210、Beta 206/207；
  通道 gap 7.0657/6.1802 eV，源总汇总 7.065672459737 eV 单独保留。
- `opt1.log` 只打印 Finished run，`opt2.log` 显式打印 normal termination of xtb；
  两者优化均有自己的 Converged 标记，运行状态与优化状态分别记录。
- 按钮只在有轨道/能隙信息时启用，加载文件没有弹出轨道窗口。
  对真实 37 步轨迹点击第 17 个能量点，画布切到相应结构；
  对 175 步曲线点击缺失坐标的第 101 点不跳帧，末点可打开最终结构。

源码包不包含原始附件或真实分子截图。
输入哈希、计数和核对摘要见 `qa_v1.11.0/xtb_real_v1110.json`。

## 新增自动回归

后端检验内容包括：内容识别、Eh/eV 与 Å/Bohr 单位、标准 SCF done 注释、
完整轨迹关联，以及原子、能量、最终坐标或完整性不匹配时拒绝关联；
还包括分数占据、空白未占据行、原编号、重复表、缺失虚轨道、自旋通道、
汇总 gap、未收敛与截断文件、Finished run、UTF-16、多个连续作业和帧数上限。

GUI 检验覆盖按钮触发、默认 eV、单位切换、真实 Matplotlib 事件跳帧、
能量点缺少结构时不跳转、包含所有周期及空帧号的绝对能量 CSV、
alpha/beta 表格与原轨迹播放导航。
此前 Gaussian/ORCA、NEB/GOAT/SOC 和显示交互测试均保留在全量回归中。

| 截图 | 内容 |
|---|---|
| [xTB 轨道](../examples/v1110_xtb_orbitals.png) | 分数占据与显式前线轨道 |
| [xTB 能量](../examples/v1110_xtb_energy.png) | 完整的三周期结构/能量对应 |
| [g-xTB 轨道](../examples/v1110_gxtb_orbitals.png) | Alpha/Beta 与独立源汇总 gap |
| [g-xTB 能量](../examples/v1110_gxtb_energy.png) | 没有完整结构历史时保留能量点 |

## 重复运行

```bash
QT_QPA_PLATFORM=offscreen \
VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests -q --tb=short
```

JUnit 报告在 `qa_v1.11.0/full_v1110.xml`。
本版保留 1.10.0 源码包的全部成员；版本号、README 和 Windows 构建读取的版本均为 1.11.0。
ZIP 保存前检查成员 CRC 与最终源码逐文件字节一致性。
