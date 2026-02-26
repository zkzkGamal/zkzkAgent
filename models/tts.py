from kokoro import KPipeline
import sounddevice as sd
import torch

pipeline = KPipeline(lang_code='a')

def speak(text):
    if not text or not text.strip():
        text = "error the generate content pls try again"
    generator = pipeline(text, voice='af_heart')
    for i, (gs, ps, audio) in enumerate(generator):
        print(f"[Chunk {i}] gs={gs}, ps={ps}, audio_len={len(audio)}")
    # Play audio chunk immediately
    sd.play(audio, samplerate=24000)
    sd.wait()  # Wait until this chunk finishes before continuing
