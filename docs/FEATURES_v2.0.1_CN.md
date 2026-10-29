# LELE v2.0.1

底部显示示例：

`Atoms 32 | Composition C8H16O8 | electrons even | Short contacts 0`

- 周期体系的 **Cell composition** 简写为 **Composition**；孤立体系保留 **Formula**。
- 电子奇偶性只显示 **electrons even / odd**；未知元素显示 **electrons unknown**。
  将鼠标放在摘要上，仍能查看电荷是否来自文件、手动设置或默认中性假设。
- 底部摘要与键长、键角、二面角信息均省略冒号。
- **Short contacts** 只显示数量，不再显示阈值、最近原子对或距离。

## 查看 Short contacts

点击底部带下划线的 **Short contacts 数量**，弹窗列出原子编号、元素及距离。
周期性体系额外显示第二个原子的晶格平移 `(a, b, c)`，例如 `-1 0 0` 表示减去一个 a 晶格向量。
该平移相对于原始坐标，原子坐标即使没有包裹回主晶胞，也能据此还原接触距离。

沿用原有 `distance < 0.60 Å` 检查，阈值仅在详情窗口说明。
每个源原子对只计算其最短周期像一次，Boundary 显示副本不会重复增加数量。
数量为 0 时也可点击，窗口会说明当前没有 Short contacts。

窗口显示打开时那一帧的快照，并在顶部标明文件名及帧号/频率参考段。
切换帧后，底部数量会更新；已打开的详情保持原快照，便于对照。

## 周期性体系体积

**Results / info** 在晶胞向量后列出 **Cell volume**，单位 Å³。
体积使用晶格向量矩阵行列式的绝对值，适用于斜晶胞，并随当前帧/扩胞更新。
非周期体系不显示晶胞体积，附带的体数据网格大小仍单独列出。

本版为源码包。Windows EXE 需重新运行 `build_windows.bat` 构建。
