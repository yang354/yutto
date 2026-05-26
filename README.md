# yutto-enhanced (基于 yutto 的增强版)

<p align="center">
   <img src="./docs/public/logo.png" width="400px">
</p>

<p align="center"><strong>🧊 yutto，一个可爱且任性的 B 站视频下载器（支持 CLI 与 Web UI）</strong></p>

## 🌟 增强版新特性

本项目在原 yutto 命令行工具的基础上进行了深度增强，主要新增了以下实用功能：

- **🎨 可视化 Web UI**：自带基于 FastAPI 的现代化网页端操作界面，支持创建、管理、查看下载任务。
- **📁 智能文件分类**：新增 `--auto-classify` 选项，下载时自动按照 `分区/UP主/视频名` 进行目录归类。
- **🐳 Docker 一键部署**：提供完整的 Docker 镜像构建和一键启动脚本，支持跨平台轻松部署 Web 服务。
- **🗑️ 增强的文件管理**：可在网页端直接浏览已下载文件，并一键调用本地文件管理器定位真实文件位置（仅本地启动支持）。

## 什么是 yutto？

yutto 是一个 B 站视频下载器，它可以帮助你下载 B 站上的投稿视频、番剧、课程等资源，支持单个视频下载、批量下载、弹幕生成等功能。

### 命令行使用示例

```bash
❯ yutto https://www.bilibili.com/video/BV1CTMHziEaB/
 INFO  发现配置文件 yutto.toml，加载中……
 大会员  成功以大会员身份登录～
 投稿视频  《原神》动画短片——「尘间星旅」
 INFO  开始处理视频 《原神》动画短片——「尘间星旅」
 ...
```

## 🚀 快速开始

### 1. 启动 Web UI (推荐)

如果你想通过网页端来下载视频，可以直接启动 Web UI：

```bash
cd webui
sh start.sh
```

启动后，访问 `http://localhost:8765` 即可打开控制台，在页面上粘贴 B 站链接即可一键下载，并支持在基础选项中开启“智能分类”。

### 2. Docker 部署 Web UI

如果你有一台服务器或 NAS，可以使用 Docker 进行部署：

```bash
cd docker
sh build.sh
sh run.sh
```
挂载目录详情可查看 `docker/Docker部署指南.md`。

### 3. 命令行直接安装 (CLI 模式)

> [!TIP]
>
> 在此之前请确保安装 Python3.10 及以上版本，并配置好 FFmpeg。

```bash
uv tool install yutto   # 推荐使用 uv 或 pipx 安装
# 或者
pip install yutto
```

## 💡 主要命令行功能

yutto 的基本命令如下：

```bash
yutto <url>
```

你可以通过 `yutto -h` 查看详细命令参数。

**单个视频下载：**
```bash
yutto https://www.bilibili.com/bangumi/play/ep395211
# 或者简化版
yutto ep395211
```

**批量下载：**
使用 `-b/--batch` 批量下载剧集或合集：
```bash
yutto --batch https://www.bilibili.com/bangumi/play/ep395211
```

**智能分类下载：**
```bash
yutto <url> --auto-classify
```

## 参与贡献

欢迎提交 Issue 或 Pull Request！

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解更多细节。
