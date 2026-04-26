from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from pathlib import Path
from datetime import datetime, timezone
import os
import socket
import json
import uuid
import subprocess
import sys
import shutil
import threading
import traceback

app = Flask(__name__)

ROOT = Path(__file__).parent
UPLOADS = ROOT / "uploads"
STEMS = ROOT / "stems"
SEPARATED = ROOT / "separated"
TRACKS_FILE = ROOT / "tracks.json"

UPLOADS.mkdir(exist_ok=True)
STEMS.mkdir(exist_ok=True)
SEPARATED.mkdir(exist_ok=True)

TD_HOST = "127.0.0.1"
TD_PORT = 7000

jobs = {}
tracks_lock = threading.Lock()

ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"
}

EXPECTED_STEMS = ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]


def build_demucs_env():
    env = os.environ.copy()

    if os.name != "nt":
        return env

    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]

    shared_entry = next(
        (
            entry
            for entry in path_entries
            if "gyan.ffmpeg.shared" in entry.lower().replace("/", "\\")
            and "full_build-shared\\bin" in entry.lower().replace("/", "\\")
        ),
        None,
    )

    def is_conflicting_non_shared_ffmpeg(entry):
        normalized = entry.lower().replace("/", "\\")
        return (
            "gyan.ffmpeg_microsoft.winget.source" in normalized
            and "full_build\\bin" in normalized
            and "full_build-shared\\bin" not in normalized
        )

    cleaned_entries = []

    if shared_entry:
        cleaned_entries.append(shared_entry)

    for entry in path_entries:
        if shared_entry and entry == shared_entry:
            continue
        if is_conflicting_non_shared_ffmpeg(entry):
            continue
        cleaned_entries.append(entry)

    env["PATH"] = os.pathsep.join(cleaned_entries)
    return env


def send_to_touchdesigner(data):
    message = json.dumps(data).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(message, (TD_HOST, TD_PORT))
    sock.close()


def load_tracks():
    if not TRACKS_FILE.exists():
        return []

    try:
        data = json.loads(TRACKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict) and "id" in item and "name" in item]


def save_tracks(tracks):
    TRACKS_FILE.write_text(json.dumps(tracks, indent=2), encoding="utf-8")


def track_display_name(original_name):
    cleaned = Path(original_name).stem.replace("_", " ").strip()
    return cleaned or "Untitled Track"


def upsert_track(track_id, track_name, original_name):
    record = {
        "id": track_id,
        "name": track_name,
        "originalFile": original_name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "stems": {
            stem_name[:-4]: f"/stems/{track_id}/{stem_name}"
            for stem_name in EXPECTED_STEMS
        },
    }

    with tracks_lock:
        tracks = [entry for entry in load_tracks() if entry.get("id") != track_id]
        tracks.insert(0, record)
        save_tracks(tracks)

    return record


def set_job(job_id, state, message, progress, track_id=None, track_name=None):
    previous = jobs.get(job_id, {})
    payload = {
        "state": state,
        "message": message,
        "progress": progress
    }

    resolved_track_id = track_id if track_id is not None else previous.get("trackId")
    resolved_track_name = track_name if track_name is not None else previous.get("trackName")

    if resolved_track_id is not None:
        payload["trackId"] = resolved_track_id
    if resolved_track_name is not None:
        payload["trackName"] = resolved_track_name

    jobs[job_id] = payload


