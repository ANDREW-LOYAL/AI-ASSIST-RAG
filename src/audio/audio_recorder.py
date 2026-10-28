"""Module for audio recording and voice recognition"""
import time
import threading
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps
from src.config import VADConfig, AudioConfig, WhisperConfig

def model_load():
    """Whisper model loading function"""
    print("Cargando modelo Whisper...")
    model = WhisperModel(WhisperConfig.WHISPER_MODEL,
                         device=WhisperConfig.WHISPER_DEVICE,
                         compute_type=WhisperConfig.DATA_TYPE_RATE,
                         cpu_threads=WhisperConfig.CPU_THREADS)
    return model

def audio_trascriber(audio_data, model):
    """Transcribe audio data using the Whisper model"""
    text_segments, info = model.transcribe(
        audio_data,
        beam_size=5,
        language=WhisperConfig.LANGUAGE,
        vad_filter=True
    )
    return text_segments

def get_final_text(text_segments):
    """Combine text segments into a single string."""
    text_list = [segment.text for segment in text_segments]
    final_text = " ".join(text_list).strip()
    return final_text

class VoiceRecognition:
    """Class for handling voice recognition and audio recording."""

    def __init__(self):
        self.model = model_load()
        self.vad_options = VadOptions(threshold=
                                      VADConfig.HUMAN_PROBABILITY_THRESHOLD,
                                      min_speech_duration_ms=
                                      VADConfig.MIN_SPEECH_DURATION_MS)
        self.no_voice_time = 0.0
        self.detected_voice = False
        self.block_size = VADConfig.BLOCK_SIZE
        self.frecuency = VADConfig.FRECUENCY
        self.audio_blocks = []
        self._state_lock = threading.Lock()
        self.channel_count = AudioConfig.CHANNELS
        self.data_type = AudioConfig.DATA_TYPE

    def callback(self, indata, frames, time_info, status):
        """Processes incoming audio data, detects human voice, and manages silence duration."""

        audio_chunk = indata.copy().flatten()
        timestamps = get_speech_timestamps(audio_chunk,
                                           self.vad_options,
                                           sampling_rate=self.frecuency)
        human_voice_detected = len(timestamps) > 0

        with self._state_lock:
            self.audio_blocks.append(audio_chunk)
            if human_voice_detected:
                self.detected_voice = True
                self.no_voice_time = 0.0
            elif self.detected_voice:
                self.no_voice_time += frames / self.frecuency

    def audio_taker(
        self,
        max_silence_duration=VADConfig.MAX_SILENCE_DURATION,
        initial_timeout=VADConfig.INITIAL_SILENCE_TIMEOUT,
        max_recording_duration=VADConfig.MAX_RECORDING_DURATION,
        stop_event=None,
    ):
        """Record until silence, timeout, or cancellation, then transcribe."""
        print(f"""Escuchando..El programa se detendrá si detecta silencio por
              {max_silence_duration}s""")

        with self._state_lock:
            self.audio_blocks = []
            self.no_voice_time = 0.0
            self.detected_voice = False

        if stop_event is not None and stop_event.is_set():
            return ""

        recording_started = time.monotonic()

        with sd.InputStream(samplerate=self.frecuency,
                            channels=self.channel_count,
                            dtype=self.data_type,
                            blocksize=self.block_size,
                            callback=self.callback):
            while True:
                elapsed = time.monotonic() - recording_started
                with self._state_lock:
                    detected_voice = self.detected_voice
                    no_voice_time = self.no_voice_time

                if stop_event is not None and stop_event.is_set():
                    break
                if detected_voice and no_voice_time >= max_silence_duration:
                    print(f"""No se detecto voz humana por {max_silence_duration}s.
                          Finalizando la grabación de audio...""")
                    break
                if not detected_voice and elapsed >= initial_timeout:
                    print(f"No se detectó voz dentro de {initial_timeout}s.")
                    break
                if elapsed >= max_recording_duration:
                    print(f"Se alcanzó el máximo de grabación ({max_recording_duration}s).")
                    break

                if stop_event is None:
                    time.sleep(0.1)
                else:
                    stop_event.wait(0.1)

        with self._state_lock:
            audio_blocks = self.audio_blocks
            detected_voice = self.detected_voice
            self.audio_blocks = []

        if not detected_voice or not audio_blocks:
            return ""

        complete_audio = np.concatenate(audio_blocks)
        text_segments = audio_trascriber(complete_audio, self.model)
        final_text = get_final_text(text_segments)

        del complete_audio
        print(final_text)
        return final_text
