# from kokoro import KPipeline
# import sounddevice as sd
# import torch

# pipeline = KPipeline(lang_code='a')

# def speak(text):
#     if not text or not text.strip():
#         text = "error the generate content pls try again"
#     generator = pipeline(text, voice='af_heart')
#     for i, (gs, ps, audio) in enumerate(generator):
#         print(f"[Chunk {i}] gs={gs}, ps={ps}, audio_len={len(audio)}")
#     # Play audio chunk immediately
#     sd.play(audio, samplerate=24000)
#     sd.wait()  # Wait until this chunk finishes before continuing


import wave
import sounddevice as sd
import soundfile as sf  
from piper.voice import PiperVoice

# Load your voice
voice = PiperVoice.load("./models/voices/en_US-amy-medium.onnx")
temp_file="temp_output.wav"

def speak(text):
    if not text or not text.strip():
        text = "error the generate content pls try again"
    with wave.open(temp_file, "wb") as wav_file:
        wav_file.setnchannels(1)                    # mono
        wav_file.setsampwidth(2)                    # 16-bit PCM
        wav_file.setframerate(voice.config.sample_rate)  # usually 22050 — don't hardcode
        voice.synthesize_wav(text, wav_file)
    data, fs = sf.read(temp_file, dtype='float32')
    sd.play(data, fs)
    sd.wait()  # Block until playback finishes
    import os; os.remove(temp_file)  # clean up 

