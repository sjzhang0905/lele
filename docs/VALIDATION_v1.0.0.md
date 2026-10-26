# LELE 1.0.0 验证记录

日期：2026-10-26

## 版本内容

- 欢迎页版本号下显示 `sjzhang0905@hotmail.com`；可选择复制，点击通过 mailto 打开系统邮件客户端。
- 程序、窗口标题、Python 包元数据及 Windows 打包版本记录统一使用 1.0.0。
- 同步此前已完成的白色欢迎页、四帧瞬移动画、功能分类菜单、X/Y/Z 视角、
  手动拟合平面、原子总数、仅显示奇偶性的电子统计及站立鹦鹉图标。
- 保留远程仓库已有的专有许可、版权说明及项目链接。
- Windows 构建沿用已成功使用的直接打包入口，并包含站立鹦鹉图标。

## 本地验证

- 完整回归测试：**130 项测试通过，64 个子测试通过**，无失败、无跳过。
- 欢迎页检查验证邮箱位于版本号与打开文件按钮之间，mailto 地址与显示邮箱一致。
- 已查看实际 Qt 渲染的欢迎页标题截图，确认 1.0.0 和邮箱位置、对齐、间距正常。
  更新的 `examples/welcome_preview.png` 仅展示标题、邮箱与动画区域。
- 实际生成 `lele_explorer-1.0.0-py3-none-any.whl`，核对版本、作者邮箱、专有许可标识、
  LICENSE 文件及三个图像/图标资源均正确包含。
- 原有四帧动画、文件打开、快捷键、原子编辑、平面拟合及电子奇偶性测试继续通过。

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow python -m pytest tests -q
python -m pip wheel --no-deps --no-build-isolation . -w /tmp/lele-wheel
```

## 环境与范围

Linux、Python 3.12.14、PySide6 6.12.0、VTK 9.7.1、ASE 3.29.0。
本次未在当前环境生成 Windows EXE；Windows 生成程序仍需运行打包脚本。
此前用户已确认 0.9.5 在 Windows 上打包成功，改名副本可显示鹦鹉图标，
原文件的旧图标属于 Windows 图标缓存现象。
GitHub 自动检查和合并结果以对应 PR、提交及 Actions 记录为准。
