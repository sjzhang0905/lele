# LELE 3.3.0 等值面与切片

在左侧 Field 页面加载 CUBE、VASP 体数据或已计算的轨道网格后：

1. 使用 Dataset 选择当前场；调整正负等值、颜色、透明度、显示样式（Surface、Wireframe、Points）、线宽/点大小和平滑光照。平滑光照只改变显示，不修改原始网格。
2. 通过 Independent isosurface layers 添加、删除和显示多个带符号的等值面层；每层可独立设置颜色、透明度、样式和可见性。层属于当前选中的同一个数据场，切换 Dataset 会让这些层应用于新选中的场。自定义层覆盖基础正负设置，可用 Use basic +/− controls 返回。
3. Planar slice 打开沿网格矢量平行平面的切片，可调位置、色阶、等高线与色标，并导出坐标和数值 CSV。网格轴不一定是笛卡尔 X/Y/Z；倾斜晶胞按实际网格矢量处理。大图预览会标记降采样，统计和 CSV 使用完整切片。均值是网格采样点的算术平均，不是电荷积分。
4. Export active field CUBE 导出当前场。几何以 Bohr 写出；已知的密度、轨道振幅和电势单位转换为原子单位，未知单位不猜测且会提示。CUBE 仅保存当前场和静态结构，不保存表面样式；原子电荷列设为 0，并非计算得到的电荷。

等值面正负颜色对轨道表示相位，并不直接代表电子电荷正负。不同物理场的单位和意义不同。暂未实现不同数据场的同时叠加或在一个场的等值面上映射另一个场的颜色，也未实现任意 hkl 切面。自定义层和显示设置可随 LELE 工程保存；大网格可能占用较多内存。

参考功能：[VESTA 等值面](https://jp-minerals.org/vesta/en/doc/VESTAch12.html)、[VESTA 显示样式](https://jp-minerals.org/vesta/en/doc/VESTAch5.html)、[Chemcraft Cube](https://chemcraftprog.com/help/workwithcubes.html)、[VMD Isosurface](https://www.ks.uiuc.edu/Research/vmd/vmd-1.8.5/ug/node68.html)、[VMD VolumeSlice](https://www.ks.uiuc.edu/Research/vmd/vmd-1.8.5/ug/node67.html)。
