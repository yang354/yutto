# yutto Web UI Docker 部署与启动指南

本指南详细介绍了如何使用 Docker 及 Docker Compose 构建与运行 yutto Web UI。

---

## 目录
0. [准备工作（环境要求）](#零-准备工作环境要求)
1. [Mac M1 (arm64) 部署步骤](#一-mac-m1-arm64-部署步骤)
2. [Windows (amd64) 部署步骤](#二-windows-amd64-部署步骤)
3. [常见问题与说明](#三-常见问题与说明)

---

## 零、 准备工作（环境要求）

在运行任何构建命令之前，请确保您的电脑上已安装并启动了 **Docker**。

- **Mac 用户**：
  - 请下载并安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) (选择 Apple Chip 版本)。
  - 或者使用 Homebrew 安装：
    ```bash
    brew install --cask docker
    ```
  - **提示**：安装后必须从应用程序中打开 **Docker Desktop**，确保其在后台运行（可以在顶部菜单栏看到小鲸鱼图标）。

---

## 一、 Mac M1 (arm64) 部署步骤

如果您在 Mac M1/M2/M3 等 Apple Silicon 芯片的设备上运行，可选择以下三种方式：

### 方法 A：使用自动化 Shell 脚本启动 (极简推荐 ⭐⭐⭐)

为了方便起见，已在 `docker/` 目录下为您写好了自动化构建与启动脚本：

1. 进入 `docker` 目录：
   ```bash
   cd /Users/yyyz/Desktop/开源项目/yutto-main/docker
   ```
2. **一键构建镜像**：
   ```bash
   ./build.sh
   ```
3. **一键运行容器**：
   ```bash
   ./run.sh
   ```
   *注意：如果需要连接您本地的 MySQL 数据库，请编辑 `run.sh` 里面的 `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD` 等环境变量配置。*
4. 启动完成后，使用浏览器访问：`http://localhost:8765`

---

## 二、 Windows (amd64) 部署步骤

如果目标运行设备是一台 Windows 电脑，您可以通过 Mac 跨平台编译镜像并导出，也可以直接在 Windows 上使用源码构建。

### 方法 A：在 Mac 上打包并迁移至 Windows 启动 (推荐 ⭐)

#### 第一步：在 Mac 终端中跨平台构建 Windows 镜像并导出
1. 进入项目根目录：
   ```bash
   cd /Users/yyyz/Desktop/开源项目/yutto-main
   ```
2. 构建 amd64 镜像：
   ```bash
   docker build --platform linux/amd64 -t yutto-webui:win-amd64 -f docker/Dockerfile.webui .
   ```
3. 将镜像导出为 tar 压缩包：
   ```bash
   docker save yutto-webui:win-amd64 -o docker/yutto-webui-win.tar
   ```
4. 将生成的 `yutto-webui-win.tar` 以及 `docker-compose-win.yml` 文件复制到您的 Windows 电脑上。

#### 第二步：在 Windows 上导入并启动
1. 打开 Windows 的 PowerShell 或 CMD 命令提示符，导入镜像：
   ```cmd
   docker load -i yutto-webui-win.tar
   ```
2. 根据需要编辑 `docker-compose-win.yml`，修改 `volumes` 映射的冒号前面的路径（例如，改为 `D:/心脏信号`）。
3. 运行 Docker Compose 启动服务：
   ```cmd
   docker compose -f docker-compose-win.yml up -d
   ```
4. 访问 `http://localhost:8765` 即可开始使用。
5. 停止并移除服务：
   ```cmd
   docker compose -f docker-compose-win.yml down
   ```

---

### 方法 B：使用 Windows 自动化批处理脚本一键启动 (推荐 ⭐⭐⭐)

如果您直接在 Windows 上运行（且本地有源码及 Docker 环境），双击批处理脚本即可一键完成：

1. 进入 `docker` 目录。
2. **一键构建镜像**：双击运行 **`build.bat`** 文件（构建完成后会自动暂停提示成功）。
3. **一键运行容器**：双击运行 **`run.bat`** 文件（会自动清理旧容器，启动新容器并映射下载目录至 `C:\Users\YourUsername\Desktop\心脏信号`）。
   *注意：如果需要连接本地 MySQL 数据库，请用文本编辑器打开 `run.bat` 并修改 `MYSQL_HOST` 等环境变量。*
4. 在浏览器访问 `http://localhost:8765` 即可开始使用。

---

## 三、 常见问题与说明

1. **“command not found: docker” 报错**：
   这说明您还没有安装 Docker Desktop，或者没有把它加入到环境变量。请按照 [准备工作](#零-准备工作环境要求) 的步骤下载并启动 Docker Desktop。
2. **容器挂载路径问题**：
   后端代码默认配置的下载目录为 `/Users/yyyz/Desktop/心脏信号`。因此，通过 `-v` 或 Compose 的 `volumes` 进行映射时，冒号后面的部分必须固定为 `/Users/yyyz/Desktop/心脏信号`，冒号前面则是您实际期望保存的物理宿主机目录。
3. **端口占用**：
   如果宿主机上的 `8765` 端口已被其他服务占用，可将命令中的 `-p 8765:8765` 更改为其他端口（如 `-p 8888:8765`），随后通过新端口访问即可。
