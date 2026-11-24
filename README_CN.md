# LELE

**Local Environment and Lattice Explorer（局域环境与晶格探索工具）** 是一款用于查看分子、晶体结构和计算化学结果的桌面软件。

[在线使用手册](https://sjzhang0905.dpdns.org/lele/manual/) · [更新记录](CHANGELOG.md) · [English](README.md)

## Windows 启动

安装 64 位 CPython 3.12 或 3.11，完整解压源码包后双击 `start_windows.bat`。启动脚本会创建环境、安装依赖并打开 LELE。

如需生成 Windows 可执行程序，首次成功启动后运行 `build_windows.bat`。分发时保留完整的 `dist/LELE` 文件夹。

## 从源码运行

```bash
python -m pip install -e ".[test]"
python -m lele
```

运行测试可使用 `python -m pytest tests -q`。

## 项目信息

[源码仓库](https://github.com/sjzhang0905/lele) · [开发与发布说明](docs/GITHUB_PREPARATION_CN.md) · [联系作者](mailto:sjzhang0905@hotmail.com)

[MIT 许可证](LICENSE) · [第三方声明](SOURCE_NOTICE.md)
