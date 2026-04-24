"""STEP 3 실행 스크립트 - 오디오 합성 (TTS + BGM)

STEP 2 결과(step2_storyboard.json)를 읽어서:
1. 장면별 나레이션 음성 생성 (Edge TTS, 무료)
2. 분위기에 맞는 BGM 자동 선택
3. TTS + BGM 믹싱 → 최종 오디오 트랙

타이밍: 실제 영상 클립 길이 기준, 화면 전환 후 0.3초 뒤 나레이션 시작

사용법:
  python run_step3.py
"""
import sys
import io
import json
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import OUTPUT_DIR, IMAGES_DIR
from src.step3_audio.tts import TTSGenerator
from src.step3_audio.bgm import BGMManager
from src.step3_audio.mixer import AudioMixer
from src.step4_video.renderer import _find_video_files

NARRATION_DELAY = 0.0  # 나레이션 딜레이 없음 (바로 시작)


def get_video_durations(videos_dir: str) -> list[float]:
    """실제 영상 클립 길이 목록 반환 (초)"""
    from moviepy import VideoFileClip
    video_files = _find_video_files(videos_dir)
    durations = []
    for vf in video_files:
        try:
            clip = VideoFileClip(str(vf))
            durations.append(clip.duration)
            clip.close()
        except Exception as e:
            print(f"    [!] {vf.name} 길이 읽기 실패: {e}")
            durations.append(3.0)
    return durations


def main():
    parser = argparse.ArgumentParser(description="릴몽 STEP 3: 오디오 합성")
    parser.add_argument("--input",  default=str(OUTPUT_DIR / "step2_storyboard.json"))
    parser.add_argument("--videos", default=str(IMAGES_DIR))
    args = parser.parse_args()

    input_path = Path(args.input)

    print("=" * 50)
    print("  릴몽 STEP 3: 오디오 합성")
    print("  (Edge TTS + BGM 자동 매칭)")
    print("=" * 50)
    print()

    if not input_path.exists():
        print(f"[!] STEP 2 결과 파일 없음: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    store_name = storyboard["store_name"]
    category   = storyboard.get("category", "기타")
    bgm_mood   = storyboard.get("bgm_mood", "warm")
    scenes     = storyboard.get("scenes", [])

    print(f"[v] 스토리보드: {store_name} | 장면 {len(scenes)}개 | BGM: {bgm_mood}")
    print()

    # 1) 실제 영상 클립 길이 측정 → 타이밍 계산
    print("[*] 실제 영상 클립 길이 측정 중...")
    video_durations = get_video_durations(args.videos)
    total_duration  = sum(video_durations)

    actual_start_times = []
    t = 0.0
    for d in video_durations:
        actual_start_times.append(t)
        t += d

    print(f"    클립 {len(video_durations)}개 | 총 {total_duration:.2f}초")
    print()

    # 2) TTS 생성 + 큐 방식 타이밍 계산
    print("[*] TTS 나레이션 생성 중...")
    tts       = TTSGenerator.for_category(category)
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    scene_audios  = []
    queue_end_ms  = 0  # 마지막으로 배치된 나레이션이 끝나는 시각

    for i, scene in enumerate(scenes):
        idx       = scene["scene_index"]
        narration = scene.get("narration", "").strip()
        if not narration:
            continue

        if i >= len(actual_start_times):
            print(f"    [!] 장면 {idx}: 대응 영상 클립 없음, 건너뜀")
            continue

        out_path = str(audio_dir / f"scene_{idx:02d}.mp3")
        print(f"    [TTS] 장면 {idx}: {narration}")
        tts.generate(narration, out_path)

        # TTS 길이 측정
        from pydub import AudioSegment
        tts_duration_ms = len(AudioSegment.from_file(out_path))

        # 큐 구조: 이전 나레이션 끝나면 바로 시작 (장면 전환 무관)
        start_ms     = queue_end_ms
        queue_end_ms = start_ms + tts_duration_ms

        print(f"        시작: {start_ms/1000:.2f}s  끝: {queue_end_ms/1000:.2f}s  길이: {tts_duration_ms/1000:.2f}s")

        scene_audios.append({
            "path":        out_path,
            "start_ms":    start_ms,
            "scene_index": idx,
            "tts_duration": tts_duration_ms / 1000.0,
        })

    print(f"[v] TTS 완료: {len(scene_audios)}개")

    # TTS 길이 목록 저장 → STEP 4에서 클립 길이 조정에 사용
    tts_durations = [s["tts_duration"] for s in scene_audios]
    timings_path  = OUTPUT_DIR / "step3_tts_durations.json"
    with open(timings_path, "w", encoding="utf-8") as f:
        import json as _json
        _json.dump(tts_durations, f, ensure_ascii=False, indent=2)
    print(f"[v] 클립 타이밍 저장: {timings_path.name}")

    print()

    # 3) BGM 선택
    print("[*] BGM 매칭 중...")
    bgm_manager = BGMManager()
    print(f"    {bgm_manager.get_status()}")
    bgm_path = bgm_manager.select_bgm(mood=bgm_mood, category=category)
    if bgm_path:
        print(f"[v] BGM: {Path(bgm_path).name}")
    else:
        print("[!] BGM 없음 → 나레이션만으로 생성합니다.")
    print()

    # 4) 믹싱
    print("[*] 오디오 믹싱 중...")
    mixer            = AudioMixer()
    total_duration_ms = int(total_duration * 1000) + 1000
    final_audio_path  = str(OUTPUT_DIR / "step3_final_audio.mp3")

    mixer.mix(
        scene_audio_paths=scene_audios,
        bgm_path=bgm_path,
        total_duration_ms=total_duration_ms,
        output_path=final_audio_path,
    )

    print(f"[v] 최종 오디오: {final_audio_path}")
    print()
    print("[v] STEP 3 완료!")
    print("    다음: python run_step4.py")


if __name__ == "__main__":
    main()
