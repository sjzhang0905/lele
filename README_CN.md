# LELE

**Local Environment and Lattice Explorer — 局域环境与晶格探索工具**

当前版本：**0.9.1**。本版从 ChemView Studio 0.9.0 统一改名为 LELE，Python 包名为 `lele`，Windows 程序名为 `LELE.exe`。

## 当前功能

- 分子、晶体、计算输入和输出的结构读取与格式转换，沿用 ChemStructConverter 后端及 ASE。
- 九种显示风格、自定义元素颜色、预设保存、标签、晶胞和 XYZ/abc 坐标轴。
- 多选、片段选择、反选、删除、撤销和坐标编辑；距离、键角和二面角测量。
- 选中三个及以上非共线原子后自动拟合平面；支持周期镜像和将完整结构、晶胞及附带网格刚性对齐到 XY。
- 支持的轨迹文件逐帧浏览和播放，包括 SIESTA 输出/ANI 历史；有相应能量数据时绘制能量曲线。
- 几何氢键候选、短距离检查、CUBE 正负等值面和 PNG 截图。

轨迹帧数、能量等内容取决于文件本身及读取器。结构编辑只作用于当前帧；保存修改后的坐标请使用 `Export structure`。

## 后续规划

表面、碳材料和异质结构构建，更多旋转矩阵工具，以及 AIMD 自动分析、科学绘图和 SVG 出图属于后续开发内容，**本版尚未集成**。

## Windows 启动与打包

1. 使用 64 位 Python 3.12，或 3.11，解压完整源码目录。
2. 双击 `start_windows.bat`，自动建立环境、安装依赖并启动。
3. 窗口标题应为 `LELE 0.9.1 - Local Environment and Lattice Explorer`。
4. 首次成功启动后，可运行 `build_windows.bat`。新程序位于 `dist\LELE\LELE.exe`，分发时保留整个 `dist\LELE` 文件夹及其 `_internal` 内容。

从已配置好的开发环境也可执行：

```text
python -m pip install -e ".[test]"
python -m lele
python -m pytest tests -q
```

## 常用操作

| 操作 | 方式 |
|---|---|
| 打开结构 | Ctrl+O，或拖入文件 |
| 原子多选 | 三维画布逐个单击，或在坐标表选择多行 |
| 反选 | Ctrl+I |
| 删除选中原子 | Delete；输入框内仍用于删除文字 |
| 撤销结构编辑 | Ctrl+Z |
| 选中相连片段 | Ctrl+G |
| 切换选中原子之间的成键 | Ctrl+B |
| 自动拟合平面 | 选择至少三个非共线原子，在 Edit 中操作 |
| 导出结构 | Ctrl+Shift+S |
| 保存截图 | Ctrl+S，当前为 PNG |

## 配置与版本历史

LELE 使用独立、固定的 Qt 应用配置目录。首次运行时会尝试从原 ChemViewStudio 或旧启动入口目录复制有效的显示预设；已有 LELE 配置优先，旧文件保留。

历史说明和旧验收结果已归档到 `docs/history`。转换后端继续使用 ChemStructConverter 的原名称。

## GitHub 准备

源码仓库为 [sjzhang0905/lele](https://github.com/sjzhang0905/lele)。本目录包含标准 Python 项目元数据、Git 忽略规则、换行规则，以及 GitHub Actions 测试和 Windows 打包定义。详细操作见 [开发与发布说明](docs/GITHUB_PREPARATION_CN.md)，实际工作流状态请在仓库的 Actions 页面查看。

## 许可

LELE 原创源码、文档和素材采用**专有许可，保留所有权利**，不是 MIT/GPL 等开源发布。使用、修改或再分发需要作者书面许可，详见 [LICENSE](LICENSE)。

`licenses/BINARY_ONLY_LICENSE` 适用于单独发布的可执行文件。第三方组件和依赖保留各自的许可，见 `SOURCE_NOTICE.md`。
