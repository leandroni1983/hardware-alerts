import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / 'data'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'conversations.db'

# Debug: print DB path on import to help diagnose where the file is created
try:
    print(f"[conversations] DB_PATH = {DB_PATH}")
except Exception:
    pass


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            chat_id TEXT PRIMARY KEY,
            stage TEXT,
            data TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def set_state(chat_id: str, stage: str, data: dict | None):
    _ensure_table()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "REPLACE INTO conversations (chat_id, stage, data, updated_at) VALUES (?, ?, ?, ?)",
            (str(chat_id), stage, json.dumps(data or {}), datetime.utcnow().isoformat()),
        )
        # Debug log
        try:
            print(f"[conversations] set_state chat_id={chat_id} stage={stage} data={data}")
        except Exception:
            pass
    except Exception as e:
        print('[conversations] set_state error:', e)
    conn.commit()
    conn.close()


def get_state(chat_id: str) -> dict | None:
    _ensure_table()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT stage, data FROM conversations WHERE chat_id = ?", (str(chat_id),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    try:
        data = json.loads(row['data']) if row['data'] else {}
    except Exception:
        data = {}
    try:
        print(f"[conversations] get_state chat_id={chat_id} -> stage={row['stage']} data={data}")
    except Exception:
        pass
    return {'stage': row['stage'], 'data': data}


def clear_state(chat_id: str):
    _ensure_table()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM conversations WHERE chat_id = ?", (str(chat_id),))
    conn.commit()
    conn.close()
    try:
        print(f"[conversations] clear_state chat_id={chat_id}")
    except Exception:
        pass
