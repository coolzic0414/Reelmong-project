"""
대본 텍스트에서 핵심 정보 추출
- 음식 종류, 장소, 분위기 키워드 파악
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 장소 키워드
LOCATION_WORDS = [
    "성수", "홍대", "강남", "연남", "망원", "을지로", "신촌", "이태원",
    "합정", "건대", "압구정", "청담", "여의도", "마포", "용산", "종로",
    "부산", "제주", "인천", "수원", "대전", "대구", "광주",
]

# 분위기 키워드
MOOD_WORDS = {
    "감성적": ["감성", "분위기", "뷰", "인테리어", "예쁜", "힐링"],
    "가성비": ["가성비", "저렴", "싸다", "착한가격", "합리적"],
    "프리미엄": ["오마카세", "파인다이닝", "고급", "프리미엄", "특별한"],
    "웨이팅": ["웨이팅", "줄", "예약", "인기많은", "핫한"],
    "혼밥": ["혼밥", "혼술", "혼자", "1인"],
    "데이트": ["데이트", "커플", "둘이서"],
}

# 음식 카테고리 키워드
FOOD_CATEGORY = {
    "카페/디저트": ["카페", "디저트", "케이크", "빵", "커피", "라떼", "베이커리"],
    "한식": ["한식", "비빔밥", "갈비", "삼겹살", "된장", "국밥", "김치"],
    "일식": ["스시", "라멘", "우동", "돈카츠", "오마카세", "일식"],
    "양식": ["파스타", "스테이크", "피자", "버거", "양식", "브런치"],
    "중식": ["짜장면", "짬뽕", "마라", "중식", "딤섬"],
    "분식": ["떡볶이", "순대", "튀김", "김밥", "분식"],
    "고기": ["삼겹살", "갈비", "고기", "소고기", "돼지고기", "양꼬치"],
}


def extract_info(script: str, food_type: str) -> dict:
    """
    대본 + 음식종류에서 핵심 정보 추출
    반환: {keywords, location, mood, food_category, food_type}
    """
    text = script + " " + food_type

    # 장소 추출
    location = next((w for w in LOCATION_WORDS if w in text), None)

    # 분위기 추출 (여러 개 가능)
    moods = [mood for mood, words in MOOD_WORDS.items()
             if any(w in text for w in words)]

    # 음식 카테고리 추출
    food_category = next(
        (cat for cat, words in FOOD_CATEGORY.items()
         if any(w in text for w in words) or any(w in food_type for w in words)),
        "기타"
    )

    # 핵심 키워드 추출 (한글 2글자 이상)
    raw_keywords = re.findall(r"[가-힣]{2,}", text)
    stopwords = {"이거", "저거", "그게", "인데", "이고", "있고", "하고",
                 "인것", "같은", "정말", "진짜", "완전", "너무", "근데"}
    keywords = [k for k in raw_keywords if k not in stopwords][:10]

    return {
        "keywords"     : keywords,
        "location"     : location,
        "moods"        : moods,
        "food_category": food_category,
        "food_type"    : food_type.strip(),
    }
