# LELE v2.1.0：VASP 输出与独立文件支持

本版在 v2.0.3 上增加 VASP 专用读取流程，保留 Ctrl+B 普通键、Ctrl+H 虚线氢键、
编辑时冻结连接、逐文件视图保存等原有功能。解压后运行 `start_windows.bat`。

## 可以打开的文件

| 文件 | 读取内容 | 缺少其他文件时 |
| --- | --- | --- |
| OUTCAR、OUTCAR_opt、OUTCAR_freq、重命名的 VASP 输出 | 离子步结构、晶胞、力、能量、任务信息、振动频率/位移 | 独立打开 |
| 只有离子步能量的 OUTCAR 片段 | 每条能量记录、能量曲线、CSV | 结果页，无虚构结构 |
| 只有结构的 OUTCAR | 已打印的完整结构、晶胞；若有力也保留 | 结构浏览，无虚构能量 |
| XDATCAR、XDATCAR_*、重命名的 XDATCAR | 多帧结构、分数/笛卡尔坐标、晶胞、重复元素组 | 独立浏览、播放和结构导出 |
| OSZICAR、OSZICAR_* | 离子步 F、E0 能量记录 | 结果页、曲线、CSV，无坐标 |

不会自动读取同目录的 POSCAR、CONTCAR、POTCAR、OUTCAR 或 XDATCAR 来填充缺失数据。
例如 XDATCAR 没有能量，仍可打开播放；OUTCAR 只有能量，仍可查看、导出全部记录。
单独的初始坐标不会被强行分配给后来未匹配到坐标的能量。

XDATCAR 支持固定晶胞，以及每帧/分段重复完整晶胞头部的变胞形式。若文件只含一个
固定晶胞头部，按文件中实际给出的晶胞读取，不推算未打印的变胞过程。
旧式无元素行的 XDATCAR 仅在标题明确逐项列出所有元素组时读取，不能从文件确定元素时
会明确报错；不从邻近 POTCAR 猜测元素。没有晶胞的笛卡尔坐标可展示，但不启用周期映像。

## 能量和力

内部能量使用 eV。默认依次取 `energy(sigma->0)`、`free energy TOTEN`、
`energy without entropy` 中实际打印的值。Results / info 展示可用的三种数值。
能量窗口可以明确切换到任一种已打印的量；缺少的值留空。

曲线 CSV 包含离子记录号、可选的结构帧号、当前选中的能量、三种原始能量、
Cartesian maximum/RMS force 和来源行号。纯能量点没有结构帧号，点击不会跳到不相关结构。
OSZICAR 默认 E0，缺失时用 F；不把 DAV/RMM 等电子迭代记录当成离子步。

OUTCAR 也可能在电子迭代内部打印 TOTEN；读取器根据电子/离子阶段区分，不把这些中间值
接入离子曲线。力曲线的 maximum/RMS 是已打印笛卡尔力分量的最大绝对值/均方根，
不冒充 VASP 的结构优化收敛判据，也不补造未打印的阈值。

## 振动与虚频

`Eigenvectors and eigenvalues of the dynamical matrix` 产生振动列表。`f/i` 保存为负频率，
列表保留原始编号。用模式表中实际打印的 XYZ 作为振动参考结构，使用该计算的晶胞；
动画不使用最后一个有限差分位移结构代替参考结构。有限差分结构在文件树单独标明。

原始动力学矩阵本征向量除以各原子的 `sqrt(POMASS)` 后用于动画、位移箭头和选中原子
贡献分析。如果 OUTCAR 已打印 `Eigenvectors after division by SQRT(mass)`，优先使用该表，
同一模式不重复列出。POMASS 缺失时使用标准元素质量并在结果中注明。

没有完整位移表的模式保留频率但不能动画；没有元素和坐标的纯频率片段可显示频率结果。
本版不从频率或位移推算 IR/Raman 强度。有限差分文件的曲线包括各个位移结构，不能将其
解释为优化收敛轨迹。计算概览中的频率任务能量使用能匹配到的振动参考结构能量；
匹配不到时保持缺失。

## 边界与验证

尾部尚未写完时，保留已完成的结构/模式并给出说明，不回退成只有最后一帧。
沿用现有每次最多 750 个结构帧的限制；超过时明确报错，不静默抽样。
不重复合并不同时间点的相同坐标，也不会丢失它们各自的晶胞。

VASP 读入后可使用已有周期晶胞显示、Boundary、扩胞、帧导航、PNG/GIF、
振动箭头、按选中原子筛选模式和几何参数曲线等界面。
完整验证见 [VALIDATION_v2.1.0.md](VALIDATION_v2.1.0.md)。本包为源码，Windows EXE 需重新构建。

格式约定参考 VASP 官方说明：

- [OUTCAR](https://vasp.at/wiki/OUTCAR)
- [XDATCAR](https://vasp.at/wiki/XDATCAR)
- [IBRION](https://vasp.at/wiki/IBRION)
- [质量加权与 SQRT(mass) 位移表](https://vasp.at/wiki/Improved_dimer_method)
