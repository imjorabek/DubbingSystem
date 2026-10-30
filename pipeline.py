import os
import subprocess
from openai import OpenAI
from elevenlabs.client import ElevenLabs

# API kalitlarni muhit o'zgaruvchilaridan (environment variables) yoki to'g'ridan-to'g'ri sozlash
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "YOUR_ELEVENLABS_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)


def download_video(video_url: str, output_dir: str = "downloads") -> tuple[str, str]:
    """1-qadam: Link orqali video va audioni aslicha yuklab olish"""
    os.makedirs(output_dir, exist_ok=True)
    video_path = os.path.join(output_dir, "original_video.mp4")
    audio_path = os.path.join(output_dir, "original_audio.wav")

    # Videoni vizual sifatini saqlagan holda yuklash
    cmd_video = f'yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 -o "{video_path}" "{video_url}"'
    subprocess.run(cmd_video, shell=True, check=True)

    # Audioni alohida WAV formatida ajratib olish
    cmd_audio = f'ffmpeg -y -i "{video_path}" -vn -acodec pcm_s16le -ar 44100 "{audio_path}"'
    subprocess.run(cmd_audio, shell=True, check=True)

    return video_path, audio_path


def separate_audio(audio_path: str, output_dir: str = "separated") -> tuple[str, str]:
    """
    2-qadam: Audiodan spiker ovozi (Vocals) va Fon musiqasini (Background Music)
    bir-biridan ajratish (Demucs AI yordamida)
    """
    cmd_demucs = f'demucs --two-stems=vocals "{audio_path}" -o "{output_dir}"'
    subprocess.run(cmd_demucs, shell=True, check=True)

    track_name = os.path.splitext(os.path.basename(audio_path))[0]
    vocals_path = os.path.join(output_dir, "htdemucs", track_name, "vocals.wav")
    bgm_path = os.path.join(output_dir, "htdemucs", track_name, "no_vocals.wav")

    return vocals_path, bgm_path


def transcribe_and_translate(vocals_path: str) -> str:
    """3-qadam: Nutqni matnga o'girish (Whisper) va O'zbek tiliga tarjima qilish (GPT-4o)"""
    # STT: Whisper orqali asl nutq matnini olish
    with open(vocals_path, "rb") as audio_file:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file
        )
    original_text = transcript.text

    # Translation: Context va ma'noni buzmasdan O'zbek tiliga o'girish
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Sana berilgan matn video nutqidan olingan. "
                    "Mazmun va kontekstni zarracha buzmagan holda, "
                    "uni tabiiy va ravon O'ZBEK tiliga tarjima qilib ber."
                )
            },
            {"role": "user", "content": original_text}
        ]
    )
    translated_text = response.choices[0].message.content
    return translated_text


def generate_uzbek_audio(translated_text: str, output_path: str = "uzbek_voice.mp3") -> str:
    """4-qadam: Yangi ElevenLabs SDK orqali matnni audioga o'girish va saqlash"""
    
    # Audio generatorini chaqirish
    audio_stream = elevenlabs_client.text_to_speech.convert(
        text=translated_text,
        voice_id="JBFqnCBsd6RMkjVDRZzb",  # Masalan, 'George' yoki boshqa spiker voice_id si
        model_id="eleven_multilingual_v2"
    )

    # Audioni faylga yozish
    with open(output_path, "wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)

    return output_path


def merge_audio_and_video(
    original_video: str, 
    bgm_audio: str, 
    uzbek_audio: str, 
    output_video: str = "final_output.mp4"
) -> str:
    """
    5-qadam: Asl videoga fon musiqasi va yangi O'zbekcha ovozni mikser qilib ulash.
    Video kadrlari o'zgarmaydi (-c:v copy parametriga ko'ra stream-copy qilinadi).
    """
    cmd = (
        f'ffmpeg -y -i "{original_video}" -i "{uzbek_audio}" -i "{bgm_audio}" '
        f'-filter_complex "[1:a]volume=1.0[v1];[2:a]volume=0.8[v2];[v1][v2]amix=inputs=2:duration=first[aout]" '
        f'-map 0:v:0 -map "[aout]" -c:v copy -c:a aac "{output_video}"'
    )
    subprocess.run(cmd, shell=True, check=True)
    return output_video


if __name__ == "__main__":
    # Sinov uchun video URL
    TEST_URL = "https://www.youtube.com/watch?example"
    
    print("1/5: Video va audio yuklanmoqda...")
    v_path, a_path = download_video(TEST_URL)
    
    print("2/5: Ovoz va fon musiqasi ajratilmoqda...")
    vocals, bgm = separate_audio(a_path)
    
    print("3/5: Matnga o'girilib, O'zbek tiliga tarjima qilinmoqda...")
    uz_text = transcribe_and_translate(vocals)
    
    print("4/5: O'zbekcha yangi audio yaratilmoqda...")
    uz_audio = generate_uzbek_audio(uz_text)
    
    print("5/5: Audio va video sinxronlanmoqda...")
    final_result = merge_audio_and_video(v_path, bgm, uz_audio)
    
    print(f"Jarayon yakunlandi! Tayyor fayl: {final_result}")