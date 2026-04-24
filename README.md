# 릴몽 (Reelmong)

**F&B 매장 홍보 숏폼 영상 자동 생성 AI 파이프라인**

영상 클립 10개와 매장 정보만 넣으면, 나레이션·자막·BGM이 합성된 9:16 세로 숏폼 영상과 유튜브/인스타 제목·해시태그까지 자동으로 만들어줍니다.

---

## 어떤 프로그램인가요?

음식점·카페 등 F&B 매장의 홍보 영상(인스타 릴스, 유튜브 쇼츠)을 자동으로 제작합니다.

**인풋**
- `data/images/` 폴더에 3~5초짜리 mp4 클립 최대 10개
- 매장 이름, 매장 소개, 업종 (Step 1 실행 시 입력)

**아웃풋**
- `step4_final_video.mp4` — 바로 업로드 가능한 9:16 세로 숏폼 영상
- `step5_recommend.json` — 유튜브/인스타 제목 후보 8개 + 해시태그 20개

**핵심 특징**
- 외부 유료 API 없이 로컬에서 전부 동작 (Ollama 로컬 LLM + Edge TTS 무료)
- BLIP 이미지 캡셔닝으로 영상 속 음식을 실제로 인식해서 대본 작성
- 후킹 멘트 10개 후보 자동 생성 후 랜덤 선택 → 첫 장면에 배치
- 나레이션 끝나는 타이밍에 맞춰 영상 클립 자동 분할/연장
- 자막 팝(pop) 애니메이션 (나레이션 시작 시 뿅! 등장)

---

## 동작 구조

```
data/images/ (mp4 클립 10개)
        │
        ▼
  ┌─────────────────────────────────────────────────────┐
  │  Step 1  영상 중간 프레임 추출 → BLIP 이미지 분석     │
  │          각 클립에서 무슨 음식·공간인지 파악           │
  └─────────────────────┬───────────────────────────────┘
                        │ step1_result.json
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  Step 2  Ollama LLM으로 대본 생성                    │
  │          - 후킹 멘트 10개 생성 후 랜덤 1개 선택        │
  │          - 장면별 나레이션 (15자 이내, 이미지 반영)     │
  │          - 음식 종류(food_type) 자동 분류             │
  └─────────────────────┬───────────────────────────────┘
                        │ step2_storyboard.json
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  Step 3  나레이션 음성 + BGM 합성                    │
  │          - Edge TTS로 한국어 음성 생성 (무료)          │
  │          - 업종별 자동 BGM 선택 (data/bgm/ 폴더)      │
  │          - 나레이션 큐(queue) 방식: 겹침 없이 연속 재생 │
  └─────────────────────┬───────────────────────────────┘
                        │ step3_final_audio.mp3
                        │ step3_tts_durations.json
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  Step 4  최종 영상 렌더링                             │
  │          - 영상 클립 10개 순서대로 연결               │
  │          - 나레이션 길이에 맞게 클립 자동 조정          │
  │          - 자막 팝 애니메이션 오버레이                 │
  │          - 오디오(TTS+BGM) 합성                      │
  └─────────────────────┬───────────────────────────────┘
                        │ step4_final_video.mp4
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  Step 5  제목 / 해시태그 추천 (crol 엔진)             │
  │          - 템플릿 기반 제목 8개                       │
  │          - Ollama AI 제목 추천 (선택)                 │
  │          - DB 기반 인기 해시태그 20개                 │
  └─────────────────────┬───────────────────────────────┘
                        │ step5_recommend.json
                        ▼
                   🎬 완성!
```

---

## 폴더 구조

```
reelmong/
├── run_step1.py          # Step 1: 프레임 추출 + 이미지 분석
├── run_step2.py          # Step 2: 대본/스토리보드 생성
├── run_step3.py          # Step 3: TTS + BGM 오디오 합성
├── run_step4.py          # Step 4: 최종 영상 렌더링
├── run_step5.py          # Step 5: 제목/해시태그 추천
├── run_step6.py          # Step 6: 영상 품질 평가 (선택)
│
├── config/
│   └── settings.py       # 전역 설정 (해상도, 모델명, 경로 등)
│
├── src/
│   ├── step1_vision/     # BLIP 이미지 캡셔닝
│   ├── step2_script/     # 스토리보드 생성 (Ollama)
│   ├── step3_audio/      # TTS / BGM / 오디오 믹서
│   ├── step4_video/      # 영상 렌더러 (MoviePy)
│   └── step5_eval/       # 영상 품질 평가
│
├── crol/                 # 제목/해시태그 추천 엔진
│   ├── recommend/        # 추천 핵심 로직
│   ├── collect/          # YouTube 데이터 수집 (선택)
│   └── crol_config.py    # crol 설정
│
├── data/
│   ├── images/           # 📥 여기에 mp4 클립 넣기
│   ├── bgm/              # 분위기별 BGM 폴더
│   │   ├── warm/
│   │   ├── energetic/
│   │   ├── calm/
│   │   ├── trendy/
│   │   └── elegant/
│   ├── fonts/            # 한국어 폰트
│   └── output/           # 각 스텝 결과물 (자동 생성)
│
├── requirements.txt
└── .env.example
```

