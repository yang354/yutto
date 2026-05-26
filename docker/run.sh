#!/bin/bash
echo "🚀 正在启动 yutto Web UI 容器..."

# 检查是否存在同名容器，存在则先清理
if [ "$(docker ps -aq -f name=yutto-web)" ]; then
    echo "清理已有的 yutto-web 容器..."
    docker rm -f yutto-web
fi

# 启动容器并挂载桌面下载目录和配置目录
# 注意：若有自建 MySQL，请修改 MYSQL_HOST 等环境变量
docker run -d \
  --name yutto-web \
  -p 8765:8765 \
  -v ~/.config/yutto:/root/.config/yutto \
  -v "/Users/yyyz/Desktop/心脏信号:/downloads" \
  -e DOWNLOAD_DIR="/downloads" \
  -e MYSQL_HOST="host.docker.internal" \
  -e MYSQL_USER="root" \
  -e MYSQL_PASSWORD="mogu2018" \
  -e MYSQL_DB="yutto_webui" \
  yutto-webui:mac-m1

echo "✅ 容器启动成功！"
echo "👉 请访问: http://localhost:8765"
