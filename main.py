import os
import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 1-bosqichda yozilgan pipeline.py faylidan funksiyalarni import qilamiz
from pipeline import (
    download_video,
    separate_audio,
    transcribe_and_translate,
    generate_uzbek_audio,
    merge_audio_and_video
)

app = FastAPI(title="AI Video Dubbing API")

# Frontend (Next.js) so'rovlarini o'tkazish uchun CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Qayta ishlangan tayyor video fayllarni static papkadan ko'rsatish
os.makedirs("outputs", exist_ok=True)
app.mount("/static", StaticFiles(directory="outputs"), name="static")

# Jarayonlar holatini xotirada saqlash uchun lug'at (In-Memory Status DB)
jobs_db = {}

class ProcessRequest(BaseModel):
    video_url: str

def process_video_task(job_id: str, video_url: str):
    """Fonda ishlaydigan va pipeline.py funksiyalarini tartib bilan chaqiradigan vazifa"""
    try:
        job_dir = os.path.join("outputs", job_id)
        os.makedirs(job_dir, exist_ok=True)

        # 1-qadam
        jobs_db[job_id]["status"] = "downloading"
        jobs_db[job_id]["message"] = "Video va audio yuklab olinmoqda..."
        v_path, a_path = download_video(video_url, output_dir=job_dir)

        # 2-qadam
        jobs_db[job_id]["status"] = "separating"
        jobs_db[job_id]["message"] = "Fon musiqasi va spiker nutqi ajratilmoqda..."
        vocals, bgm = separate_audio(a_path, output_dir=job_dir)

        # 3-qadam
        jobs_db[job_id]["status"] = "translating"
        jobs_db[job_id]["message"] = "Nutq matnga o'girilib, O'zbek tiliga tarjima qilinmoqda..."
        uzbek_text = transcribe_and_translate(vocals)

        # 4-qadam
        jobs_db[job_id]["status"] = "synthesizing"
        jobs_db[job_id]["message"] = "O'zbekcha yangi ovoz yaratilmoqda..."
        uz_audio_path = os.path.join(job_dir, "uzbek_voice.mp3")
        generate_uzbek_audio(uzbek_text, output_path=uz_audio_path)

        # 5-qadam
        jobs_db[job_id]["status"] = "merging"
        jobs_db[job_id]["message"] = "Videoga yangi audio sinxronlanmoqda..."
        final_video_path = os.path.join(job_dir, "final.mp4")
        merge_audio_and_video(v_path, bgm, uz_audio_path, output_video=final_video_path)

        # Yakuniy natija
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["message"] = "Tarjima tayyor!"
        jobs_db[job_id]["result_url"] = f"http://127.0.0.1:8000/static/{job_id}/final.mp4"

    except Exception as e:
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["error"] = str(e)


@app.post("/api/v1/translate")
async def start_translation(req: ProcessRequest, background_tasks: BackgroundTasks):
    """1. Frontenddan link qabul qilish va background_task yaratish"""
    job_id = str(uuid.uuid4())
    jobs_db[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "message": "Jarayon navbatga qo'shildi",
        "result_url": None,
        "error": None
    }
    
    # Videoni fonda qayta ishlashni boshlash (Backend qotib qolmasligi uchun)
    background_tasks.add_task(process_video_task, job_id, req.video_url)
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/v1/status/{job_id}")
async def get_status(job_id: str):
    """2. Frontend har bir necha sekundda jarayon holatini tekshirishi uchun API"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Jarayon topilmadi")
    return jobs_db[job_id]