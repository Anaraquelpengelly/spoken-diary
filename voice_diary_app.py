import gradio as gr
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# --- 1. SETUP LOGGING ---
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
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

if not all([DEEPGRAM_API_KEY, PCLOUD_USERNAME, PCLOUD_PASSWORD]):
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

# --- 5. HELPER FUNCTIONS ---
def ensure_diary_folder():
    """Ensure '/Diary' folder exists in pCloud"""
    try:
        logger.debug("Checking pCloud folder structure...")
        
        # Method: listfolder(folderid=0) - Standard pcloud syntax
        root = pc.listfolder(folderid=0)
        
        # Check metadata contents
        contents = root.get('metadata', {}).get('contents', [])
        
        for item in contents:
            if item.get('name') == 'Diary' and item.get('isfolder'):
                folder_id = item.get('folderid')
                logger.debug(f"✅ Found existing Diary folder (ID: {folder_id})")
                return folder_id
        
        # Create if missing
        logger.info("⚠️ Diary folder not found. Creating...")
        # Method: createfolder(path='/Diary')
        res = pc.createfolder(path='/Diary')
        new_id = res['metadata']['folderid']
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
        
        with open(audio_path, 'rb') as audio:
            buffer_data = audio.read()
        
        payload = {"buffer": buffer_data}
        
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
            language="en",
        )
        
        logger.info("📡 Sending request to Deepgram API...")
        # Standard v3.4+ REST call
        response = deepgram.listen.rest.v("1").transcribe_file(payload, options)
        
        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
        logger.success(f"✅ Transcription complete ({len(transcript)} chars)")
        return transcript
        
    except Exception as e:
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
            return "Error: Could not access Diary folder"
            
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_diary.txt"
        temp_path = f"/tmp/{filename}"
        
        # Ensure /tmp exists
        os.makedirs("/tmp", exist_ok=True)
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
        logger.debug(f"Uploading {filename} to folder ID {folder_id}...")
        
        # Method: uploadfile(files=[path], folderid=id) - Standard pcloud syntax
        pc.uploadfile(files=[temp_path], folderid=folder_id)
        
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        logger.success(f"✅ Saved successfully: {filename}")
        return f"Saved: {filename}"
        
    except Exception as e:
        logger.exception("❌ Save Operation Failed")
        return f"Save error: {str(e)}"

# --- 6. GRADIO APP ---
logger.info("🎨 Building Gradio Interface...")

with gr.Blocks(title="Voice Diary", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🎙️ Voice Diary")
    
    with gr.Row():
        # type="filepath" ensures we get a path string, not raw bytes
        audio_input = gr.Audio(sources=["microphone"], type="filepath", label="Record")
        transcribe_btn = gr.Button("Transcribe", variant="primary")
    
    transcript_box = gr.Textbox(label="Transcript", lines=5, interactive=True)
    
    with gr.Row():
        save_btn = gr.Button("Save to pCloud", variant="secondary")
        status_msg = gr.Textbox(label="Status", interactive=False)
    
    # Event Listeners
    transcribe_btn.click(
        fn=transcribe_audio, 
        inputs=audio_input, 
        outputs=transcript_box
    )
    
    save_btn.click(
        fn=save_transcript, 
        inputs=transcript_box, 
        outputs=status_msg
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"🌍 Launching Server on 0.0.0.0:{port}")
    app.launch(server_name="0.0.0.0", server_port=port, pwa=True)
