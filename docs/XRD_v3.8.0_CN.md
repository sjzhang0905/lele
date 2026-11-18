# 结构模拟粉末 XRD

在加载具有三维周期晶胞的结构后，通过 Analysis 菜单打开 Powder XRD。
使用当前帧的实际晶胞、坐标和占据率，不使用 Boundary 的显示复制范围。
窗口持有打开时的结构快照；后续编辑结构后，重新打开窗口以更新结构。

## 可调参数与导出

- 单色波长：Cu Kα1（默认 1.54056 Å）、Mo Kα1、Co Kα1、Cr Kα1，或自定义。
- 2θ 起止角、采样步长、Gaussian / Lorentzian 峰形和 FWHM。
- Lorentz–polarization 校正开关、统一的各向同性 B 因子（Å²）。
- 显示反射标记及最强的 12 个峰的 hkl 标签。
- 反射表提供峰位、d 间距、归一化积分强度、重合的倒易点数以及 Miller 指数。
- SVG 优先；光栅图通过统一出图窗口选择分辨率和平滑。
- 导出可编辑的 2θ–强度曲线 CSV 和反射表 CSV。反射表还包含未归一化的模型强度。

点击 Calculate pattern 更新结果。取消计算或输入参数无效时保留上一份结果，
状态栏明确说明；导出的始终是当前已计算结果。
反射积分强度与展宽曲线分别归一化至最大值 100。
步长建议不大于 FWHM/5，以免较窄峰出现采样误差。

## 计算方法

晶胞矩阵 A 按行存放直接晶格矢量（Å），倒易矩阵 B = inv(A).T，不含 2π。
枚举指定 2θ 范围内的全部整数 (h,k,l)，包括所有等价方向和 Friedel 对：

    g = (h,k,l) B
    d = 1 / |g|
    2θ = 2 asin(λ / (2d))
    s = sin(θ) / λ = 1 / (2d)
    f0(s) = Z − 41.78214 s² Σ_i a_i exp(−b_i s²)
    F(hkl) = Σ_sites Σ_species occupancy × f0(s) × exp(−Biso s²)
             × exp[2πi(hx + ky + lz)]
    I(hkl) = |F(hkl)|²

其中 x,y,z 为分数坐标。占据率作用于振幅，因此混合占据和部分空位不会被
整数化为最大占据元素。打开校正时再乘以

    LP(θ) = [1 + cos²(2θ)] / [sin²(θ) cos(θ)]。

相差小于 1e-5 度的峰位合并，并累加强度。由于已经遍历全部倒易点，
不再额外乘一次多重性。表中的倒易点数包括偶然重合的不同反射，
并不假定它们都属于同一个空间群等价族。
展宽采用统一 FWHM；反射表强度对应展宽前的积分权重。

## 范围与限制

这是从已知结构计算理论粉末谱，不是以实验谱反推结构的 Rietveld 精修。
不包含择优取向、异常散射、Kα 双线、仪器零点/轴向发散、尺寸/应变展宽、
多相含量优化或 CIF 中的各向异性热振动张量。默认 B=0，可手动指定一个
统一 B；它不代表自动读取了原结构的原子位移参数。

计算以完整的当前晶胞为准，CIF 的对称展开由已有导入器完成。
含真空层的表面模型仍被作为真空方向重复的三维晶体，不等于基底体相粉末谱。
当前散射系数覆盖 H–Cf 的中性元素（另含 D）；不支持的元素会明确报错。

计算有进度和取消支持；不会静默截断倒易点。超过 2000 万个候选倒易点或
25 万个曲线采样间隔时要求减小计算范围、改用较小原胞或增大采样步长。

## 来源与许可

方法参考 pymatgen XRDCalculator 的公开数学说明：
https://pymatgen.org/pymatgen.analysis.diffraction.html

VESTA 对粉末衍射模拟的说明：
https://jp-minerals.org/vesta/en/doc/VESTAch14.html

中性原子系数直接取自 pymatgen 的 atomic_scattering_params.json，数值未修改：
https://github.com/materialsproject/pymatgen/blob/master/src/pymatgen/analysis/diffraction/atomic_scattering_params.json

下载日期：2026-11-10；原 JSON SHA-256：
c675301248bb86ea359428f20c3987d719b1ac1a779166ef27e1d0f652467d93

系数随 lele/xrd_scattering.py 提供，其模块注释包含原项目完整 MIT 许可和版权声明。
LELE 的倒易点枚举、UI、曲线生成和导出代码为本项目实现，不需要安装 pymatgen。

## 本次验证

自动测试覆盖简单立方多重性、Bragg 角、BCC 消光、金刚石 Si 的前三个峰位
及 200 消光、部分/混合占据的相干振幅权重、斜晶胞、整体旋转和平移不变性、
B 与 LP 校正、曲线/表格 CSV、取消计算及非周期结构拒绝。
另使用 Qt offscreen 打开 Si 衍射窗口并检查图表、参数和导出控件布局。
