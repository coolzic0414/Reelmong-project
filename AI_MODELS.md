# 릴몽 AI 모델 구성

## 사용 플랫폼
모든 AI 모델은 **OpenRouter** (https://openrouter.ai) 를 통해 단일 API 키로 연동됩니다.
`.env` 파일에 `OPENROUTER_API_KEY` 하나만 설정하면 전체 파이프라인이 동작합니다.

---

## 모델 구성

### Step 1 — 이미지 분석 (Vision)
| 항목 | 내용 |
|------|------|
| 모델 | `google/gemini-2.5-flash` |
| 역할 | 영상 프레임 이미지를 분석하여 한국어 장면 묘사 생성 |
| 변경 전 | BLIP (로컬, 1.9GB) → Ollama 한국어 변환 (2단계) |
| 변경 후 | Gemini Vision으로 이미지 → 한국어 분석 직접 출력 (1단계) |

### Step 2 — 대본 생성 (LLM)
| 항목 | 내용 |
|------|------|
| 모델 | `google/gemini-2.5-flash` |
| 역할 | 이미지 분석 결과를 바탕으로 숏폼 나레이션 스토리보드 생성 |
| 변경 전 | Ollama + gemma3:4b (로컬 실행) |
| 변경 후 | Gemini 2.5 Flash via OpenRouter |

### Step 3 — 음성 합성 (TTS)
| 항목 | 내용 |
|------|------|
| 모델 | `google/gemini-3.1-flash-tts-preview` |
| 보이스 | `Kore` (한국어 최적화) |
| 출력 형식 | PCM → MP3 변환 저장 |
| 역할 | 나레이션 텍스트를 한국어 음성으로 합성 |
| 변경 전 | Edge TTS `ko-KR-SunHiNeural` (무료) |
| 변경 후 | Gemini TTS `Kore` via OpenRouter |

### Step 5 — 제목/해시태그 추천 (LLM)
| 항목 | 내용 |
|------|------|
| 모델 | `google/gemini-2.5-flash` |
| 역할 | 영상 대본 기반 유튜브/인스타 제목 및 해시태그 추천 |
| 변경 전 | Ollama + gemma3:4b (로컬 실행) |
| 변경 후 | Gemini 2.5 Flash via OpenRouter |

---

## 변경 전/후 비교

| 구분 | 변경 전 | 변경 후 |
|------|---------|---------|
| 이미지 분석 | BLIP (로컬 1.9GB) + Ollama | Gemini 2.5 Flash Vision |
| LLM | Ollama + gemma3:4b (로컬) | Gemini 2.5 Flash |
| TTS | Edge TTS (무료, 한국어) | Gemini TTS Kore |
| API 키 | 불필요 (전부 로컬) | OpenRouter 키 1개 |
| 설치 용량 | ~10GB (모델 포함) | 최소 (API 호출) |
| 인터넷 연결 | 불필요 | 필요 |

---

## 설정 방법

```bash
# 1. .env 파일 생성
cp .env.example .env

# 2. API 키 입력
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

API 키 발급: https://openrouter.ai/settings/keys
