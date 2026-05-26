@echo off
:: 切换至项目根目录以进行构建
cd /d "%~dp0.."

echo 📦 开始构建 Windows (amd64) 版本的 Docker 镜像...
docker build -t yutto-webui:win-amd64 -f docker/Dockerfile.webui .

echo ✅ 镜像构建成功！标签为：yutto-webui:win-amd64
pause
