"""
릴몽 Web API 서버 (FastAPI + SSE)

실행: python api.py
접속: http://localhost:8000
"""
import asyncio
import json
import re
import shutil
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "crol"))

app = FastAPI(title="릴몽 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 전역 상태 ─────────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}
_pipeline_lock = threading.Lock()   # 동시에 1개만 실행


def _set(job_id: str, **kw):
    if job_id in _jobs:
        _jobs[job_id].update(kw)


def _log(job_id: str, msg: str):
    if job_id in _jobs:
        _jobs[job_id]["logs"].append(msg)
    print(f"[{job_id}] {msg}")


# ── 파이프라인 ────────────────────────────────────────────────────────────
def _run_pipeline(
    job_id: str,
    job_images_dir: Path,
    job_output_dir: Path,
    store_name: str,
    store_intro: str,
    category: str,
):
    with _pipeline_lock:
        try:
            from config.settings import IMAGES_DIR, OUTPUT_DIR

            # 표준 images 폴더에 복사 (기존 삭제 후)
            if IMAGES_DIR.exists():
                shutil.rmtree(IMAGES_DIR)
            shutil.copytree(job_images_dir, IMAGES_DIR)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            # ── STEP 1: Vision 분석 ───────────────────────────────────────
            _set(job_id, step=1, progress=5, step_name="이미지 분석 중...")
            _log(job_id, "▶ Step 1: 영상 프레임 추출 + Gemini Vision 분석")

            from moviepy import VideoFileClip
            from PIL import Image
            from src.step1_vision import ImageAnalyzer
            from src.step4_video.renderer import _find_video_files

            video_files = _find_video_files(str(IMAGES_DIR))
            if not video_files:
                raise Exception("영상 파일을 찾을 수 없습니다")

            frames_dir = OUTPUT_DIR / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            frame_paths = []

            for i, vp in enumerate(video_files):
                out_path = frames_dir / f"frame_{i:02d}.jpg"
                try:
                    clip = VideoFileClip(str(vp))
                    arr = clip.get_frame(clip.duration / 2)
                    clip.close()
                    Image.fromarray(arr.astype("uint8")).save(str(out_path), "JPEG", quality=90)
                    frame_paths.append(str(out_path))
                    _log(job_id, f"  프레임 추출: {vp.name}")
                except Exception as e:
                    _log(job_id, f"  [!] {vp.name}: {e}")

            _set(job_id, progress=15)
            analyzer = ImageAnalyzer()
            result1 = analyzer.analyze_store(
                image_paths=frame_paths,
                store_name=store_name,
                store_intro=store_intro,
                category=category,
            )
            result1.save(str(OUTPUT_DIR / "step1_result.json"))
            _set(job_id, progress=20)
            _log(job_id, f"  완료 — 카테고리: {result1.category} | 분위기: {result1.overall_mood}")

            # ── STEP 2: 대본 생성 ─────────────────────────────────────────
            _set(job_id, step=2, progress=25, step_name="대본 생성 중...")
            _log(job_id, "▶ Step 2: 쇼츠 대본 생성 (Gemini LLM)")

            from src.step2_script.generator import ScriptGenerator

            gen = ScriptGenerator()
            storyboard = gen.generate(analysis=result1)
            storyboard.save(str(OUTPUT_DIR / "step2_storyboard.json"))
            # job 디렉토리에도 저장 (미리보기·재생성 API용)
            job_output_dir.mkdir(parents=True, exist_ok=True)
            storyboard.save(str(job_output_dir / "step2_storyboard.json"))
            _set(job_id, progress=40)
            _log(job_id, f"  완료 — {len(storyboard.scenes)}개 장면 생성")

            # ── STEP 3: TTS + 믹싱 ────────────────────────────────────────
            _set(job_id, step=3, progress=45, step_name="음성 합성 중...")
            _log(job_id, "▶ Step 3: TTS 음성 합성 + BGM 믹싱 (Gemini TTS)")

            from pydub import AudioSegment
            from src.step3_audio.bgm import BGMManager
            from src.step3_audio.mixer import AudioMixer
            from src.step3_audio.tts import TTSGenerator

            def _clean_narration(text: str) -> str:
                text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
                text = re.sub(r"[\u2600-\u27BF\u2B00-\u2BFF\uFE00-\uFE0F]", "", text)
                return text.strip()

            # 실제 영상 길이 측정
            video_durations = []
            for vf in video_files:
                try:
                    c = VideoFileClip(str(vf))
                    video_durations.append(c.duration)
                    c.close()
                except Exception:
                    video_durations.append(3.0)

            total_duration = sum(video_durations)
            total_duration_ms = int(total_duration * 1000)
            actual_start_times: list[float] = []
            t = 0.0
            for d in video_durations:
                actual_start_times.append(t)
                t += d

            tts = TTSGenerator.for_category(result1.category)
            audio_dir = OUTPUT_DIR / "audio"
            audio_dir.mkdir(exist_ok=True)

            scene_audios: list[dict] = []
            DELAY_MS = 300
            queue_end_ms = 0
            last_idx = len(storyboard.scenes) - 1

            for i, scene in enumerate(storyboard.scenes):
                narration = _clean_narration(scene.narration)
                if not narration or i >= len(actual_start_times):
                    continue

                out_path = str(audio_dir / f"scene_{scene.scene_index:02d}.mp3")
                _log(job_id, f"  TTS 장면 {scene.scene_index}: {narration[:25]}...")
                tts.generate(narration, out_path)

                tts_ms = len(AudioSegment.from_file(out_path))
                start_ms = max(int(actual_start_times[i] * 1000) + DELAY_MS, queue_end_ms)

                if start_ms >= total_duration_ms:
                    continue

                end_ms = start_ms + tts_ms
                if end_ms > total_duration_ms:
                    if i == last_idx:
                        start_ms = max(0, total_duration_ms - tts_ms - 500)
                        end_ms = start_ms + tts_ms
                    else:
                        continue

                queue_end_ms = end_ms
                scene_audios.append({
                    "path": out_path,
                    "start_ms": start_ms,
                    "scene_index": scene.scene_index,
                    "narration": narration,
                    "tts_duration": tts_ms / 1000.0,
                })

            # 타이밍 저장 (step4 자막용)
            timings_path = OUTPUT_DIR / "step3_narr_timings.json"
            with open(timings_path, "w", encoding="utf-8") as f:
                json.dump([{
                    "scene_index": s["scene_index"],
                    "narration": s["narration"],
                    "start": s["start_ms"] / 1000.0,
                    "duration": s["tts_duration"],
                    "path": s["path"],
                } for s in scene_audios], f, ensure_ascii=False, indent=2)

            bgm_manager = BGMManager()
            bgm_path = bgm_manager.select_bgm(
                mood=storyboard.bgm_mood, category=result1.category
            )

            mixer = AudioMixer()
            final_audio_path = str(OUTPUT_DIR / "step3_final_audio.mp3")
            mixer.mix(
                scene_audio_paths=scene_audios,
                bgm_path=bgm_path,
                total_duration_ms=total_duration_ms,
                output_path=final_audio_path,
            )
            _set(job_id, progress=60)
            _log(job_id, f"  완료 — {len(scene_audios)}개 음성 합성")

            # ── STEP 4: 영상 렌더링 ───────────────────────────────────────
            _set(job_id, step=4, progress=65, step_name="영상 제작 중...")
            _log(job_id, "▶ Step 4: 최종 영상 렌더링")

            from src.step4_video.renderer import VideoRenderer

            renderer = VideoRenderer()
            final_video_path = str(OUTPUT_DIR / "step4_final_video.mp4")
            # narr_timings 로드 (step3에서 저장한 타이밍 JSON)
            narr_timings = None
            if timings_path.exists():
                with open(timings_path, "r", encoding="utf-8") as f:
                    narr_timings = json.load(f)

            renderer.render(
                storyboard=storyboard.to_dict(),
                audio_path=final_audio_path,
                output_path=final_video_path,
                videos_dir=str(IMAGES_DIR),
                narr_timings=narr_timings,
            )
            _set(job_id, progress=80)
            _log(job_id, "  완료 — 최종 영상 생성")

            # ── STEP 5: 제목 추천 ─────────────────────────────────────────
            _set(job_id, step=5, progress=85, step_name="제목 추천 중...")
            _log(job_id, "▶ Step 5: 제목 / 해시태그 추천 (Gemini + DB)")

            from recommend.engine import run as crol_run

            food_type = getattr(storyboard, "food_type", "") or result1.category
            script_text = getattr(storyboard, "script_full_text", "")

            rec = crol_run(script=script_text, food_type=food_type, use_ollama=True)
            with open(OUTPUT_DIR / "step5_recommend.json", "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)

            _set(job_id, progress=95)
            _log(job_id, f"  완료 — {len(rec.get('ranked_titles', []))}개 제목 추천")

            # ── STEP 6: 품질 평가 ─────────────────────────────────────────
            _set(job_id, step=6, progress=98, step_name="품질 평가 중...")
            _log(job_id, "▶ Step 6: 영상 품질 평가")

            from src.step5_eval.evaluator import VideoEvaluator

            ev = VideoEvaluator()
            eval_r = ev.evaluate(
                video_path=final_video_path,
                storyboard_path=str(OUTPUT_DIR / "step2_storyboard.json"),
                audio_path=final_audio_path,
            )
            eval_r.save(str(OUTPUT_DIR / "step5_eval_result.json"))
            _log(job_id, f"  완료 — 등급: {eval_r.grade} ({eval_r.total_score:.1f}점)")

            # 완성 영상을 job 디렉토리에 보존
            job_output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_video_path, job_output_dir / "final_video.mp4")

            _set(
                job_id,
                status="done",
                progress=100,
                step=6,
                step_name="완료!",
                result={
                    "ranked_titles": rec.get("ranked_titles", [])[:5],
                    "recommended_hashtags": rec.get("recommended_hashtags", [])[:20],
                    "ref_titles": rec.get("ref_titles", [])[:5],
                    "trend_titles": rec.get("trend_titles", [])[:5],
                    "video_path": str(job_output_dir / "final_video.mp4"),
                    "grade": eval_r.grade,
                    "score": round(eval_r.total_score, 1),
                    "food_type": food_type,
                    "location": rec.get("location", ""),
                    "category": result1.category,
                },
            )
            _log(job_id, "🎉 전체 파이프라인 완료!")

        except Exception as e:
            import traceback
            _set(job_id, status="error", error=str(e))
            _log(job_id, f"❌ 오류: {e}")
            _log(job_id, traceback.format_exc())


# ── 라우트 ───────────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse("web/index.html")


@app.post("/api/start")
async def start(
    files: list[UploadFile] = File(...),
    store_name: str = Form(...),
    store_intro: str = Form(default="맛있는 음식을 제공하는 매장입니다"),
    category: str = Form(default=""),
):
    if not files:
        raise HTTPException(400, "영상 파일을 업로드해주세요")

    job_id = str(uuid.uuid4())[:8]
    job_images_dir = ROOT / "data" / "jobs" / job_id / "images"
    job_output_dir = ROOT / "data" / "jobs" / job_id / "output"
    job_images_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        # 파일명에서 경로 구분자 제거 (보안 + 안전)
        safe_name = Path(f.filename).name if f.filename else f"video_{uuid.uuid4().hex[:6]}.mp4"
        dest = job_images_dir / safe_name
        with open(dest, "wb") as fp:
            shutil.copyfileobj(f.file, fp)

    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "step": 0,
        "step_name": "준비 중...",
        "logs": [f"작업 시작 | 영상 {len(files)}개 업로드 완료"],
        "result": None,
        "error": None,
    }

    t = threading.Thread(
        target=_run_pipeline,
        args=(job_id, job_images_dir, job_output_dir, store_name, store_intro, category),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id}


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다")

    async def stream():
        while True:
            job = dict(_jobs.get(job_id, {}))
            yield f"data: {json.dumps(job, ensure_ascii=False)}\n\n"
            if job.get("status") in ("done", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/video/{job_id}")
async def preview_video(job_id: str):
    """영상 인라인 미리보기"""
    if job_id not in _jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    job = _jobs[job_id]
    if job.get("status") != "done":
        raise HTTPException(400, "영상이 아직 완성되지 않았습니다")
    vp = Path(job["result"]["video_path"])
    if not vp.exists():
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")
    return FileResponse(str(vp), media_type="video/mp4",
                        headers={"Content-Disposition": "inline"})


@app.get("/api/storyboard/{job_id}")
async def get_storyboard(job_id: str):
    """스토리보드 JSON 반환 (장면 편집용)"""
    if job_id not in _jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    sb_path = ROOT / "data" / "jobs" / job_id / "output" / "step2_storyboard.json"
    if not sb_path.exists():
        raise HTTPException(404, "스토리보드를 찾을 수 없습니다")
    with open(sb_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/regenerate/{job_id}")
async def regenerate(job_id: str, body: Dict[str, Any]):
    """수정된 장면으로 TTS + 영상 재렌더링"""
    if job_id not in _jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    if _jobs[job_id].get("status") == "running":
        raise HTTPException(400, "이미 작업이 진행 중입니다")

    scenes = body.get("scenes", [])
    if not scenes:
        raise HTTPException(400, "장면 데이터가 없습니다")

    job_output_dir = ROOT / "data" / "jobs" / job_id / "output"

    # 수정된 장면으로 storyboard 업데이트
    sb_path = job_output_dir / "step2_storyboard.json"
    if not sb_path.exists():
        raise HTTPException(404, "스토리보드 파일을 찾을 수 없습니다")
    with open(sb_path, "r", encoding="utf-8") as f:
        storyboard_data = json.load(f)
    storyboard_data["scenes"] = scenes
    with open(sb_path, "w", encoding="utf-8") as f:
        json.dump(storyboard_data, f, ensure_ascii=False, indent=2)

    _set(job_id, status="running", progress=40, step=2,
         step_name="재생성 준비 중...", error=None)

    t = threading.Thread(
        target=_run_regen,
        args=(job_id, job_output_dir, storyboard_data),
        daemon=True,
    )
    t.start()
    return {"ok": True}


# ── 재생성 파이프라인 (Step 3 + 4 재실행) ─────────────────────────────────
def _run_regen(job_id: str, job_output_dir: Path, storyboard_data: dict):
    with _pipeline_lock:
        try:
            from config.settings import OUTPUT_DIR

            # IMAGES_DIR 복사 없이 job_images_dir 직접 사용
            # (이전 파이프라인이 파일 핸들을 잡고 있을 수 있어 rmtree 대신 직접 참조)
            job_images_dir = ROOT / "data" / "jobs" / job_id / "images"
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            # storyboard 전역 OUTPUT_DIR에도 반영
            with open(OUTPUT_DIR / "step2_storyboard.json", "w", encoding="utf-8") as f:
                json.dump(storyboard_data, f, ensure_ascii=False, indent=2)

            # Storyboard 객체 재구성
            from src.step2_script.models import Storyboard, SceneScript
            scenes_obj = [SceneScript(**s) for s in storyboard_data.get("scenes", [])]
            storyboard = Storyboard(
                store_name=storyboard_data.get("store_name", ""),
                category=storyboard_data.get("category", ""),
                total_duration=storyboard_data.get("total_duration", 0),
                scenes=scenes_obj,
                bgm_mood=storyboard_data.get("bgm_mood", ""),
                script_full_text=storyboard_data.get("script_full_text", ""),
                hook_candidates=storyboard_data.get("hook_candidates", []),
                food_type=storyboard_data.get("food_type", ""),
            )

            # ── STEP 3: TTS 재합성 ──────────────────────────────────────
            _set(job_id, step=3, progress=45, step_name="음성 재합성 중...")
            _log(job_id, "▶ 재생성 Step 3: TTS 음성 합성 + BGM 믹싱")

            from moviepy import VideoFileClip
            from pydub import AudioSegment
            from src.step3_audio.bgm import BGMManager
            from src.step3_audio.mixer import AudioMixer
            from src.step3_audio.tts import TTSGenerator
            from src.step4_video.renderer import _find_video_files

            def _clean(text: str) -> str:
                text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
                text = re.sub(r"[\u2600-\u27BF\u2B00-\u2BFF\uFE00-\uFE0F]", "", text)
                return text.strip()

            # job_images_dir 직접 사용 (IMAGES_DIR 파일 잠금 회피)
            video_files = _find_video_files(str(job_images_dir))
            video_durations = []
            for vf in video_files:
                try:
                    c = VideoFileClip(str(vf))
                    video_durations.append(c.duration)
                    c.close()
                except Exception:
                    video_durations.append(3.0)

            total_duration = sum(video_durations)
            total_duration_ms = int(total_duration * 1000)
            actual_start_times: list[float] = []
            t = 0.0
            for d in video_durations:
                actual_start_times.append(t)
                t += d

            tts = TTSGenerator.for_category(storyboard.category)
            audio_dir = OUTPUT_DIR / "audio"
            audio_dir.mkdir(exist_ok=True)

            scene_audios: list[dict] = []
            DELAY_MS = 300
            queue_end_ms = 0
            last_idx = len(storyboard.scenes) - 1

            for i, scene in enumerate(storyboard.scenes):
                narration = _clean(scene.narration)
                if not narration or i >= len(actual_start_times):
                    continue
                out_path = str(audio_dir / f"scene_{scene.scene_index:02d}.mp3")
                _log(job_id, f"  TTS 장면 {scene.scene_index}: {narration[:25]}...")
                tts.generate(narration, out_path)
                tts_ms = len(AudioSegment.from_file(out_path))
                start_ms = max(int(actual_start_times[i] * 1000) + DELAY_MS, queue_end_ms)
                if start_ms >= total_duration_ms:
                    continue
                end_ms = start_ms + tts_ms
                if end_ms > total_duration_ms:
                    if i == last_idx:
                        start_ms = max(0, total_duration_ms - tts_ms - 500)
                        end_ms = start_ms + tts_ms
                    else:
                        continue
                queue_end_ms = end_ms
                scene_audios.append({
                    "path": out_path, "start_ms": start_ms,
                    "scene_index": scene.scene_index,
                    "narration": narration, "tts_duration": tts_ms / 1000.0,
                })

            timings_path = OUTPUT_DIR / "step3_narr_timings.json"
            with open(timings_path, "w", encoding="utf-8") as f:
                json.dump([{
                    "scene_index": s["scene_index"], "narration": s["narration"],
                    "start": s["start_ms"] / 1000.0, "duration": s["tts_duration"],
                    "path": s["path"],
                } for s in scene_audios], f, ensure_ascii=False, indent=2)

            bgm_path = BGMManager().select_bgm(
                mood=storyboard.bgm_mood, category=storyboard.category)
            final_audio_path = str(OUTPUT_DIR / "step3_final_audio.mp3")
            AudioMixer().mix(scene_audio_paths=scene_audios, bgm_path=bgm_path,
                             total_duration_ms=total_duration_ms,
                             output_path=final_audio_path)
            _set(job_id, progress=70)
            _log(job_id, f"  완료 — {len(scene_audios)}개 음성 재합성")

            # ── STEP 4: 영상 재렌더링 ───────────────────────────────────
            _set(job_id, step=4, progress=75, step_name="영상 재렌더링 중...")
            _log(job_id, "▶ 재생성 Step 4: 영상 렌더링")

            from src.step4_video.renderer import VideoRenderer
            final_video_path = str(OUTPUT_DIR / "step4_final_video.mp4")
            narr_timings = None
            if timings_path.exists():
                with open(timings_path, "r", encoding="utf-8") as f:
                    narr_timings = json.load(f)

            VideoRenderer().render(
                storyboard=storyboard.to_dict(),
                audio_path=final_audio_path,
                output_path=final_video_path,
                videos_dir=str(job_images_dir),
                narr_timings=narr_timings,
            )
            _set(job_id, progress=95)
            shutil.copy2(final_video_path, job_output_dir / "final_video.mp4")

            # result 유지하되 video_path만 갱신
            prev_result = _jobs[job_id].get("result") or {}
            prev_result["video_path"] = str(job_output_dir / "final_video.mp4")
            _set(job_id, status="done", progress=100, step=4,
                 step_name="재생성 완료!", result=prev_result)
            _log(job_id, "🎉 재생성 완료!")

        except Exception as e:
            import traceback
            _set(job_id, status="error", error=str(e))
            _log(job_id, f"❌ 오류: {e}")
            _log(job_id, traceback.format_exc())


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    job = _jobs[job_id]
    if job.get("status") != "done":
        raise HTTPException(400, "영상이 아직 완성되지 않았습니다")
    vp = Path(job["result"]["video_path"])
    if not vp.exists():
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")
    return FileResponse(
        str(vp),
        media_type="video/mp4",
        filename=f"reelmong_{job_id}.mp4",
    )


if __name__ == "__main__":
    (ROOT / "web").mkdir(exist_ok=True)
    print("=" * 45)
    print("  릴몽 서버 시작")
    print("  접속: http://localhost:8000")
    print("=" * 45)
    uvicorn.run(app, host="0.0.0.0", port=8000)
