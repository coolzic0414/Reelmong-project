"""
Ollama LLM 연동 — 대본 + DB 트렌드 데이터 기반 제목/태그 생성
"""
import json
import sys, os
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from crol_config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT


def _call_ollama(prompt: str) -> str | None:
    """Ollama API 호출"""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        print(f"[ollama] 연결 실패 — Ollama가 실행 중인지 확인하세요 ({OLLAMA_HOST})")
        return None
    except Exception as e:
        print(f"[ollama] 오류: {e}")
        return None


def _build_prompt(script: str, food_type: str, info: dict, patterns: dict) -> str:
    """프롬프트 구성"""

    ref_titles    = "\n".join(f"- {t}" for t in patterns.get("titles", [])[:10])
    ref_hashtags  = ", ".join(f"#{h}" for h in patterns.get("top_hashtags", [])[:15])
    location      = info.get("location") or "서울"
    moods         = ", ".join(info.get("moods", [])) or "일반"

    prompt = f"""당신은 한국 유튜브 음식 숏폼 콘텐츠 전문가입니다.
아래 정보를 바탕으로 조회수가 높을 것 같은 제목 5개와 해시태그 15개를 추천해주세요.

[영상 대본]
{script[:500]}

[음식 정보]
- 음식 종류: {food_type}
- 촬영 장소: {location}
- 분위기: {moods}

[현재 트렌드 참고 제목 (실제 인기 영상)]
{ref_titles if ref_titles else "데이터 없음"}

[현재 인기 해시태그]
{ref_hashtags if ref_hashtags else "데이터 없음"}

[조건]
- 제목은 한국어로, 유튜브 숏폼 스타일로 작성
- 클릭하고 싶은 제목, 과장되지 않은 자연스러운 표현
- 해시태그는 # 포함해서 작성
- 아래 형식으로만 답하세요

[출력 형식]
제목1: (제목)
제목2: (제목)
제목3: (제목)
제목4: (제목)
제목5: (제목)
해시태그: #태그1 #태그2 #태그3 ... (15개)
"""
    return prompt


def _parse_response(response: str) -> dict:
    """LLM 응답 파싱"""
    titles    = []
    hashtags  = []

    for line in response.splitlines():
        line = line.strip()
        if line.startswith("제목") and ":" in line:
            title = line.split(":", 1)[1].strip()
            if title:
                titles.append(title)
        elif line.startswith("해시태그:"):
            raw = line.split(":", 1)[1].strip()
            hashtags = [h.strip() for h in raw.split() if h.startswith("#")]

    return {"titles": titles[:5], "hashtags": hashtags[:15]}


def generate(script: str, food_type: str, info: dict, patterns: dict) -> dict:
    """
    Ollama로 제목 + 해시태그 생성
    반환: {"titles": [...], "hashtags": [...]}
    """
    print(f"[ollama] {OLLAMA_MODEL} 로 생성 중...")
    prompt   = _build_prompt(script, food_type, info, patterns)
    response = _call_ollama(prompt)

    if not response:
        print("[ollama] 생성 실패 — 템플릿 결과만 사용됩니다")
        return {"titles": [], "hashtags": []}

    result = _parse_response(response)
    print(f"[ollama] 제목 {len(result['titles'])}개, 해시태그 {len(result['hashtags'])}개 생성")
    return result


def check_connection() -> bool:
    """Ollama 연결 확인"""
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        print(f"[ollama] 연결 성공 | 설치된 모델: {models}")
        return True
    except Exception:
        print(f"[ollama] 연결 실패 ({OLLAMA_HOST})")
        return False
