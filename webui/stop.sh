#!/bin/bash
# yutto Web UI 停止脚本

echo "🧊 正在检测并停止 yutto Web UI 服务..."

# 查找占用 8765 端口的进程 PID
PID=$(lsof -t -i:8765)

if [ -z "$PID" ]; then
    # 尝试通过进程名称查找 server.py
    PID=$(pgrep -f "python.*server.py")
fi

if [ -n "$PID" ]; then
    echo "发现运行中的服务 PID: $PID"
    kill $PID
    sleep 1
    # 确认是否已成功停止
    if lsof -i:8765 >/dev/null 2>&1; then
        echo "⚠️ 正常停止失败，正在强制结束进程..."
        kill -9 $PID
    fi
    echo "✅ 服务已停止！"
else
    echo "ℹ️ 未发现正在运行的 yutto Web UI 服务 (端口 8765)。"
fi
