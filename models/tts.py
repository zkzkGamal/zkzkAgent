import warnings
warnings.filterwarnings("ignore", module="librosa")

from TTS.api import TTS
import sounddevice as sd

model_name = "tts_models/en/vctk/vits"
tts = TTS(model_name ,progress_bar=False, gpu=True)

def speak(text):
    speaker = tts.speakers[11]
    wav = tts.tts(
        text=text,
        speaker=speaker
    )
    sd.play(wav, samplerate=tts.synthesizer.output_sample_rate)
    sd.wait()