# Voice Diary App

A simple voice diary application that records audio, transcribes it using Deepgram, and saves transcripts to pCloud.

## Setup

1. **Clone the repository**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your credentials:
   - Get Deepgram API key from https://deepgram.com (comes with $200 free credit)
   - Use your pCloud email and password

4. **Run locally**
   ```bash
   python voice_diary_app.py
   ```
   
   Open http://localhost:7860 in your browser (or phone browser on same network)

## Deployment

### Railway
1. Push to GitHub
2. Connect repo to Railway
3. Add environment variables in Railway dashboard (don't use .env file in production)
4. Deploy

### Render/Fly.io
Similar process - set environment variables in their dashboards.

## Usage

1. Click the microphone to record your diary entry
2. Click "Transcribe" to convert speech to text
3. Review and edit the transcript if needed
4. Click "Save to pCloud" to save to your Diary folder

Files are saved as `YYYY-MM-DD_HH-MM-SS_diary.txt`
