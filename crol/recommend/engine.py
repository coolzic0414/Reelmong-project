"""
추천 엔진 통합 진입점
템플릿 추천 + Ollama 추천 결합
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from recommend.extractor  import extract_info
from recommend.retriever  import retrieve
from recommend.templates  import generate_template_titles
from recommend.ollama_gen import generate as ollama_generate, check_connection


def run(script: str, food_type: str, use_ollama: bool = True) -> dict:
    """
    추천 실행
    - script   : 영상 대본 텍스트
    - food_type: 음식 종류 (예: "카페 라떼", "삼겹살", "디저트")
    - use_ollama: Ollama 사용 여부
    """
    print(f"\n{'='*55}")
    print(f"  추천 시작 | 음식: {food_type}")
    print(f"{'='*55}")

    # 1. 대본에서 정보 추출
    info = extract_info(script, food_type)
    print(f"[engine] 장소: {info['location']} | 분위기: {info['moods']}")
    print(f"[engine] 카테고리: {info['food_category']}")

    # 2. DB에서 관련 영상 패턴 검색
    patterns = retrieve(food_type, info["keywords"])

    # 3. 템플릿 기반 추천
    template_results = generate_template_titles(
        food_type=food_type,
        location=info["location"],
        count=8,
    )

    # 4. Ollama 기반 추천
    ollama_results = {"titles": [], "hashtags": []}
    if use_ollama:
        ollama_results = ollama_generate(script, food_type, info, patterns)

    # 5. 해시태그 통합 (Ollama + DB 패턴)
    combined_hashtags = list(dict.fromkeys(
        ollama_results.get("hashtags", []) +
        [f"#{h}" for h in patterns.get("top_hashtags", [])[:20]]
    ))[:20]

    return {
        "food_type"         : food_type,
        "location"          : info["location"],
        "food_category"     : info["food_category"],
        "moods"             : info["moods"],
        "template_titles"   : template_results,
        "ollama_titles"     : ollama_results.get("titles", []),
        "recommended_hashtags": combined_hashtags,
        "ref_titles"        : patterns.get("titles", [])[:5],
    }


def print_result(result: dict):
    if not result:
        print("추천 결과 없음")
        return

    print(f"\n{'='*55}")
    print(f"  추천 결과 | {result.get('food_type')} | {result.get('location', '장소 미상')}")
    print(f"{'='*55}")

    if result.get("ollama_titles"):
        print("\n[AI 추천 제목 (Ollama)]")
        for i, title in enumerate(result["ollama_titles"], 1):
            print(f"  {i}. {title}")

    print("\n[템플릿 추천 제목]")
    for i, item in enumerate(result.get("template_titles", []), 1):
        tag = f"[{item['type']}]"
        print(f"  {i}. {tag:<12} {item['title']}")

    print("\n[추천 해시태그]")
    print("  " + " ".join(result.get("recommended_hashtags", [])))

    if result.get("ref_titles"):
        print("\n[참고한 실제 인기 영상 제목]")
        for t in result["ref_titles"]:
            print(f"  • {t}")
    print()
