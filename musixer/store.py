import json
import sqlite3
import threading
import time
import uuid

from .config import DATA_DIR

DB_PATH = DATA_DIR / "library.db"
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'song',
  parent_id TEXT,
  style TEXT NOT NULL DEFAULT '',
  lyrics TEXT NOT NULL DEFAULT '',
  params TEXT NOT NULL DEFAULT '{}',
  metas TEXT NOT NULL DEFAULT '{}',
  audio_path TEXT NOT NULL,
  cover_path TEXT NOT NULL DEFAULT '',
  video_path TEXT NOT NULL DEFAULT '',
  duration REAL NOT NULL DEFAULT 0,
  favorite INTEGER NOT NULL DEFAULT 0,
  album_id TEXT,
  persona_id TEXT,
  engine TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS albums (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS personas (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  style TEXT NOT NULL DEFAULT '',
  vocal_gender TEXT NOT NULL DEFAULT 'auto',
  reference_path TEXT NOT NULL DEFAULT '',
  source_track_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lyric_docs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  idea TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  versions TEXT NOT NULL DEFAULT '[]',
  updated_at REAL NOT NULL
);
"""

JSON_FIELDS = {"params", "metas", "versions"}


def conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.executescript(SCHEMA)
        _local.conn = c
    return c


def new_id():
    return uuid.uuid4().hex[:12]


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_FIELDS & d.keys():
        try:
            d[k] = json.loads(d[k])
        except (TypeError, ValueError):
            pass
    return d


def _enc(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def insert(table, values):
    values = dict(values)
    values.setdefault("id", new_id())
    if table == "lyric_docs":
        values.setdefault("updated_at", time.time())
    else:
        values.setdefault("created_at", time.time())
    cols = ", ".join(values)
    qs = ", ".join("?" for _ in values)
    c = conn()
    c.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", [_enc(v) for v in values.values()])
    c.commit()
    return get(table, values["id"])


def get(table, id_):
    return _row(conn().execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone())


def update(table, id_, values):
    if not values:
        return get(table, id_)
    if table == "lyric_docs":
        values = {**values, "updated_at": time.time()}
    sets = ", ".join(f"{k} = ?" for k in values)
    c = conn()
    c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [_enc(v) for v in values.values()] + [id_])
    c.commit()
    return get(table, id_)


def delete(table, id_):
    c = conn()
    c.execute(f"DELETE FROM {table} WHERE id = ?", (id_,))
    c.commit()


def query(table, where="", args=(), order="created_at DESC", limit=500):
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {int(limit)}"
    return [_row(r) for r in conn().execute(sql, args).fetchall()]
