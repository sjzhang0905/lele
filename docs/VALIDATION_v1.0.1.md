# LELE 1.0.1 验证记录

日期：2026-10-26

## 修改内容

- 根目录 LICENSE 改为 MIT License，保留 2026 sjzhang0905 版权声明。
- 包元数据使用 `license = "MIT"`，安装包仅把根目录 LICENSE 识别为当前项目许可。
- 原 binary-only 条款归档至 `docs/history/BINARY_ONLY_LICENSE_pre_v1.0.1.txt`，
  明确不适用于 1.0.1 及以后版本；移除原活动路径。历史版本的变更、验证记录保持原意。
- 同步中英文说明和 SOURCE_NOTICE；第三方组件继续保留各自许可和版权声明。
- 欢迎页在联系邮箱下显示 `https://github.com/sjzhang0905/lele`，支持选择复制和点击打开。
- 程序、包元数据和 Windows 启动器更新为 1.0.1；Windows 分发目录增加 LICENSE 和 SOURCE_NOTICE.md。

## 验证结果

- 完整回归测试：**130 项测试通过，64 个子测试通过**，无失败、无跳过。
- Qt 界面检查确认仓库链接位于邮箱下方、打开按钮上方，链接地址正确并启用外部链接。
- 已查看实际 Qt 生成的欢迎页预览，确认版本号、邮箱、仓库地址完整显示。
- 实际生成 1.0.1 wheel，确认 `License-Expression: MIT`，且仅含一个 `License-File: LICENSE`；
  安装包中的许可文本与根目录 LICENSE 一致，不包含活动的 binary-only 许可文件。
- 在临时输出目录执行 GitHub Windows 构建使用的版本/许可复制语句，确认 VERSION.txt 为 1.0.1，
  LICENSE 和 SOURCE_NOTICE.md 均正确复制；检查本地批处理对应语句的语法与目标路径。

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow python -m pytest tests -q
python -m pip wheel --no-deps --no-build-isolation . -w /tmp/lele-wheel
```

## 环境与范围

Linux、Python 3.12.14、PySide6 6.12.0、VTK 9.7.1、ASE 3.29.0。
本次未在当前环境构建 Windows EXE；GitHub 自动检查和合并结果以相应 PR、提交和 Actions 记录为准。
