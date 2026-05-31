# 릴몽 (Reelmong)

**F&B 매장 홍보 숏폼 영상 자동 생성 AI 파이프라인**

영상 클립과 매장 정보만 넣으면, 나레이션·자막·BGM이 합성된 9:16 세로 숏폼 영상과 유튜브/인스타 제목·해시태그까지 자동으로 만들어줍니다.

---

## 데모

| 입력 | 출력 |
|------|------|
| 매장 클립 (mp4 최대 10개) + 매장명/소개/업종 | 9:16 숏폼 영상 + 제목/해시태그 추천 |

---

## 기술 스택

| 역할 | 기술 |
|------|------|
| 백엔드 API | FastAPI + SSE (실시간 진행 상황) |
| 프론트엔드 | Vanilla JS + HTML/CSS (웹 UI) |
| 이미지 분석 | Google Gemini 2.5 Flash (Vision) |
| 대본 생성 | Google Gemini 2.5 Flash (LLM) |
| 음성 합성 | Google Gemini TTS (`Kore` 보이스) |
| 영상 편집 | MoviePy 2.x |
| 추천 엔진 | SQLite DB + Gemini LLM |
| AI 연동 | OpenRouter (단일 API 키) |

> 모델 상세 설명 → [AI_MODELS.md](AI_MODELS.md)

---

## 동작 구조

```
[웹 UI] 클립 업로드 + 매장 정보 입력
        │
        ▼
  Step 1  Gemini Vision으로 각 클립 장면 분석 (음식·공간 한국어 인식)
        │
        ▼
  Step 2  Gemini LLM으로 숏폼 대본 생성
          - 후킹 멘트 10개 후보 → 바이럴 점수 기반 선택
          - 장면별 나레이션 + 자막 자동 작성
        │
        ▼
  Step 3  TTS 음성 생성 + BGM 합성
          - Gemini TTS (한국어 Kore 보이스)
          - 업종별 자동 BGM 선택
        │
        ▼
  Step 4  최종 영상 렌더링
          - 나레이션 타이밍에 맞춰 클립 자동 조정
          - 자막 팝 애니메이션 오버레이
        │
        ▼
  Step 5  제목 / 해시태그 추천 (crol 엔진)
          - 템플릿 + Gemini AI 기반 제목 8개
          - YouTube DB 기반 인기 해시태그 20개
        │
        ▼
[웹 UI] 영상 미리보기 + 대본 편집 + 다운로드
```

---

## 폴더 구조

```
reelmong-algorithm/
├── api.py                # FastAPI 서버 (메인 진입점)
├── web/
│   └── index.html        # 웹 UI
│
├── config/
│   └── settings.py       # 전역 설정 (해상도, 모델명, 경로 등)
│
├── src/
│   ├── step1_vision/     # Gemini Vision 이미지 분석
│   ├── step2_script/     # 스토리보드 생성 (Gemini LLM)
│   ├── step3_audio/      # TTS / BGM / 오디오 믹서
│   ├── step4_video/      # 영상 렌더러 (MoviePy)
│   └── step5_eval/       # 영상 품질 평가
│
├── crol/                 # 제목/해시태그 추천 + YouTube 수집 엔진
│   ├── recommend/        # 추천 핵심 로직
│   ├── collect/          # YouTube 데이터 수집
│   ├── analyze/          # 수집 데이터 분석
│   ├── db/               # SQLite DB 초기화/쿼리
│   ├── collect_once.py   # 수동 수집 실행 스크립트
│   └── crol_config.py    # crol 설정
│
├── data/
│   ├── bgm/              # 분위기별 BGM
│   │   ├── warm/         # 따뜻한 (카페, 한식)
│   │   ├── energetic/    # 신나는 (치킨, 분식)
│   │   ├── calm/         # 차분한 (일식, 양식)
│   │   ├── trendy/       # 트렌디한 (카페, 베이커리)
│   │   └── elegant/      # 고급스러운
│   ├── fonts/            # 한국어 폰트
│   └── jobs/             # 작업별 결과물 (자동 생성)
│
├── requirements.txt
├── .env                  # API 키 (gitignore됨)
└── .env.example          # 환경변수 예시
```

---

## 설치 방법

### 1. 사전 요구사항

| 항목 | 설치 |
|------|------|
| Python 3.10+ | https://python.org |
| FFmpeg | `winget install ffmpeg` (Windows) / `brew install ffmpeg` (Mac) |
| OpenRouter API 키 | https://openrouter.ai/settings/keys |

### 2. 패키지 설치

```bash
pip install -r requirements.txt
pip install -r crol/requirements.txt
```

Python 3.13 이상은 추가 설치 필요:
```bash
pip install audioop-lts
```

### 3. 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성:

```env
# 필수
OPENROUTER_API_KEY=your_openrouter_api_key_here

# 선택 (YouTube 데이터 수집 시)
YOUTUBE_API_KEY=your_youtube_api_key_here
NAVER_CLIENT_ID=your_naver_client_id_here
NAVER_CLIENT_SECRET=your_naver_client_secret_here
```

> YouTube / Naver API 키 없이도 기본 추천(템플릿 + Gemini AI)은 정상 동작합니다.

### 4. BGM 파일 추가 (선택)

`data/bgm/` 하위 폴더에 분위기에 맞는 mp3 파일을 넣으면 자동으로 선택됩니다.

---

## 실행 방법

### 서버 시작

```bash
python api.py
```

브라우저에서 `http://localhost:8000` 접속

### YouTube 데이터 수집 (추천 품질 향상)

```bash
cd crol
python collect_once.py
```

---

## 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/generate` | 영상 생성 시작 (파일 업로드) |
| `GET` | `/api/progress/{job_id}` | 실시간 진행 상황 (SSE) |
| `GET` | `/api/video/{job_id}` | 생성된 영상 미리보기 |
| `GET` | `/api/storyboard/{job_id}` | 스토리보드 JSON |
| `POST` | `/api/regenerate/{job_id}` | 대본 수정 후 영상 재생성 |
| `GET` | `/api/download/{job_id}` | 최종 영상 다운로드 |

---

## 주의사항

- `.env` 파일은 절대 GitHub에 올리지 마세요 (`.gitignore`에 포함되어 있음)
- 영상 클립 파일명은 숫자로 끝나야 순서대로 정렬됩니다 (예: `clip0.mp4`, `clip1.mp4`)
- Windows에서 영상 재생성 시 MoviePy 파일 잠금 현상이 발생할 수 있습니다 — 서버 재시작 후 재시도하세요
