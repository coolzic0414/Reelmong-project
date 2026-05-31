"""TTS 모듈 - Gemini TTS via OpenRouter

OpenRouter를 통해 Gemini TTS로 한국어 음성을 합성합니다.
- Gemini TTS는 PCM 포맷으로 반환 → pydub으로 MP3 변환
- API 키 하나로 LLM + Vision + TTS 통합
"""
from pathlib import Path

from openai import OpenAI
from pydub import AudioSegment

from config.settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    TTS_MODEL,
    TTS_VOICE,
    TTS_VOICE_MALE,
)

# 업종별 보이스 매핑 (여성/남성)
CATEGORY_VOICE_MAP = {
    "한식"    : TTS_VOICE,       # 여성
    "카페"    : TTS_VOICE,       # 여성
    "베이커리" : TTS_VOICE,       # 여성
    "분식"    : TTS_VOICE,       # 여성
    "양식"    : TTS_VOICE,       # 여성
    "일식"    : TTS_VOICE_MALE,  # 남성
    "치킨"    : TTS_VOICE_MALE,  # 남성
    "피자"    : TTS_VOICE_MALE,  # 남성
    "중식"    : TTS_VOICE_MALE,  # 남성
    "기타"    : TTS_VOICE,       # 여성 (기본)
}

# Gemini TTS PCM 스펙 (OpenRouter 기준)
PCM_SAMPLE_RATE = 24000
PCM_SAMPLE_WIDTH = 2   # 16-bit
PCM_CHANNELS = 1       # mono


class TTSGenerator:
    """Gemini TTS (OpenRouter)를 사용한 한국어 음성 합성"""

    def __init__(self, voice: str = TTS_VOICE):
        self.client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
        self.voice = voice

    @classmethod
    def for_category(cls, category: str) -> "TTSGenerator":
        """업종에 맞는 보이스로 TTS 생성기 반환 (여성/남성 자동 선택)"""
        voice = CATEGORY_VOICE_MAP.get(category, TTS_VOICE)
        print(f"    [TTS] 보이스: {voice} (업종: {category})")
        return cls(voice=voice)

    def generate(self, text: str, output_path: str) -> str:
        """나레이션 텍스트 → MP3 음성 파일 생성

        Gemini TTS: PCM 수신 → MP3 변환 저장
        Args:
            text: 나레이션 텍스트
            output_path: 출력 MP3 파일 경로
        Returns:
            생성된 MP3 파일 경로
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Gemini TTS는 pcm 포맷만 지원
        response = self.client.audio.speech.create(
            model=TTS_MODEL,
            input=text,
            voice=self.voice,
            response_format="pcm",
        )

        # PCM 바이트 → pydub AudioSegment → MP3 저장
        pcm_bytes = response.content
        audio = AudioSegment(
            data=pcm_bytes,
            sample_width=PCM_SAMPLE_WIDTH,
            frame_rate=PCM_SAMPLE_RATE,
            channels=PCM_CHANNELS,
        )
        audio.export(output_path, format="mp3", bitrate="192k")

        return output_path

    def generate_per_scene(
        self, scenes: list[dict], output_dir: str
    ) -> list[str]:
        """장면별 나레이션 개별 생성

        Args:
            scenes: [{"narration": "텍스트", "scene_index": 1}, ...]
            output_dir: 출력 디렉토리
        Returns:
            생성된 MP3 파일 경로 리스트
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        paths = []

        for scene in scenes:
            narration = scene.get("narration", "")
            idx = scene.get("scene_index", 0)
            if not narration.strip():
                continue

            out_path = str(Path(output_dir) / f"scene_{idx:02d}.mp3")
            print(f"    [TTS] 장면 {idx} 음성 생성 중...")
            self.generate(narration, out_path)
            paths.append(out_path)

        return paths
