import os
from pathlib import Path
import pyttsx3
import threading
import time
import atexit
import signal
import sys
import speech_recognition as sr

# TTS
engine = pyttsx3.init()
_engine_lock = threading.Lock()


def _shutdown_tts():
    # Ensure pyttsx3 background loop is stopped on process exit
    try:
        with _engine_lock:
            engine.stop()
    except Exception:
        pass

# Track last PyAudio instance to ensure clean termination
_last_pyaudio = None

def _force_exit():
    """Force exit when hanging"""
    try:
        _shutdown_tts()
        _shutdown_audio()
    except Exception:
        pass
    os._exit(0)

def _signal_handler(signum, frame):
    """Handle Ctrl+C more aggressively"""
    _force_exit()

def _shutdown_audio():
    global _last_pyaudio
    try:
        if _last_pyaudio is not None:
            _last_pyaudio.terminate()
    except Exception:
        pass
    finally:
        _last_pyaudio = None

# Register cleanup handlers
atexit.register(_shutdown_tts)
atexit.register(_shutdown_audio)
# Only install signal handlers in main thread to avoid Streamlit runner errors
try:
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
except Exception:
    # Ignore if not allowed in this environment
    pass

def speak(text):
    # Prevent re-entrant run loop errors under Streamlit's multi-run model
    with _engine_lock:
        try:
            engine.say(text)
            engine.runAndWait()
        except RuntimeError as e:
            msg = str(e).lower()
            if "run loop already started" in msg:
                # Wait for current speech to finish, then try once more
                while engine.isBusy():
                    time.sleep(0.05)
                engine.say(text)
                engine.runAndWait()
            else:
                raise

# ASR
try:
    from vosk import Model, KaldiRecognizer
    import pyaudio
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False

MODEL_DIR = Path(__file__).parent / "models" / "vosk-model-small-en-us-0.15"

def recognize_from_vosk(seconds=5, sample_rate=16000, should_stop=None, device_index=None):
    if not VOSK_AVAILABLE:
        return None
    if not MODEL_DIR.exists():
        return None

    global _last_pyaudio
    model = Model(str(MODEL_DIR))
    p = pyaudio.PyAudio()
    _last_pyaudio = p
    stream = None
    try:
        try:
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=sample_rate,
                            input=True, frames_per_buffer=8000,
                            input_device_index=device_index)
            actual_rate = sample_rate
        except Exception:
            # Device may not support 16k; fall back to 44100 and resample via recognizer model
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100,
                            input=True, frames_per_buffer=8192,
                            input_device_index=device_index)
            actual_rate = 44100
        stream.start_stream()
        rec = KaldiRecognizer(model, actual_rate)

        transcript = ""
        import time as _t, json
        t_end = _t.time() + seconds
        while _t.time() < t_end:
            if callable(should_stop) and should_stop():
                break
            data = stream.read(4000, exception_on_overflow=False)
            if rec.AcceptWaveform(data):
                res = rec.Result()
                j = json.loads(res)
                transcript += " " + j.get("text", "")

        final = rec.FinalResult()
        j = json.loads(final)
        transcript += " " + j.get("text", "")

        transcript = transcript.strip()
        return transcript.lower() if transcript else None
    finally:
        try:
            if stream is not None:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
        except Exception:
            pass
        try:
            p.terminate()
        except Exception:
            pass
        _last_pyaudio = None


def recognize_with_google(timeout=6, device_index=None, should_stop=None, energy_threshold=None, dynamic_energy=True):
    r = sr.Recognizer()
    r.dynamic_energy_threshold = dynamic_energy
    if energy_threshold is not None:
        r.energy_threshold = energy_threshold
    mic_kwargs = {}
    if device_index is not None:
        mic_kwargs["device_index"] = device_index
    with sr.Microphone(**mic_kwargs) as source:
        try:
            r.adjust_for_ambient_noise(source, duration=0.5)
        except Exception:
            pass
        import time as _t
        deadline = _t.time() + timeout
        # Poll in short chunks so we can honor stop requests
        while _t.time() < deadline and not (callable(should_stop) and should_stop()):
            remaining = max(0.5, min(1.0, deadline - _t.time()))
            try:
                audio = r.listen(source, timeout=1, phrase_time_limit=remaining)
            except Exception:
                continue
            try:
                text = r.recognize_google(audio).lower()
                if text:
                    return text
            except Exception:
                # No recognition, continue polling until timeout or stop
                continue
    return None


def listen(prefer_vosk=True, timeout=6, device_index=None, should_stop=None, energy_threshold=None, dynamic_energy=True):
    # Try Vosk first if available
    if prefer_vosk and VOSK_AVAILABLE and MODEL_DIR.exists():
        t = recognize_from_vosk(seconds=timeout, should_stop=should_stop, device_index=device_index)
        if t and t.strip():
            return t
    
    # Fallback to Google if Vosk failed or not preferred
    result = recognize_with_google(
        timeout=timeout,
        device_index=device_index,
        should_stop=should_stop,
        energy_threshold=energy_threshold,
        dynamic_energy=dynamic_energy,
    )
    return result


def test_microphone(seconds=3, device_index=None, energy_threshold=None, dynamic_energy=True):
    return recognize_with_google(
        timeout=seconds,
        device_index=device_index,
        should_stop=None,
        energy_threshold=energy_threshold,
        dynamic_energy=dynamic_energy,
    )


def list_microphones():
    try:
        return sr.Microphone.list_microphone_names() or []
    except Exception:
        return []
