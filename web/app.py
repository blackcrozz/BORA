"""
BORA Web UI — Flask Backend
Handles upload, pipeline processing with SSE progress, and review.
"""

import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import (
    Flask, Response, jsonify, render_template,
    request, send_from_directory,
)
from werkzeug.utils import secure_filename

# ── Path setup ──────────────────────────────────────────────
BORA_ROOT = Path(__file__).parent.parent  # D:\BORA
sys.path.insert(0, str(BORA_ROOT))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

UPLOAD_FOLDER = BORA_ROOT / "uploads"
OUTPUT_FOLDER = BORA_ROOT / "output"
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}

# ── Job State Store ──────────────────────────────────────────
jobs: dict[str, dict] = {}  # job_id → {status, progress, segments, result, error}
progress_queues: dict[str, queue.Queue] = {}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def emit(q: queue.Queue, event: str, data: dict):
    """Push SSE event to job queue."""
    q.put({"event": event, "data": json.dumps(data)})


# ── Routes ───────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/review/<job_id>")
def review(job_id):
    job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    return render_template("review.html", job_id=job_id)


@app.route("/api/job/<job_id>")
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


@app.route("/api/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["video"]
    if not f.filename or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file type"}), 400

    job_id = str(uuid.uuid4())[:8]
    filename = f"{job_id}_{secure_filename(f.filename)}"
    filepath = UPLOAD_FOLDER / filename
    f.save(str(filepath))

    jobs[job_id] = {
        "id": job_id,
        "filename": f.filename,
        "filepath": str(filepath),
        "status": "uploaded",
        "progress": 0,
        "step": "Ready",
        "segments": [],
        "review_data": None,
        "result_path": None,
        "error": None,
    }

    return jsonify({"job_id": job_id, "filename": f.filename})


@app.route("/api/process", methods=["POST"])
def process():
    data = request.json
    job_id = data.get("job_id")
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    settings = data.get("settings", {})
    job["settings"] = settings
    job["status"] = "processing"

    q = queue.Queue()
    progress_queues[job_id] = q

    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, job["filepath"], settings, q),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "started"})


@app.route("/api/progress/<job_id>")
def progress_stream(job_id):
    q = progress_queues.get(job_id)
    if not q:
        return Response("data: {}\n\n", mimetype="text/event-stream")

    def generate():
        while True:
            try:
                msg = q.get(timeout=30)
                if msg is None:
                    break
                yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/render", methods=["POST"])
def render():
    """Apply manual review selections and render final video."""
    data = request.json
    job_id = data.get("job_id")
    removed_words = data.get("removed_words", [])   # list of {start, end}
    removed_gaps = data.get("removed_gaps", [])      # list of {start, end}
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404

    q = queue.Queue()
    progress_queues[job_id + "_render"] = q

    thread = threading.Thread(
        target=run_render,
        args=(job_id, removed_words, removed_gaps, q),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "rendering"})


@app.route("/api/progress_render/<job_id>")
def progress_render_stream(job_id):
    q = progress_queues.get(job_id + "_render")
    if not q:
        return Response("data: {}\n\n", mimetype="text/event-stream")

    def generate():
        while True:
            try:
                msg = q.get(timeout=30)
                if msg is None:
                    break
                yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache"})


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUT_FOLDER), filename)


# ── Pipeline Runner ──────────────────────────────────────────

