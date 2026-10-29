# LELE 开发与发布

当前版本：**1.7.0**。已在保留真实扩胞的基础上重新实现 v1.4.0/v1.5.0 功能，包含光谱、偶极与跃迁表导出、Boundary、能量单位、改进 GIF、复制粘贴和框选。恢复入口见 `docs/RESTORED_FEATURES_v1.7.0_CN.md`。欢迎页保留邮箱与仓库地址。项目采用 **MIT 协议**。

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

从 1.0.1 起，本仓库的 LELE 原创源码、文档、素材和作者分发的可执行程序采用根目录 `LICENSE` 中的 MIT 协议。分发时保留所需版权和许可声明；第三方组件和依赖继续适用其各自许可。

旧 binary-only 协议保留在 `docs/history/BINARY_ONLY_LICENSE_pre_v1.0.1.txt`，仅供历史参考，不适用于 1.0.1 及以后版本。原来的 `standalone_Windows_executable` 仓库可继续用于可执行文件发布。
