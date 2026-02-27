import os
import sys
import time
from datetime import datetime

import gradio as gr
from dotenv import load_dotenv
from loguru import logger

# --- 1. SETUP LOGGING ---
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add("voice_diary.log", rotation="10 MB", level="DEBUG")

logger.info("🚀 Starting Voice Diary App...")

# --- 2. LOAD DEPENDENCIES ---
try:
    from deepgram import DeepgramClient, PrerecordedOptions

    # Using the standard 'pcloud' library (PyPI package: pcloud)
    from pcloud import PyCloud

    logger.success("✅ Libraries imported successfully")
except ImportError as e:
    logger.critical(f"❌ Library Import Error: {e}")
    logger.info("💡 Tip: Run 'uv pip install pcloud deepgram-sdk==3.4.0'")
    sys.exit(1)

load_dotenv()

# --- 3. CONFIGURATION ---
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
PCLOUD_USERNAME = os.getenv("PCLOUD_USERNAME")
PCLOUD_PASSWORD = os.getenv("PCLOUD_PASSWORD")
APP_USERNAME = os.getenv("APP_USERNAME")
APP_PASSWORD = os.getenv("APP_PASSWORD")

if not all(
    [DEEPGRAM_API_KEY, PCLOUD_USERNAME, PCLOUD_PASSWORD, APP_PASSWORD, APP_USERNAME]
):
    logger.error("❌ Missing environment variables! Check .env file.")
    sys.exit(1)

# --- 4. INITIALIZE CLIENTS ---
try:
    # Deepgram Client (v3.4.0 standard)
    deepgram = DeepgramClient(api_key=DEEPGRAM_API_KEY)
    logger.info("🔹 Deepgram Client initialized")

    # pCloud Client (Standard PyCloud)
    # Note: PyCloud uses positional args for username/password
    pc = PyCloud(PCLOUD_USERNAME, PCLOUD_PASSWORD, endpoint="eapi")
    logger.info(f"🔹 pCloud Client initialized for user: {PCLOUD_USERNAME}")
except Exception as e:
    logger.critical(f"❌ Client Initialization Failed: {e}")
    sys.exit(1)

# --- USAGE TRACKING ---
usage_stats = {
    "session_start": datetime.now(),
    "transcriptions": {
        "count": 0,
        "total_audio_minutes": 0.0,
        "total_api_latency_ms": 0.0,
        "errors": 0,
        "last_transcription": None,
    },
    "saves": {"count": 0, "errors": 0, "last_save": None},
    "deepgram": {"estimated_cost_usd": 0.0, "total_api_calls": 0},
    "errors": [],
}
logger.info("📊 Usage tracking initialized")

# --- LOCAL BACKUP DIR ---
BACKUP_DIR = "/tmp/diary_backups"
os.makedirs(BACKUP_DIR, exist_ok=True)
logger.info(f"📁 Local backup directory: {BACKUP_DIR}")


# --- 5. HELPER FUNCTIONS ---
def ensure_diary_folder():
    """Ensure '/Diary' folder exists in pCloud"""
    try:
        logger.debug("Checking pCloud folder structure...")

        # Method: listfolder(folderid=0) - Standard pcloud syntax
        root = pc.listfolder(folderid=0)

        # Check metadata contents
        contents = root.get("metadata", {}).get("contents", [])

        for item in contents:
            if item.get("name") == "Diary" and item.get("isfolder"):
                folder_id = item.get("folderid")
                logger.debug(f"✅ Found existing Diary folder (ID: {folder_id})")
                return folder_id

        # Create if missing
        logger.info("⚠️ Diary folder not found. Creating...")
        # Method: createfolder(path='/Diary')
        res = pc.createfolder(path="/Diary")
        new_id = res["metadata"]["folderid"]
        logger.success(f"✅ Created new Diary folder (ID: {new_id})")
        return new_id

    except Exception as e:
        logger.error(f"❌ Folder Error: {e}")
        return None


def transcribe_audio(audio_path):
    """Transcribe audio file using Deepgram"""
    if not audio_path:
        logger.warning("⚠️ No audio file received from frontend")
        return "No audio file provided"

    logger.info(f"🎤 Processing audio file: {audio_path}")

    try:
        file_size = os.path.getsize(audio_path)
        logger.debug(f"File size: {file_size / 1024:.2f} KB")

        with open(audio_path, "rb") as audio:
            buffer_data = audio.read()

        payload = {"buffer": buffer_data}

        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
            language="en",
            diarize=True,
        )

        logger.info("📡 Sending request to Deepgram API...")
        start_time = time.perf_counter()
        response = deepgram.listen.rest.v("1").transcribe_file(payload, options)
        latency_ms = (time.perf_counter() - start_time) * 1000

        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]

        # Extract duration and calculate cost (nova-2: $0.0043/min)
        try:
            duration_seconds = response["metadata"]["duration"]
        except (KeyError, TypeError):
            duration_seconds = 0
        duration_minutes = duration_seconds / 60
        cost = duration_minutes * 0.0043

        # Update usage stats
        usage_stats["transcriptions"]["count"] += 1
        usage_stats["transcriptions"]["total_audio_minutes"] += duration_minutes
        usage_stats["transcriptions"]["total_api_latency_ms"] += latency_ms
        usage_stats["transcriptions"]["last_transcription"] = (
            datetime.now().isoformat()
        )
        usage_stats["deepgram"]["total_api_calls"] += 1
        usage_stats["deepgram"]["estimated_cost_usd"] += cost

        logger.success(
            f"✅ Transcription complete ({len(transcript)} chars) | "
            f"{duration_minutes:.2f}min | {latency_ms:.0f}ms | ${cost:.4f}"
        )
        if transcript:
            logger.info(f"📝 Transcript text: {transcript}")
        return transcript

    except Exception as e:
        usage_stats["transcriptions"]["errors"] += 1
        usage_stats["errors"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "type": "transcription",
                "error": str(e),
            }
        )
        logger.exception("❌ Transcription Failed")
        return f"Transcription error: {str(e)}"