def run_pipeline(job_id: str, filepath: str, settings: dict, q: queue.Queue):
    job = jobs[job_id]

    def step(name, pct, detail=""):
        job["step"] = name
        job["progress"] = pct
        emit(q, "progress", {"step": name, "pct": pct, "detail": detail})

    try:
        from dotenv import load_dotenv
        load_dotenv(str(BORA_ROOT / ".env"))

        input_path = Path(filepath)
        stem = input_path.stem
        out_dir = OUTPUT_FOLDER

        # ── Step 0: Silence Removal ─────────────────────────
        if settings.get("remove_silences"):
            step("Removing silences", 5, "Detecting silent segments...")
            from pipeline.silence_remover import remove_silences
            clean_path = str(out_dir / f"{stem}_clean.mp4")
            # CORRECT
            remove_silences(
                str(input_path), clean_path,
                silence_threshold=float(settings.get("silence_threshold", -35)),
                min_silence_duration=float(settings.get("min_silence", 0.5)),
            )
            input_path = Path(clean_path)
            stem = input_path.stem
            step("Removing silences", 10, "✓ Silences removed")

        # ── Step 1: Extract Audio ───────────────────────────
        step("Extracting audio", 12, "Converting to WAV...")
        from pipeline.extract_audio import extract_audio
        audio_path = str(out_dir / f"{stem}_audio.wav")
        extract_audio(str(input_path), audio_path)
        step("Extracting audio", 18, "✓ Audio extracted")

        # ── Step 2: Transcribe ──────────────────────────────
        step("Transcribing", 20, f"Loading Whisper {settings.get('model','medium')}...")
        from pipeline.transcribe import transcribe_audio
        result = transcribe_audio(
            audio_path,
            model_name=settings.get("model", "medium"),
            language=settings.get("language") or None,
            word_timestamps=True,
            bilingual_correction=settings.get("bilingual_correction", True),
        )
        segments = result["segments"]
        job["segments"] = segments
        step("Transcribing", 40, f"✓ {len(segments)} segments transcribed")

        # ── Step 2a: AI Review ──────────────────────────────
        if settings.get("ai_review") and os.getenv("GEMINI_API_KEY"):
            step("AI Review", 42, "Analyzing transcript for safe cut points...")
            from pipeline.ai_reviewer import review_transcript, apply_review
            review = review_transcript(
                segments,
                language=settings.get("language", "id"),
                strength=int(settings.get("filler_strength", 50)),
            )
            segments, ai_removed = apply_review(segments, review)
            step("AI Review", 52, f"✓ {len(ai_removed)} AI-approved cuts applied")

        # ── Step 2b: Filler Removal ─────────────────────────
        if settings.get("remove_fillers"):
            strength = int(settings.get("filler_strength", 50))
            step("Removing fillers", 54, f"Detecting fillers (strength={strength})...")
            from pipeline.filler_remover import clean_segments, cut_filler_segments, remap_timestamps
            from pipeline.silence_remover import get_video_duration
            segments, removed_intervals = clean_segments(
                segments,
                strength=strength,
                use_gemini=settings.get("bilingual_correction", True),
            )
            if removed_intervals:
                dur = get_video_duration(str(input_path))
                filler_free = str(out_dir / f"{stem}_nofiller.mp4")
                cut_filler_segments(str(input_path), filler_free, removed_intervals, dur)
                segments = remap_timestamps(segments, removed_intervals)
                input_path = Path(filler_free)
                stem = input_path.stem
            step("Removing fillers", 62, f"✓ Fillers removed")

        # ── Build review data for UI ────────────────────────
        step("Building review", 65, "Preparing Review UI data...")
        review_data = build_review_data(segments)
        job["review_data"] = review_data
        job["current_video"] = str(input_path)
        job["segments"] = segments
        job["status"] = "review"

        emit(q, "review_ready", {
            "job_id": job_id,
            "review_data": review_data,
            "segment_count": len(segments),
        })
        step("Ready for Review", 70, "Review the captions and mark cuts")

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        job["status"] = "error"
        job["error"] = str(e)
        emit(q, "error", {"message": str(e), "detail": err})
    finally:
        q.put(None)


