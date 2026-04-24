import sqlite3
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from crol_config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 수집된 영상 원본 데이터
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id            TEXT NOT NULL,
            snapshot_at   TEXT NOT NULL,
            source        TEXT,
            keyword       TEXT,
            title         TEXT,
            description   TEXT,
            tags          TEXT,
            channel       TEXT,
            view_count    INTEGER,
            like_count    INTEGER,
            comment_count INTEGER,
            published_at  TEXT,
            duration      TEXT,
            is_short      INTEGER,
            PRIMARY KEY (id, snapshot_at)
        )
    """)

    # 일별 집계
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date               TEXT PRIMARY KEY,
            top_title_patterns TEXT,
            top_tags           TEXT,
            top_hashtags       TEXT,
            top_keywords       TEXT,
            created_at         TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] 초기화 완료")


# ── videos ──────────────────────────────────────────────────────────
def upsert_video(row: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO videos
        (id, snapshot_at, source, keyword, title, description, tags, channel,
         view_count, like_count, comment_count, published_at, duration, is_short)
        VALUES (:id, :snapshot_at, :source, :keyword, :title, :description, :tags,
                :channel, :view_count, :like_count, :comment_count, :published_at,
                :duration, :is_short)
    """, row)
    conn.commit()
    conn.close()


def get_videos_for_date(date: str) -> list[dict]:
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM videos WHERE snapshot_at LIKE ?", (f"{date}%",))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── daily_stats ──────────────────────────────────────────────────────
def save_daily_stats(date: str, stats: dict):
    import json
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO daily_stats
        (date, top_title_patterns, top_tags, top_hashtags, top_keywords, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        date,
        json.dumps(stats.get("top_title_patterns", []), ensure_ascii=False),
        json.dumps(stats.get("top_tags", []), ensure_ascii=False),
        json.dumps(stats.get("top_hashtags", []), ensure_ascii=False),
        json.dumps(stats.get("top_keywords", []), ensure_ascii=False),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def get_latest_daily_stats() -> dict | None:
    import json
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for key in ("top_title_patterns", "top_tags", "top_hashtags", "top_keywords"):
        d[key] = json.loads(d[key])
    return d
