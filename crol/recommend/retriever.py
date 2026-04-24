"""
DB에서 관련 인기 영상 데이터 검색
- 음식 종류 / 키워드 기반으로 유사 영상 조회
- 제목 패턴, 해시태그 추출
"""
import json
import sqlite3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from crol_config import DB_PATH


def get_relevant_videos(food_type: str, keywords: list[str], limit: int = 30) -> list[dict]:
    """
    음식 종류 + 키워드로 관련 영상 검색 (조회수 높은 순)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 키워드 OR 조건 생성
    search_terms = [food_type] + keywords[:5]
    conditions   = " OR ".join(["title LIKE ?" for _ in search_terms])
    params       = [f"%{term}%" for term in search_terms] + [limit]

    cur.execute(f"""
        SELECT title, tags, description, view_count, is_short
        FROM videos
        WHERE is_short = 1 AND ({conditions})
        ORDER BY view_count DESC
        LIMIT ?
    """, params)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_top_shorts(limit: int = 30) -> list[dict]:
    """관련 영상이 부족할 때 fallback: 전체 쇼츠 조회수 TOP"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT title, tags, description, view_count
        FROM videos
        WHERE is_short = 1
        ORDER BY view_count DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def extract_patterns(videos: list[dict]) -> dict:
    """
    영상 목록에서 제목 패턴, 해시태그 빈도 추출
    """
    import re
    from collections import Counter

    all_hashtags: Counter = Counter()
    all_tags:     Counter = Counter()
    titles = []

    for v in videos:
        title = v.get("title", "")
        desc  = v.get("description", "")
        tags_raw = v.get("tags", "[]")

        if title:
            titles.append(title)

        # 해시태그
        hashtags = re.findall(r"#\S+", title + " " + desc)
        all_hashtags.update([h.lstrip("#").lower() for h in hashtags])

        # 태그
        try:
            tags = json.loads(tags_raw) if tags_raw else []
            all_tags.update([t.lower() for t in tags if t])
        except Exception:
            pass

    return {
        "titles"      : titles[:20],
        "top_hashtags": [tag for tag, _ in all_hashtags.most_common(25)],
        "top_tags"    : [tag for tag, _ in all_tags.most_common(25)],
    }


def retrieve(food_type: str, keywords: list[str]) -> dict:
    """전체 검색 + 패턴 추출 통합"""
    videos = get_relevant_videos(food_type, keywords, limit=30)

    # 관련 영상 부족하면 전체 TOP으로 보완
    if len(videos) < 10:
        videos += get_top_shorts(limit=20)

    patterns = extract_patterns(videos)
    print(f"[retriever] 관련 영상 {len(videos)}개 검색됨")
    return patterns