def save_transcript(text):
    """Save transcript to pCloud"""
    if not text or not text.strip():
        logger.warning("⚠️ Attempted to save empty transcript")
        return "Cannot save empty transcript"

    logger.info("💾 Saving transcript to pCloud...")

    try:
        folder_id = ensure_diary_folder()
        if not folder_id:
            logger.error("❌ Aborting save: Could not access Diary folder")
            usage_stats["saves"]["errors"] += 1
            return "Error: Could not access Diary folder"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_diary.txt"
        backup_path = os.path.join(BACKUP_DIR, filename)
        temp_path = f"/tmp/{filename}"

        # Write local backup first (survives pCloud failures)
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"💾 Local backup saved: {backup_path}")

        # Write temp file for pCloud upload
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)

        logger.debug(f"Uploading {filename} to folder ID {folder_id}...")

        # Method: uploadfile(files=[path], folderid=id) - Standard pcloud syntax
        pc.uploadfile(files=[temp_path], folderid=folder_id)

        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        # Remove backup only after successful pCloud upload
        if os.path.exists(backup_path):
            os.remove(backup_path)
            logger.debug(f"🗑️ Backup cleaned up after successful upload: {filename}")

        usage_stats["saves"]["count"] += 1
        usage_stats["saves"]["last_save"] = datetime.now().isoformat()
        logger.success(f"✅ Saved successfully: {filename}")
        return f"Saved: {filename}"

    except Exception as e:
        usage_stats["saves"]["errors"] += 1
        usage_stats["errors"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "type": "save",
                "error": str(e),
            }
        )
        logger.exception("❌ Save Operation Failed")
        return f"Save error: {str(e)}"


def transcribe_and_save(audio_path):
    """Transcribe audio and auto-save to pCloud"""
    transcript = transcribe_audio(audio_path)
    if transcript and not transcript.startswith(("No audio", "Transcription error")):
        save_result = save_transcript(transcript)
    else:
        save_result = ""
    return transcript, save_result


def get_usage_stats():
    """Get formatted usage statistics for display"""
    uptime = datetime.now() - usage_stats["session_start"]
    count = usage_stats["transcriptions"]["count"]
    avg_latency = (
        usage_stats["transcriptions"]["total_api_latency_ms"] / count
        if count > 0
        else 0
    )

    return {
        "session": {
            "started": usage_stats["session_start"].strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": str(uptime).split(".")[0],
        },
        "transcriptions": {
            "total": count,
            "audio_minutes": round(
                usage_stats["transcriptions"]["total_audio_minutes"], 2
            ),
            "avg_api_latency_ms": round(avg_latency, 2),
            "errors": usage_stats["transcriptions"]["errors"],
            "last": usage_stats["transcriptions"]["last_transcription"],
        },
        "deepgram": {
            "api_calls": usage_stats["deepgram"]["total_api_calls"],
            "estimated_cost_usd": f"${usage_stats['deepgram']['estimated_cost_usd']:.4f}",
        },
        "saves": {
            "successful": usage_stats["saves"]["count"],
            "errors": usage_stats["saves"]["errors"],
            "last": usage_stats["saves"]["last_save"],
        },
        "recent_errors": usage_stats["errors"][-5:],
    }


# --- 6. GRADIO APP ---
logger.info("🎨 Building Gradio Interface...")

with gr.Blocks(title="Voice Diary", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🎙️ Voice Diary")

    with gr.Tabs():
        with gr.Tab("Diary"):
            audio_input = gr.Audio(
                sources=["microphone"], type="filepath", label="Record & Transcribe"
            )

            transcript_box = gr.Textbox(
                label="Transcript", lines=5, interactive=True
            )

            with gr.Row():
                save_btn = gr.Button("Save to pCloud", variant="secondary")
                status_msg = gr.Textbox(label="Status", interactive=False)

            audio_input.stop_recording(
                fn=transcribe_and_save,
                inputs=audio_input,
                outputs=[transcript_box, status_msg],
            )
            save_btn.click(
                fn=save_transcript, inputs=transcript_box, outputs=status_msg
            )

        with gr.Tab("Stats"):
            gr.Markdown("## 📊 Usage Statistics")
            stats_display = gr.JSON(label="Statistics", show_label=False)
            refresh_btn = gr.Button("Refresh Stats", variant="secondary")

            app.load(fn=get_usage_stats, outputs=stats_display)
            refresh_btn.click(fn=get_usage_stats, outputs=stats_display)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"🌍 Launching Server on 0.0.0.0:{port}")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        auth=(APP_USERNAME, APP_PASSWORD),
        pwa=True,
    )