---

## 설치 방법

### 1. 사전 요구사항

| 항목 | 설치 방법 |
|------|----------|
| Python 3.10+ | https://python.org |
| FFmpeg | `winget install ffmpeg` (Windows) / `brew install ffmpeg` (Mac) |
| Ollama | https://ollama.com 에서 설치 후 `ollama pull gemma3:4b` |

### 2. 패키지 설치

```bash
pip install -r requirements.txt
pip install -r crol/requirements.txt
```

### 3. 환경변수 설정

```bash
# .env.example을 복사해서 .env 파일 생성
cp .env.example .env
```

`.env` 파일 내용 (수정 불필요, 기본값 그대로 사용 가능):
```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
```

crol 제목 추천에 YouTube 데이터를 직접 수집하려면 `crol/.env` 파일에 YouTube API 키 입력:
```
# crol/.env
YOUTUBE_API_KEY=your_youtube_api_key_here
```
> YouTube API 키 없이도 기본 추천(템플릿 + AI)은 정상 동작합니다.

### 4. BGM 파일 추가 (선택)

`data/bgm/` 하위 폴더에 분위기에 맞는 mp3 파일을 넣으면 자동으로 선택됩니다.

```
data/bgm/warm/      ← 따뜻한 분위기 (카페, 한식)
data/bgm/energetic/ ← 신나는 분위기 (치킨, 분식)
data/bgm/calm/      ← 차분한 분위기 (일식, 양식)
data/bgm/trendy/    ← 트렌디한 분위기 (카페, 베이커리)
data/bgm/elegant/   ← 고급스러운 분위기
```

---

## 사용 방법

### Step 1: 영상 클립 준비 + 분석

```bash
# data/images/ 폴더에 mp4 파일 넣기 (파일명 숫자 순서대로)
# 예: 쿠우쿠우0.mp4, 쿠우쿠우1.mp4 ... 쿠우쿠우9.mp4

# 실행 (대화형)
python run_step1.py

# 또는 인자로 직접 입력
python run_step1.py --name "쿠우쿠우 홍대점" --intro "무한리필 초밥 뷔페" --category "일식"
```

### Step 2~4: 대본 생성 → 오디오 합성 → 영상 렌더링

```bash
python run_step2.py
python run_step3.py
python run_step4.py
```

### Step 5: 제목 / 해시태그 추천

```bash
python run_step5.py

# Ollama 없이 빠르게 실행하려면
python run_step5.py --no-ollama
```

### (선택) Step 6: 영상 품질 평가

```bash
python run_step6.py
```

---

## 출력 결과 예시

**제목 추천 (step5_recommend.json)**
```
[AI 추천 제목]
  1. 무한리필 초밥인데 이게 진짜 가능해?
  2. 여기 초밥 퀄리티 실화냐...

[템플릿 추천 제목]
  1. [hook]    이거 보면 지금 당장 가고싶어짐
  2. [honest]  쿠우쿠우 광고 아님 진짜 맛있어서 올림
  3. [twist]   기대 안 했다가 쿠우쿠우 완전 반함
  ...

[추천 해시태그]
  #shorts #먹방 #초밥 #무한리필 #일식맛집 #맛집 ...
```

---

## 기술 스택

| 역할 | 라이브러리 / 모델 |
|------|-----------------|
| 이미지 분석 | BLIP (Salesforce/blip-image-captioning-large) |
| 대본 생성 | Ollama + gemma3:4b (로컬 LLM) |
| 음성 합성 | Edge TTS (Microsoft, 무료) |
| 영상 편집 | MoviePy 2.x |
| 오디오 믹싱 | pydub |
| 제목 추천 | crol 엔진 (템플릿 + Ollama + SQLite DB) |

---

## 주의사항

- **BLIP 모델**은 첫 실행 시 Hugging Face에서 자동 다운로드 (약 1.9GB)
- **Ollama**는 Step 1, 2, 5 실행 전에 반드시 `ollama serve` 로 실행되어 있어야 함
- 영상 클립 파일명은 숫자로 끝나야 순서대로 정렬됨 (예: `clip0.mp4`, `clip1.mp4`)
- `data/images/` 폴더는 한 번에 한 매장 작업용 — 새 매장 촬영 시 기존 클립 교체 후 Step 1부터 재실행