def run_demucs(job_id, track_id, track_name, original_name, song_path):
    try:
        set_job(job_id, "running", "Starting Demucs stem separation...", 10, track_id=track_id, track_name=track_name)

        command = [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            "htdemucs",
            "--out",
            str(SEPARATED),
            str(song_path)
        ]

        set_job(job_id, "running", "Splitting song into vocals, drums, bass, and other. This can take a few minutes...", 35, track_id=track_id, track_name=track_name)

        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=build_demucs_env(),
        )

        if completed.returncode != 0:
            set_job(job_id, "error", "Demucs failed. Check the terminal for the full error.", 0, track_id=track_id, track_name=track_name)
            print(completed.stdout)
            return

        set_job(job_id, "running", "Copying stems into the web app...", 80, track_id=track_id, track_name=track_name)

        output_folder = SEPARATED / "htdemucs" / song_path.stem
        track_folder = STEMS / track_id
        track_folder.mkdir(parents=True, exist_ok=True)

        missing = []

        for stem_name in EXPECTED_STEMS:
            source = output_folder / stem_name
            destination = track_folder / stem_name

            if source.exists():
                shutil.copy(source, destination)
            else:
                missing.append(stem_name)

        if missing:
            set_job(job_id, "error", "Missing stems: " + ", ".join(missing), 0, track_id=track_id, track_name=track_name)
            return

        upsert_track(track_id, track_name, original_name)
        set_job(job_id, "done", "Done. Track saved and ready. Press Play / Resume.", 100, track_id=track_id, track_name=track_name)

    except Exception:
        set_job(job_id, "error", "Something went wrong while splitting the song.", 0, track_id=track_id, track_name=track_name)
        traceback.print_exc()


@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.route("/stems/<track_id>/<path:filename>")
def track_stems(track_id, filename):
    safe_track_id = secure_filename(track_id)
    track_folder = STEMS / safe_track_id

    if not track_folder.exists() or not (track_folder / filename).exists():
        return jsonify({"ok": False, "error": "Stem file not found for this track."}), 404

    return send_from_directory(track_folder, filename)


@app.route("/stems/<path:filename>")
def stems(filename):
    with tracks_lock:
        tracks = load_tracks()

    if tracks:
        latest_track_id = tracks[0].get("id")
        if latest_track_id:
            latest_folder = STEMS / latest_track_id
            if (latest_folder / filename).exists():
                return send_from_directory(latest_folder, filename)

    return send_from_directory(STEMS, filename)


@app.route("/api/upload-song", methods=["POST"])
def upload_song():
    if "song" not in request.files:
        return jsonify({"ok": False, "error": "No song file was uploaded."}), 400

    song = request.files["song"]

    if song.filename == "":
        return jsonify({"ok": False, "error": "No file selected."}), 400

    original_name = secure_filename(song.filename)
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "ok": False,
            "error": "Unsupported file type. Try mp3, wav, m4a, flac, ogg, or aac."
        }), 400

    track_id = uuid.uuid4().hex
    track_name = track_display_name(original_name)
    job_id = track_id
    saved_name = f"{track_id}_{original_name}"
    song_path = UPLOADS / saved_name
    song.save(song_path)

    set_job(job_id, "queued", "Song uploaded. Waiting to start splitting...", 5, track_id=track_id, track_name=track_name)

    thread = threading.Thread(
        target=run_demucs,
        args=(job_id, track_id, track_name, original_name, song_path),
        daemon=True
    )
    thread.start()

    return jsonify({
        "ok": True,
        "jobId": job_id,
        "trackId": track_id,
        "trackName": track_name,
        "message": "Upload received. Stem splitting started."
    })


@app.route("/api/split-status/<job_id>")
def split_status(job_id):
    if job_id not in jobs:
        return jsonify({
            "ok": False,
            "error": "Unknown job id."
        }), 404

    return jsonify({
        "ok": True,
        **jobs[job_id]
    })


@app.route("/api/tracks")
def tracks():
    with tracks_lock:
        all_tracks = load_tracks()

    return jsonify({
        "ok": True,
        "tracks": all_tracks
    })


@app.route("/api/control", methods=["POST"])
def control():
    data = request.get_json(force=True)
    send_to_touchdesigner(data)
    return jsonify({"ok": True, "sent": data})


if __name__ == "__main__":
    print()
    print("Stem Hand Controller running.")
    print("Open http://localhost:5050")
    print("TouchDesigner UDP output: 127.0.0.1:7000")
    print()
    app.run(host="0.0.0.0", port=5050, debug=True)
