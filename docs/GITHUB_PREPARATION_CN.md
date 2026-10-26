# LELE 开发与发布

当前版本：**1.0.0**。欢迎页版本号下显示联系邮箱 **sjzhang0905@hotmail.com**。

源码仓库：[sjzhang0905/lele](https://github.com/sjzhang0905/lele)。

## 本地开发

使用 64 位 Python 3.12（或 3.11）和已获授权的仓库访问方式：

```text
git clone https://github.com/sjzhang0905/lele.git
cd lele
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\python.exe -m lele
.venv\Scripts\python.exe -m pytest tests -q
```

也可在源码目录直接运行 `start_windows.bat`。修改完成并验证后，用本机已有的 Git 作者配置提交和推送：

```text
git add .
git commit -m "Describe the change"
git push origin main
```

`.gitignore` 已排除虚拟环境、缓存和构建产物。不要将凭据或运行数据提交到源码仓库。

## 测试与 Windows 构建

推送或 PR 会触发 Tests 工作流；实际运行状态在 Actions 页面查看。

在 **Actions → Windows executable → Run workflow** 手动启动 Windows 构建。成功后下载 `LELE-windows-x64` 产物，其中应包含 `LELE.exe`、`VERSION.txt` 和 `_internal`。

本地和 GitHub Windows 构建均使用站立鹦鹉图标。文件图标可能受 Windows 缓存影响；可用改名副本确认图标是否已更新。

该工作流只保存构建产物，不自动创建 Release。分发时保留完整程序目录，先完成 Windows 原生界面和导出功能验收。

## 源码与可执行文件

本仓库用于 LELE 源码开发。原创源码、文档和素材采用根目录 `LICENSE` 中的专有许可，保留所有权利。第三方组件和依赖保留其各自许可。

单独发布的可执行文件适用 `licenses/BINARY_ONLY_LICENSE`。原来的 `standalone_Windows_executable` 仓库可继续作为可执行文件的发布入口；源码和程序包分别维护。

后续若决定采用 MIT、GPL 或其他开放源码许可，应由作者明确修改许可文件和相关说明。
