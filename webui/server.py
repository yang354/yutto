"""
yutto Web UI - FastAPI Backend Server
通过 WebSocket 实时推送 yutto 下载进度
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import time
import uuid
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from yutto.auth import resolve_auth, resolve_auth_file, save_auth
from yutto.login import (
    QR_POLL_API,
    QR_STATUS_CONFIRMED,
    QR_STATUS_EXPIRED,
    QR_STATUS_NOT_SCANNED,
    QR_STATUS_SCANNED,
    complete_login,
    generate_qr_login,
)
from yutto.utils.fetcher import FetcherContext, create_sync_client

# ── 路径配置 ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent           # webui/
ROOT_DIR = BASE_DIR.parent                 # yutto-main/
STATIC_DIR = BASE_DIR / "static"
DOWNLOADS_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/Users/yyyz/Desktop/心脏信号"))
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
global_config = {
    "MAX_CONCURRENT_TASKS": int(os.environ.get("MAX_CONCURRENT_TASKS", 3))
}

from db import delete_task_db, init_db, load_config, load_tasks, save_config, save_task

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(title="yutto Web UI", version="1.0.0")

class DummyArgs:
    auth_profile = "default"
    auth_file = None
    auth = None
    config = None
    proxy = "auto"

@app.get("/api/auth/qrcode")
async def get_qrcode():
    ctx = FetcherContext()
    ctx.set_proxy("auto")
    with create_sync_client(proxy=ctx.proxy, trust_env=ctx.trust_env, timeout=10, verify=True) as client:
        try:
            url, qrcode_key = generate_qr_login(client)
            return {"url": url, "qrcode_key": qrcode_key}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/auth/poll")
async def poll_qrcode(qrcode_key: str):
    ctx = FetcherContext()
    ctx.set_proxy("auto")
    with create_sync_client(proxy=ctx.proxy, trust_env=ctx.trust_env, timeout=10, verify=True) as client:
        try:
            payload = client.get(QR_POLL_API, params={"qrcode_key": qrcode_key, "source": "main-fe-header"}).json()
            code = payload.get("code")
            if code != 0:
                return {"status": "error", "message": f"轮询登录状态失败: {payload}"}

            data = payload.get("data", {})
            status_code = data.get("code")

            if status_code == QR_STATUS_NOT_SCANNED:
                return {"status": "pending", "message": "二维码待扫描"}
            elif status_code == QR_STATUS_SCANNED:
                return {"status": "scanned", "message": "已扫码，请在 App 内确认登录"}
            elif status_code == QR_STATUS_EXPIRED:
                return {"status": "expired", "message": "二维码已过期"}
            elif status_code == QR_STATUS_CONFIRMED:
                redirect_url = data.get("url")
                result_url, sessdata, bili_jct = complete_login(client, redirect_url)
                if not sessdata:
                    return {"status": "error", "message": "登录成功但未提取到 SESSDATA"}

                args = DummyArgs()
                auth_file = resolve_auth_file(args)
                save_auth(auth_file, "default", sessdata, bili_jct)
                return {"status": "confirmed", "message": "登录成功"}

            return {"status": "unknown", "message": f"未知状态码: {status_code}"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/auth/status")
async def get_auth_status():
    ctx = FetcherContext()
    ctx.set_proxy("auto")
    args = DummyArgs()
    try:
        auth = resolve_auth(args)
    except Exception:
        auth = None

    if not auth:
        return {"is_login": False}

    try:
        # 真正获取 B 站用户名和头像
        from yutto.api.user_info import USER_INFO_API
        from yutto.login import request_json
        ctx.set_auth_info(auth)
        with create_sync_client(cookies=ctx.cookies, proxy=ctx.proxy, trust_env=ctx.trust_env, verify=True) as client:
            res_json = request_json(client, USER_INFO_API, params={})
            data = res_json.get("data", {})
            return {
                "is_login": bool(data.get("isLogin")),
                "uname": data.get("uname", "已登录用户"),
                "face": data.get("face"),
                "vip": data.get("vipStatus") == 1,
            }
    except Exception:
        return {"is_login": False}

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── 任务存储与后台运行器注册 ──────────────────────────────────────────────────
tasks: dict[str, dict[str, Any]] = {}
task_websockets: dict[str, list[WebSocket]] = {}

@app.on_event("startup")
async def on_startup():
    await init_db()

    # Load config from DB
    db_max_concurrent = await load_config("MAX_CONCURRENT_TASKS")
    if db_max_concurrent is not None:
        global_config["MAX_CONCURRENT_TASKS"] = int(db_max_concurrent)

    loaded = await load_tasks()
    tasks.update(loaded)
    asyncio.create_task(db_sync_loop())

async def db_sync_loop():
    """后台任务：每 5 秒将有变动的任务状态同步到数据库"""
    while True:
        await asyncio.sleep(5)
        for t in list(tasks.values()):
            if t.get("status") in ("running", "pending", "paused", "error", "done", "cancelled"):
                # 可以优化为仅变动时保存，这里为简单起见全量保存
                await save_task(t)

def schedule_tasks():
    """任务调度器：控制并发数量"""
    active_tasks = [t for t in tasks.values() if t["status"] in ("running", "paused")]
    if len(active_tasks) >= global_config["MAX_CONCURRENT_TASKS"]:
        return

    pending_tasks = [t for t in tasks.values() if t["status"] == "pending"]
    # 按创建时间先后顺序排序
    pending_tasks.sort(key=lambda x: x["created_at"])

    slots_available = global_config["MAX_CONCURRENT_TASKS"] - len(active_tasks)
    for t in pending_tasks[:slots_available]:
        asyncio.create_task(run_task_subprocess(t["id"]))


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def strip_ansi(text: str) -> str:
    """去除 ANSI 颜色转义码"""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def parse_progress(line: str) -> float | None:
    """
    从 yutto 输出行中提取进度百分比（0-100）。
    yutto 使用 rich 或自定义进度条，格式通常带有百分比数字。
    """
    # 匹配类似 " 45.25 MiB/ 54.30 MiB" 这样的进度行
    match = re.search(r"(\d+\.?\d*)\s*MiB\s*/\s*(\d+\.?\d*)\s*MiB", line)
    if match:
        done = float(match.group(1))
        total = float(match.group(2))
        if total > 0:
            return min(done / total * 100, 100)
    # 匹配百分比格式
    match = re.search(r"(\d+\.?\d*)%", line)
    if match:
        return min(float(match.group(1)), 100)
    return None


def build_yutto_command(params: dict[str, Any]) -> list[str]:
    """根据前端参数构建 yutto 命令行"""
    # 直接使用当前运行环境的 Python 解释器执行本地的 yutto 模块
    cmd = [
        sys.executable, "-m", "yutto",
    ]

    url = (params.get("url") or "").strip()
    if not url:
        raise ValueError("URL 不能为空")
    cmd.append(url)

    # 下载目录（None 时使用默认值）
    download_dir = (params.get("dir") or "").strip() or str(DOWNLOADS_DIR)
    cmd.extend(["-d", download_dir])

    # 批量下载
    if params.get("batch"):
        cmd.append("--batch")

    # 视频清晰度
    quality = params.get("video_quality")
    if quality:
        cmd.extend(["-q", str(quality)])

    # 仅音频
    if params.get("audio_only"):
        cmd.append("--audio-only")

    # 不要弹幕
    if params.get("no_danmaku"):
        cmd.append("--no-danmaku")

    # 不要字幕
    if params.get("no_subtitle"):
        cmd.append("--no-subtitle")

    # 覆盖已有
    if params.get("overwrite"):
        cmd.append("--overwrite")

    # 智能分类
    if params.get("auto_classify"):
        cmd.append("--auto-classify")

    # 代理（None 时跳过）
    proxy = (params.get("proxy") or "").strip()
    if proxy:
        cmd.extend(["-x", proxy])

    # 选集范围（批量下载时有效）
    episodes = (params.get("episodes") or "").strip()
    if episodes:
        cmd.extend(["-p", episodes])

    # 不显示颜色（方便日志解析）
    cmd.extend(["--no-color"])

    # 默认优化参数：由于 32 并发和 5MB 分块过于激进极易触发 B 站防火墙限速阻断，调整为温和稳定的 8 并发和 2MB 分块
    cmd.extend(["-n", "8", "-bs", "2"])

    return cmd


# ── 广播消息到任务的 WebSockets ──────────────────────────────────────────────────
async def broadcast_to_task(task_id: str, message: dict[str, Any]):
    if task_id in task_websockets:
        disconnected = []
        for ws in task_websockets[task_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            try:
                task_websockets[task_id].remove(ws)
            except ValueError:
                pass


# ── 后台任务进程运行器 ────────────────────────────────────────────────────────────
async def run_task_subprocess(task_id: str):
    t = tasks[task_id]
    try:
        cmd = build_yutto_command(t["params"])
    except Exception as e:
        t["status"] = "error"
        t["logs"].append(f"构建命令失败: {e}")
        await broadcast_to_task(task_id, {"type": "error", "message": f"构建命令失败: {e}"})
        await broadcast_to_task(task_id, {"type": "status", "status": "error", "progress": 0})
        return

    t["status"] = "running"
    await broadcast_to_task(task_id, {"type": "cmd", "cmd": " ".join(cmd)})
    await broadcast_to_task(task_id, {"type": "status", "status": "running", "progress": 0})

    try:
        # 使用 preexec_fn=os.setsid 启动，将子进程变为新进程组的 Leader
        # 这允许我们在取消或暂停时对整个进程组发送信号，防止残留孤儿进程
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT_DIR),
            env={k: v for k, v in {**os.environ, "PYTHONUNBUFFERED": "1"}.items()
                 if k not in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")},
            preexec_fn=os.setsid,
        )
    except Exception as e:
        t["status"] = "error"
        t["logs"].append(f"启动下载进程失败: {e}")
        await broadcast_to_task(task_id, {"type": "status", "status": "error", "progress": 0})
        return

    t["process"] = proc

    async def read_output():
        assert proc.stdout is not None
        buffer = ""
        while True:
            chunk_bytes = await proc.stdout.read(4096)
            if not chunk_bytes:
                break
            buffer += chunk_bytes.decode("utf-8", errors="replace")

            while "\n" in buffer or "\r" in buffer:
                idx_n = buffer.find("\n")
                idx_r = buffer.find("\r")

                if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
                    line = buffer[:idx_n]
                    buffer = buffer[idx_n+1:]
                else:
                    line = buffer[:idx_r]
                    buffer = buffer[idx_r+1:]

                line = strip_ansi(line).rstrip()
                if not line:
                    continue

                if line.startswith("╸") or line.startswith("━"):
                    pass
                else:
                    t["logs"].append(line)

                # 从输出中解析已写入磁盘的文件路径（yutto 会打印类似 "Downloading ... to /path/to/file.mp4"）
                _file_match = re.search(
                    r"(?:保存到|Downloading.*?to|已保存|合并为|输出:|Output:)\s*([/\\].+?\.(?:mp4|flv|mkv|aac|mp3|xml|srt|ass|json))",
                    line, re.IGNORECASE
                )
                if _file_match:
                    _fpath = _file_match.group(1).strip()
                    if _fpath not in t["downloaded_files"]:
                        t["downloaded_files"].append(_fpath)

                pct = parse_progress(line)
                if pct is not None:
                    t["progress"] = round(pct, 1)

                await broadcast_to_task(task_id, {
                    "type": "log",
                    "line": line,
                    "progress": t["progress"],
                })

    try:
        await read_output()
    except Exception as e:
        t["logs"].append(f"读取下载输出异常: {e}")
    finally:
        # 等待进程结束
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # 仅在非人为主动取消/暂停状态下更改为 done 或 error
        if t["status"] not in ("cancelled", "error"):
            t["status"] = "done" if proc.returncode == 0 else "error"
            t["progress"] = 100 if t["status"] == "done" else t["progress"]

        await broadcast_to_task(task_id, {
            "type": "status",
            "status": t["status"],
            "progress": t["progress"],
            "return_code": proc.returncode,
        })

        # 触发下一次调度
        schedule_tasks()

        # 关闭对应的所有客户端 WebSockets 连接
        if task_id in task_websockets:
            for ws in list(task_websockets[task_id]):
                try:
                    await ws.close()
                except Exception:
                    pass
            task_websockets.pop(task_id, None)


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/download")
async def create_download(body: dict[str, Any]):
    task_id = str(uuid.uuid4())[:8]
    try:
        cmd = build_yutto_command(body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    tasks[task_id] = {
        "id": task_id,
        "url": body.get("url", ""),
        "status": "pending",   # pending / running / paused / done / error / cancelled
        "progress": 0,
        "logs": [],
        "cmd": " ".join(cmd),
        "created_at": time.time(),
        "params": body,
        "process": None,
        "downloaded_files": [],  # 追踪本次任务写入磁盘的文件路径
    }
    # 异步在后台执行下载
    await save_task(tasks[task_id])
    schedule_tasks()
    return {"task_id": task_id}


@app.get("/api/tasks")
async def list_tasks():
    result = []
    for t in tasks.values():
        result.append({
            "id": t["id"],
            "url": t["url"],
            "status": t["status"],
            "progress": t["progress"],
            "created_at": t["created_at"],
            "log_count": len(t["logs"]),
        })
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    return {
        "id": t["id"],
        "url": t["url"],
        "status": t["status"],
        "progress": t["progress"],
        "created_at": t["created_at"],
        "cmd": t["cmd"],
        "logs": t["logs"],
    }


def kill_task_process(t: dict):
    proc: asyncio.subprocess.Process | None = t.get("process")
    if proc and proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    if t.get("process") and t["process"].returncode is None:
        kill_task_process(t)
        msg = "已取消任务"
    elif t["status"] == "pending":
        msg = "已取消排队任务"
    else:
        return {"message": "任务不在运行中"}

    t["status"] = "cancelled"
    await broadcast_to_task(task_id, {"type": "status", "status": "cancelled", "progress": t["progress"]})
    schedule_tasks()
    return {"message": msg}

@app.get("/api/config")
async def get_config():
    return {
        "max_concurrent_tasks": global_config["MAX_CONCURRENT_TASKS"],
        "is_docker": os.path.exists("/.dockerenv")
    }

@app.post("/api/config")
async def update_config(req: Request):
    data = await req.json()
    if "max_concurrent_tasks" in data:
        val = int(data["max_concurrent_tasks"])
        global_config["MAX_CONCURRENT_TASKS"] = val
        await save_config("MAX_CONCURRENT_TASKS", str(val))
        schedule_tasks()
    return {"message": "配置已更新", "max_concurrent_tasks": global_config["MAX_CONCURRENT_TASKS"]}


@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    if t["status"] != "running":
        return JSONResponse({"error": "任务并非正在下载中"}, status_code=400)

    proc: asyncio.subprocess.Process | None = t.get("process")
    if proc and proc.returncode is None:
        try:
            # 对进程组发送 SIGSTOP 信号暂停它
            os.killpg(os.getpgid(proc.pid), signal.SIGSTOP)
            t["status"] = "paused"
            await broadcast_to_task(task_id, {"type": "status", "status": "paused", "progress": t["progress"]})
            return {"message": "已暂停任务"}
        except Exception as e:
            return JSONResponse({"error": f"暂停失败: {e}"}, status_code=500)
    return {"message": "任务进程未运行"}


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    if t["status"] != "paused":
        return JSONResponse({"error": "任务并非处于暂停状态"}, status_code=400)

    proc: asyncio.subprocess.Process | None = t.get("process")
    if proc and proc.returncode is None:
        try:
            # 对进程组发送 SIGCONT 信号恢复它
            os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
            t["status"] = "running"
            await broadcast_to_task(task_id, {"type": "status", "status": "running", "progress": t["progress"]})
            return {"message": "已继续任务"}
        except Exception as e:
            return JSONResponse({"error": f"恢复失败: {e}"}, status_code=500)
    return {"message": "任务进程未运行"}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, delete_files: bool = False):
    """
    删除任务记录。
    - delete_files=false（默认）：仅清除内存中的任务记录，保留磁盘文件。
    - delete_files=true：同时删除本次任务下载到磁盘的文件。
    """
    if task_id in tasks:
        t = tasks[task_id]
        kill_task_process(t)

        deleted_files: list[str] = []
        failed_files: list[str] = []
        if delete_files:
            # 1. 删除日志中捕获到的具体文件
            for fpath in t.get("downloaded_files", []):
                try:
                    p = Path(fpath)
                    if p.exists():
                        if p.is_dir():
                            shutil.rmtree(p)
                        else:
                            p.unlink()
                        deleted_files.append(str(p))
                except Exception as e:
                    failed_files.append(f"{fpath}: {e}")

            # 2. 如果没有精确捕获到文件路径，则扫描下载目录中创建时间 >= 任务创建时间的文件
            if not deleted_files and not failed_files:
                download_dir = Path((t["params"].get("dir") or "").strip() or str(DOWNLOADS_DIR))
                created_at = t.get("created_at", 0)
                if download_dir.exists():
                    for fp in download_dir.rglob("*"):
                        if fp.is_file() and fp.stat().st_mtime >= created_at - 5:
                            try:
                                fp.unlink()
                                deleted_files.append(str(fp))
                            except Exception as e:
                                failed_files.append(f"{fp}: {e}")

        tasks.pop(task_id, None)
        task_websockets.pop(task_id, None)
        await delete_task_db(task_id)

        if delete_files:
            msg = f"已删除任务记录及 {len(deleted_files)} 个文件"
            if failed_files:
                msg += f"（{len(failed_files)} 个文件删除失败）"
            return {"success": True, "message": msg, "deleted_files": deleted_files, "failed_files": failed_files}
        return {"success": True, "message": "已清除任务记录（文件已保留在下载目录）"}
    return JSONResponse({"error": "任务不存在"}, status_code=404)



@app.post("/api/files/open")
async def open_file_location(body: dict[str, Any]):
    rel_path = body.get("path")
    if not rel_path:
        return JSONResponse({"error": "No path provided"}, status_code=400)

    full_path = DOWNLOADS_DIR / rel_path
    if not full_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)

    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", "-R", str(full_path)], check=True)
        elif system == "Windows":
            subprocess.run(["explorer", "/select,", str(full_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(full_path.parent)], check=True)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"error": f"打开文件夹失败: {e}"}, status_code=500)


@app.get("/api/files")
async def list_files():
    """列出 downloads 目录下的文件"""
    files = []
    if DOWNLOADS_DIR.exists():
        for p in DOWNLOADS_DIR.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "path": str(p.relative_to(DOWNLOADS_DIR)),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "ext": p.suffix.lower(),
                })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return files


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{task_id}")
async def websocket_download(websocket: WebSocket, task_id: str):
    await websocket.accept()

    t = tasks.get(task_id)
    if not t:
        await websocket.send_json({"type": "error", "message": "任务不存在"})
        await websocket.close()
        return

    # 1. 回放历史命令与日志
    await websocket.send_json({"type": "cmd", "cmd": t["cmd"]})
    for log in t["logs"]:
        await websocket.send_json({"type": "log", "line": log, "progress": t["progress"]})

    # 2. 发送当前最新状态
    await websocket.send_json({"type": "status", "status": t["status"], "progress": t["progress"]})

    # 3. 如果任务已经结束，直接关闭 WebSocket 连接
    if t["status"] not in ("pending", "running", "paused"):
        await websocket.close()
        return

    # 4. 注册到订阅列表以获取实时更新
    if task_id not in task_websockets:
        task_websockets[task_id] = []
    task_websockets[task_id].append(websocket)

    # 5. 持续监听，保持连接开放直到客户端主动断开
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # 移除订阅
        if task_id in task_websockets:
            try:
                task_websockets[task_id].remove(websocket)
            except ValueError:
                pass


# ── 启动入口 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    print("🧊 yutto Web UI 启动中...")
    print(f"   项目根目录: {ROOT_DIR}")
    print(f"   下载目录:   {DOWNLOADS_DIR}")
    print("   访问地址:   http://localhost:8765")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
