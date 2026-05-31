from __future__ import annotations

import io
import logging
import os
import socket
import sqlite3
import sys
import time
from datetime import datetime, date
from logging.handlers import RotatingFileHandler

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
os.chdir(_HERE)

LOG_DIR   = os.path.join(_HERE, "logs")
LOCK_FILE = os.path.join(_HERE, ".collect.lock")
LOCK_STALE_SECONDS = 3600

os.makedirs(LOG_DIR, exist_ok=True)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

log = logging.getLogger("collect_once")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

_log_path = os.path.join(LOG_DIR, f"collect_{date.today().isoformat()}.log")
_fh = RotatingFileHandler(_log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
_fh.setFormatter(_fmt)
log.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
log.addHandler(_sh)


def has_network(timeout: float = 5.0) -> bool:
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53), ("youtube.com", 443)]:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def acquire_lock() -> bool:
    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < LOCK_STALE_SECONDS:
            log.warning(f"이미 수집 중인 프로세스 있음 (lock age={int(age)}s) — 종료")
            return False
        os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        f.write(f"{os.getpid()}\n{datetime.now().isoformat()}\n")
    return True


def release_lock() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def get_db_stats() -> dict:
    """DB 현재 상태 반환 (총 영상 수, 오늘 수집 수)"""
    try:
        from crol_config import DB_PATH
        if not os.path.exists(DB_PATH):
            return {"total": 0, "today": 0}
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM videos")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM videos WHERE DATE(snapshot_at) = ?", (date.today().isoformat(),))
        today = cur.fetchone()[0]
        conn.close()
        return {"total": total, "today": today}
    except Exception:
        return {"total": 0, "today": 0}


def step(name: str, fn, *args, **kwargs):
    log.info(f"[STEP] {name} 시작")
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        log.info(f"[STEP] {name} 완료 ({time.time()-t0:.1f}s)")
        return True, result
    except Exception as e:
        log.exception(f"[STEP] {name} 실패: {e}")
        return False, None


def main() -> int:
    log.info("=" * 60)
    log.info(f"[START] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not has_network():
        log.error("네트워크 연결 없음 → 종료")
        return 2

    if not acquire_lock():
        return 3

    try:
        # 수집 전 DB 상태
        before = get_db_stats()
        if before["today"] > 0:
            log.info(f"[INFO] 오늘 이미 {before['today']}개 수집됨 (누적: {before['total']:,}개) — 재수집 진행")
        else:
            log.info(f"[INFO] 현재 DB 누적: {before['total']:,}개")

        from db.database import init_db
        from collect.youtube import run_collection
        from collect.keywords import update_trend_keywords
        from analyze.analyzer import analyze_date

        ok_count = 0
        if step("DB 초기화", init_db)[0]:             ok_count += 1
        if step("트렌드 키워드 갱신", update_trend_keywords, force=True)[0]: ok_count += 1

        ok, snapshot_at = step("YouTube 수집", run_collection)
        if ok and snapshot_at:
            ok_count += 1
            step("일일 분석", analyze_date, snapshot_at[:10])

        # 수집 후 DB 상태 비교
        after = get_db_stats()
        added = after["total"] - before["total"]
        log.info(f"[DB] 오늘 수집: {after['today']:,}개 | 신규 추가: +{added:,}개 | 누적 총합: {after['total']:,}개")
        log.info(f"[END] 성공 단계 {ok_count}/4")
        return 0 if ok_count >= 3 else 1

    finally:
        release_lock()
        log.info("[BYE] " + "=" * 56)


if __name__ == "__main__":
    sys.exit(main())