def run_render(job_id: str, removed_words: list, removed_gaps: list, q: queue.Queue):
    job = jobs[job_id]

    def step(name, pct, detail=""):
        job["step"] = name
        job["progress"] = pct
        emit(q, "progress", {"step": name, "pct": pct, "detail": detail})

    try:
        from dotenv import load_dotenv
        load_dotenv(str(BORA_ROOT / ".env"))

        settings = job.get("settings", {})
        input_path = Path(job["current_video"])
        stem = input_path.stem
        out_dir = OUTPUT_FOLDER
        segments = job["segments"]

        # ── Apply manual cuts ───────────────────────────────
        all_cuts = removed_words + removed_gaps
        if all_cuts:
            step("Applying manual cuts", 72, f"Cutting {len(all_cuts)} selected intervals...")
            from pipeline.filler_remover import cut_filler_segments, remap_timestamps
            from pipeline.silence_remover import get_video_duration

            dur = get_video_duration(str(input_path))
            cut_path = str(out_dir / f"{stem}_cut.mp4")
            cut_filler_segments(str(input_path), cut_path, all_cuts, dur)
            segments = remap_timestamps(segments, all_cuts)
            input_path = Path(cut_path)
            stem = input_path.stem
            step("Applying manual cuts", 78, "✓ Cuts applied")

        # ── Generate Captions ───────────────────────────────
        step("Generating captions", 80, "Building caption file...")
        from pipeline import generate_srt

        srt_path = str(out_dir / f"{stem}.srt")
        generate_srt(segments, srt_path)

        if settings.get("word_by_word"):
            from pipeline import generate_word_by_word_ass
            caption_path = str(out_dir / f"{stem}.ass")
            generate_word_by_word_ass(
                segments, caption_path,
                words_per_line=int(settings.get("words_per_line", 2)),
                style=settings.get("style", "tiktok"),
            )
        else:
            from pipeline import generate_ass
            caption_path = str(out_dir / f"{stem}.ass")
            generate_ass(segments, caption_path, style=settings.get("style", "tiktok"))

        step("Generating captions", 85, "✓ Captions generated")

        # ── Keyword Highlighting ────────────────────────────
        if settings.get("highlight_keywords") and os.getenv("GEMINI_API_KEY"):
            step("Keyword highlighting", 87, "Extracting keywords with AI...")
            from pipeline.keyword_extractor import extract_keywords_gemini
            # keywords handled inside generate_word_by_word_ass already via segments

        # ── Burn Captions ───────────────────────────────────
        step("Burning captions", 88, "Rendering final video...")
        final_name = f"{Path(job['filename']).stem}_bora.mp4"
        final_path = str(out_dir / final_name)

        from pipeline.burn_captions import burn_captions
        burn_captions(str(input_path), caption_path, final_path, gpu=settings.get("gpu", False))

        job["result_path"] = final_name
        job["status"] = "done"
        step("Done", 100, f"✓ {final_name}")
        emit(q, "done", {"result": final_name, "path": f"/output/{final_name}"})

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        job["status"] = "error"
        job["error"] = str(e)
        emit(q, "error", {"message": str(e), "detail": err})
    finally:
        q.put(None)


def build_review_data(segments: list) -> dict:
    """Convert segments into review-friendly format for the UI."""
    words = []
    gaps = []

    all_words = []
    for seg in segments:
        for w in seg.get("words", []):
            all_words.append({
                "word": w.get("word", "").strip(),
                "start": round(w.get("start", 0), 3),
                "end": round(w.get("end", 0), 3),
                "segment_text": seg.get("text", ""),
            })

    words = all_words

    # Detect gaps
    for i in range(1, len(all_words)):
        gap = all_words[i]["start"] - all_words[i - 1]["end"]
        if gap >= 0.2:
            gaps.append({
                "start": round(all_words[i - 1]["end"], 3),
                "end": round(all_words[i]["start"], 3),
                "duration": round(gap, 3),
                "before": all_words[i - 1]["word"],
                "after": all_words[i]["word"],
            })

    sentences = []
    for seg in segments:
        sentences.append({
            "start": round(seg.get("start", 0), 3),
            "end": round(seg.get("end", 0), 3),
            "text": seg.get("text", "").strip(),
        })

    return {"words": words, "gaps": gaps, "sentences": sentences}


if __name__ == "__main__":
    print("BORA Web UI — http://localhost:5000")
    app.run(debug=True, port=5000, threaded=True)
