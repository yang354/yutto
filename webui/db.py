from __future__ import annotations

import json
import os

import aiomysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "mogu2018")
MYSQL_DB = os.environ.get("MYSQL_DB", "yutto_webui")

pool = None

async def init_db():
    global pool
    try:
        # First connect without DB to create it if not exists
        conn = await aiomysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
        async with conn.cursor() as cur:
            await cur.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.close()

        pool = await aiomysql.create_pool(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, db=MYSQL_DB, autocommit=True
        )

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id VARCHAR(32) PRIMARY KEY,
                        url TEXT,
                        status VARCHAR(32),
                        progress FLOAT,
                        cmd TEXT,
                        created_at FLOAT,
                        params JSON,
                        downloaded_files JSON,
                        logs JSON
                    )
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        k VARCHAR(64) PRIMARY KEY,
                        v TEXT
                    )
                """)
        print(f"✅ 连接 MySQL 成功 (DB: {MYSQL_DB})")
    except Exception as e:
        print(f"❌ 连接 MySQL 失败: {e}")
        pool = None

async def load_tasks():
    if not pool: return {}
    tasks_dict = {}
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM tasks")
            rows = await cur.fetchall()
            for r in rows:
                if r['status'] in ('running', 'pending', 'paused'):
                    r['status'] = 'error' # Mark interrupted tasks as error
                    r['logs'] = json.loads(r['logs'])
                    r['logs'].append("❌ 服务意外重启，任务终止")
                else:
                    r['logs'] = json.loads(r['logs'])
                r['params'] = json.loads(r['params'])
                r['downloaded_files'] = json.loads(r['downloaded_files'])
                r['process'] = None
                tasks_dict[r['id']] = r
    return tasks_dict

async def save_task(t):
    if not pool: return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO tasks (id, url, status, progress, cmd, created_at, params, downloaded_files, logs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                status=VALUES(status), progress=VALUES(progress), downloaded_files=VALUES(downloaded_files), logs=VALUES(logs)
            """, (
                t['id'], t['url'], t['status'], t['progress'], t['cmd'], t['created_at'],
                json.dumps(t['params']), json.dumps(t['downloaded_files']), json.dumps(t['logs'])
            ))

async def delete_task_db(task_id):
    if not pool: return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))

async def load_config(k: str, default=None):
    if not pool: return default
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT v FROM config WHERE k = %s", (k,))
            row = await cur.fetchone()
            return row[0] if row else default

async def save_config(k: str, v: str):
    if not pool: return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO config (k, v) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE v=VALUES(v)
            """, (k, v))
