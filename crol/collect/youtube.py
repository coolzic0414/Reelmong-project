"""
YouTube Data API 수집기 — 음식 쇼츠 전용
"""
import json
import re
import sys
import os
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from crol_config import YOUTUBE_API_KEY, REGION_CODE, MAX_RESULTS_POPULAR, MAX_RESULTS_SEARCH
from collect.keywords import get_active_keywords
from db.database import upsert_video


def _build_service():
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def _is_short(duration: str, title: str) -> bool:
    if "#shorts" in title.lower() or "#short" in title.lower():
        return True
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if match:
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        return h * 3600 + m * 60 + s <= 60
    return False


def _fetch_video_details(service, video_ids: list[str]) -> dict:
    result = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        resp  = service.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(chunk),
        ).execute()
        for item in resp.get("items", []):
            result[item["id"]] = item
    return result


def _days_ago_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_row(vid: str, item: dict, snapshot_at: str, source: str, keyword: str | None) -> dict:
    snippet  = item.get("snippet", {})
    stats    = item.get("statistics", {})
    content  = item.get("contentDetails", {})
    duration = content.get("duration", "PT0S")
    title    = snippet.get("title", "")
    return {
        "id"           : vid,
        "snapshot_at"  : snapshot_at,
        "source"       : source,
        "keyword"      : keyword,
        "title"        : title,
        "description"  : snippet.get("description", ""),
        "tags"         : json.dumps(snippet.get("tags", []), ensure_ascii=False),
        "channel"      : snippet.get("channelTitle", ""),
        "view_count"   : int(stats.get("viewCount", 0)),
        "like_count"   : int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "published_at" : snippet.get("publishedAt", ""),
        "duration"     : duration,
        "is_short"     : int(_is_short(duration, title)),
    }


def collect_popular(snapshot_at: str):
    service, video_ids, next_page, collected = _build_service(), [], None, 0
    while collected < MAX_RESULTS_POPULAR:
        kwargs = dict(part="id", chart="mostPopular", regionCode=REGION_CODE,
                      maxResults=min(50, MAX_RESULTS_POPULAR - collected))
        if next_page:
            kwargs["pageToken"] = next_page
        resp       = service.videos().list(**kwargs).execute()
        ids        = [item["id"] for item in resp.get("items", [])]
        video_ids.extend(ids)
        collected += len(ids)
        next_page  = resp.get("nextPageToken")
        if not next_page:
            break

    details = _fetch_video_details(service, video_ids)
    for vid, item in details.items():
        upsert_video(_build_row(vid, item, snapshot_at, "popular", None))
    print(f"[youtube] popular: {len(details)}개 저장")


def collect_food_search(snapshot_at: str):
    service  = _build_service()
    keywords = get_active_keywords()
    print(f"[youtube] 활성 키워드 {len(keywords)}개로 수집")

    for keyword in keywords:
        try:
            resp = service.search().list(
                part="id",
                q=keyword + " #shorts",
                type="video",
                videoDuration="short",
                order="viewCount",
                regionCode=REGION_CODE,
                relevanceLanguage="ko",
                maxResults=MAX_RESULTS_SEARCH,
                publishedAfter=_days_ago_iso(7),
            ).execute()

            video_ids = [item["id"]["videoId"] for item in resp.get("items", [])
                         if item.get("id", {}).get("kind") == "youtube#video"]
            details   = _fetch_video_details(service, video_ids)
            for vid, item in details.items():
                upsert_video(_build_row(vid, item, snapshot_at, "search", keyword))
            print(f"[youtube] '{keyword}': {len(video_ids)}개 저장")
        except Exception as e:
            print(f"[youtube] '{keyword}' 오류: {e}")


def run_collection():
    snapshot_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n=== 수집 시작: {snapshot_at} ===")
    collect_popular(snapshot_at)
    collect_food_search(snapshot_at)
    print(f"=== 수집 완료 ===\n")
    return snapshot_at
