# LELE 3.10.0 外部样例补跑

日期：2026-11-11。

## 结论

首轮全量的 **16 个跳过记录已全部补齐**。其中 PySCF 原先按整个模块记作 1 次收集跳过，安装依赖后展开为 4 项，所以本次合计 **19 passed、0 skipped、0 failed、0 errors**，统一复验耗时 8.72 秒。

本次是针对原跳过项目的补跑，不是重新运行所有测试。首轮全量的 2021 passed、78 subtests passed 记录保持原样；本次补跑不重复计入这些已通过项。另对配色相关回归进行了检查：42 passed、58 subtests passed，其中包含本次配色和两个 CHGCAR 用例。

## 覆盖内容

| 项目 | 实际测试数 | 验证内容 |
| --- | ---: | --- |
| POSCAR1/2 与 v13 旋转脚本 | 7 | 三种操作下固定标志和行序保留、真实刚体重定向、脚本算法对照、Direct/Cartesian 真空层及新增原子导出 |
| 22.cif 与 DPA CIF | 2 | 434 原子组成、88 原子的空间群显式操作展开与坐标一致性 |
| CHGCAR | 2 | 六种文件名的网格精确哈希一致，周期等值面 Boundary 重复 |
| Sibyl.tcl | 1 | 111 元素的原子、键与图例配色 |
| CP2K Molden 振动文件 | 1 | 124 原子、六个频率、122 个冻结原子与 8 帧 GIF |
| QE 原始输入输出及 modes | 1 | 输入、五帧优化能量和晶胞、收敛状态、声子频率和本征矢绑定 |
| 真实 WAVECAR | 1 | 独立读取与平面波直接求和，实部/虚部和密度积分 |
| PySCF 独立轨道 | 4 | Molden/FCHK、球谐/笛卡尔基组的顺序、归一化及相位 |

WAVECAR 样例为 ISPIN=1、3 个 k 点、48 条能带、ENCUT=450 eV 的标准完整复数标量存储。没有提供与之对应的 OUTCAR，因此没有启用可选的 OUTCAR 打印能带/占据对照；这不属于原 16 个跳过记录之外的新完成项。

## 唯一发现与处理

原 Sibyl 测试只包含先混入 10%、再混入 5% 白色的旧规则，遗漏用户在 3.8.0 要求的额外 15% 白色，导致首次补跑失败。生产配色符合现有要求。

仅在旧测试中补充这一步独立预期计算，继续从原始 Tcl 颜色开始、每步独立取整，不调用生产配色函数生成预期。原子、键和图例全部通过。**生产代码及原 wheel 均未修改，版本仍为 3.10.0。** 原始失败日志保留，最终复验日志另存。

## 环境、数据与复现

测试环境补装 PySCF 2.15.0、pymatgen 2026.10.24（pymatgen-core 2026.10.31），只作为 QA 依赖；不加入 LELE 运行依赖。Qt 使用 offscreen、VTK 使用 EGL；没有新增原生 Windows 桌面验证。

13 个原始输入的 SHA256 在补跑前后全部一致。原始私人样例仍在独立测试目录，没有打包进入源码发布包。文件名、校验值与结果见 `verification/v3.10.0/external/supplement_summary.json`。

已增加统一补跑入口，显式检查样例与依赖，若仍有跳过会返回失败，避免漏接外部路径后把测试标为完成：

```sh
python -m pip install pyscf pymatgen pytest-timeout
python tools/qa/run_external_samples.py /path/to/original-samples
```

脚本在给定目录及其 `LELE/`、`work/` 子目录寻找原始文件；POSCAR1/2 需要同目录，四个 QE 文件也需要同目录。这些旧回归包含原样例的精确数值，不能将其他体系改成相同文件名直接替换。

主要证据：

- `verification/v3.10.0/external/supplement_final.log`、`.xml`：统一 19 项最终复验。
- `structures_initial.*`、`calculations_initial.*`、`wavefunctions_initial.*`：各组首次补跑。
- `field_palette_initial.*`：原配色测试的失败证据。
- `field_palette_final.*`、`field_palette_current_rule.json`：配色修正后相关回归与独立核对。
