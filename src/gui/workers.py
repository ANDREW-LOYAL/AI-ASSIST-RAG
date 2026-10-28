"""Background workers for model requests and voice capture/transcription."""
import queue
import threading
from PySide6.QtCore import QThread, Signal
from src.config import OllamaConfig
from src.audio.audio_recorder import VoiceRecognition
from src.ollama.chat_client import OllamaSender
from src.gui.chat_history_store import ChatStore


class ChatWorker(QThread):
    """Run one complete model/tool round-trip outside the GUI thread."""

    completed = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, store_path, conversation_id, user_message_uid, prompt, history, message):
        super().__init__()
        self.store = ChatStore(store_path, initialize=False)
        self.conversation_id = conversation_id
        self.user_message_uid = user_message_uid
        self.prompt = prompt
        self.history = history
        self.message = message

    def run(self):
        """Send the message to the model and store the assistant's response."""
        sender = OllamaSender(self.prompt)
        sender.history = self.history
        try:
            answer = sender.send_message(self.message)
            self.store.complete_turn(
                self.conversation_id,
                self.user_message_uid,
                answer,
                sender.history,
            )
            self.completed.emit(self.conversation_id, answer)
        except Exception as error:
            message = f"No se pudo completar la consulta: {error}"
            try:
                self.store.fail_turn(
                    self.conversation_id,
                    self.user_message_uid,
                    message,
                )
            except Exception:
                pass
            self.failed.emit(self.conversation_id, message)


class AudioWorker(QThread):
    """Keep one Whisper model alive and handle recording commands in a thread."""

    status_changed = Signal(str)
    transcription_ready = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._commands = queue.Queue()
        self._stop_event = threading.Event()

    def start_recording(self):
        """Start recording audio in a separate thread."""
        self._stop_event.clear()
        self._commands.put("record")

    def request_stop(self):
        """Request to stop recording audio."""
        self._stop_event.set()

    def shutdown(self):
        """Stop the worker thread and clean up."""
        self._stop_event.set()
        self._commands.put(None)

    def run(self):
        """Run the audio recording loop, handling commands and emitting signals."""
        recognizer = None
        while True:
            command = self._commands.get()
            if command is None:
                return

            try:
                if recognizer is None:
                    self.status_changed.emit("Cargando Whisper por primera vez…")
                    recognizer = VoiceRecognition()

                if self._stop_event.is_set():
                    self.transcription_ready.emit("")
                    continue

                self.status_changed.emit("Grabando… habla y espera el silencio, o pulsa Detener.")
                transcription = recognizer.audio_taker(stop_event=self._stop_event)
                self.transcription_ready.emit(transcription)
            except Exception as error:
                self.failed.emit(str(error))
