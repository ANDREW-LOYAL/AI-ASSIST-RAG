"""ChatGPT-style desktop chat window for text and voice input, Developed by Codex"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from src.config import OllamaConfig
from src.ui.chat_store import ChatStore
from src.ui.workers import AudioWorker, ChatWorker


class ChatInput(QPlainTextEdit):
    """Multiline composer that sends on Ctrl+Enter."""

    send_requested = Signal()

    def key_press_event(self, event):
        """Send the message on Ctrl+Enter, otherwise pass to default handler."""
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.send_requested.emit()
            return
        super().keyPressEvent(event)


class MessageBubble(QFrame):
    """A readable, selectable message block aligned by speaker."""

    def __init__(self, role, content, status="complete"):
        super().__init__()
        self.setObjectName("messageBubble")
        self.setProperty("role", role)
        self.setProperty("status", status)
        self.setMaximumWidth(760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        speaker = QLabel("Tú" if role == "user" else "Asistente")
        speaker.setObjectName("messageSpeaker")
        layout.addWidget(speaker)

        body = QLabel(content)
        body.setObjectName("messageBody")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(body)

        status_text = {
            "pending": "Enviando…",
            "failed": "No se completó esta consulta.",
            "interrupted": "La aplicación se cerró antes de completar esta consulta.",
        }.get(status)
        if status_text:
            state = QLabel(status_text)
            state.setObjectName("messageStatus")
            layout.addWidget(state)


class MainWindow(QMainWindow):
    """Main chat window with sidebar, message area, and composer."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IA_ASSIST-RAG")
        self.resize(1180, 820)
        self.setMinimumSize(760, 560)

        self.store = ChatStore()
        self.current_conversation_id = None
        self.chat_worker = None
        self.chat_busy = False
        self.audio_busy = False
        self.audio_recording = False
        self.close_waiting_for_workers = False

        self._build_ui()
        self._apply_style()

        conversations = self.store.list_conversations()
        if not conversations:
            self.store.create_conversation()
        self._refresh_conversations()

        self.audio_worker = AudioWorker()
        self.audio_worker.status_changed.connect(self._set_status)
        self.audio_worker.transcription_ready.connect(self._on_transcription)
        self.audio_worker.failed.connect(self._on_audio_error)
        self.audio_worker.start()

    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(270)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 14)
        sidebar_layout.setSpacing(12)

        brand = QLabel("IA_ASSIST-RAG")
        brand.setObjectName("brand")
        sidebar_layout.addWidget(brand)

        self.new_chat_button = QPushButton("＋  Nuevo chat")
        self.new_chat_button.setObjectName("newChatButton")
        self.new_chat_button.clicked.connect(self._new_conversation)
        sidebar_layout.addWidget(self.new_chat_button)

        history_label = QLabel("Chats")
        history_label.setObjectName("sidebarSectionTitle")
        sidebar_layout.addWidget(history_label)

        self.conversation_list = QListWidget()
        self.conversation_list.setObjectName("conversationList")
        self.conversation_list.currentItemChanged.connect(self._on_conversation_selected)
        sidebar_layout.addWidget(self.conversation_list, 1)

        self.sidebar_hint = QLabel("""Las conversaciones se guardan en el equipo.
                                   Desarrollado por ANDREW-LOYAL.""")
        self.sidebar_hint.setObjectName("sidebarHint")
        self.sidebar_hint.setWordWrap(True)
        sidebar_layout.addWidget(self.sidebar_hint)
        root_layout.addWidget(self.sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("chatHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(26, 14, 26, 12)
        header_layout.setSpacing(3)
        self.chat_title = QLabel("Nuevo chat")
        self.chat_title.setObjectName("chatTitle")
        self.chat_subtitle = QLabel("El asistente decide cuándo consultar el RAG.")
        self.chat_subtitle.setObjectName("chatSubtitle")
        header_layout.addWidget(self.chat_title)
        header_layout.addWidget(self.chat_subtitle)
        main_layout.addWidget(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("messagesScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(28, 22, 28, 22)
        self.messages_layout.setSpacing(16)
        self.scroll_area.setWidget(self.messages_widget)
        main_layout.addWidget(self.scroll_area, 1)

        composer_frame = QFrame()
        composer_frame.setObjectName("composerFrame")
        composer_layout = QVBoxLayout(composer_frame)
        composer_layout.setContentsMargins(22, 12, 22, 14)
        composer_layout.setSpacing(8)

        self.composer = ChatInput()
        self.composer.setObjectName("chatComposer")
        self.composer.setPlaceholderText("Escribe un mensaje… (Ctrl+Enter para enviar)")
        self.composer.setFixedHeight(88)
        self.composer.send_requested.connect(self._send_message)
        composer_layout.addWidget(self.composer)

        actions = QHBoxLayout()
        self.status_label = QLabel("Listo")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        actions.addWidget(self.status_label, 1)

        self.audio_button = QPushButton("🎙  Hablar")
        self.audio_button.setObjectName("audioButton")
        self.audio_button.setToolTip("Dicta un mensaje. Se detiene al detectar silencio por 2s, o al pulsar Detener.")
        self.audio_button.clicked.connect(self._toggle_audio)
        actions.addWidget(self.audio_button)

        self.send_button = QPushButton("Enviar  ➤")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._send_message)
        actions.addWidget(self.send_button)
        composer_layout.addLayout(actions)
        main_layout.addWidget(composer_frame)

        root_layout.addWidget(main, 1)
        self.setCentralWidget(root)

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #ffffff; color: #202123; }
            #sidebar { background: #f7f7f8; border-right: 1px solid #e5e5e5; }
            #brand { font-size: 20px; font-weight: 700; padding: 3px 4px 8px; }
            #newChatButton, #audioButton, #sendButton {
                border: 1px solid #d9d9e3; border-radius: 9px; padding: 10px 13px;
                background: #ffffff; text-align: left;
            }
            #newChatButton:hover, #audioButton:hover { background: #eeeeef; }
            #sendButton { background: #202123; color: #ffffff; border-color: #202123; }
            #sendButton:hover { background: #343541; }
            #sendButton:disabled, #audioButton:disabled { color: #9a9a9a; background: #eeeeef; }
            #sidebarSectionTitle { color: #777777; font-size: 12px; font-weight: 600; padding: 8px 4px 0; }
            #conversationList { border: 0; background: transparent; outline: none; }
            #conversationList::item { padding: 10px 9px; border-radius: 8px; }
            #conversationList::item:selected { background: #e8e8eb; color: #202123; }
            #conversationList::item:hover { background: #eeeeef; }
            #sidebarHint, #chatSubtitle, #statusLabel { color: #777777; font-size: 12px; }
            #chatHeader { border-bottom: 1px solid #eeeeee; background: #ffffff; }
            #chatTitle { font-weight: 650; font-size: 16px; }
            #messagesScrollArea { background: #ffffff; }
            #composerFrame { border-top: 1px solid #eeeeee; background: #ffffff; }
            #chatComposer { border: 1px solid #d9d9e3; border-radius: 12px; padding: 12px; }
            #chatComposer:focus { border: 1px solid #8e8ea0; }
            #messageBubble[role="user"] { background: #f4f4f4; border-radius: 14px; }
            #messageBubble[role="assistant"] { background: #ffffff; border-radius: 14px; }
            #messageBubble[status="failed"] { border: 1px solid #e6aaaa; }
            #messageSpeaker { font-weight: 650; color: #505050; }
            #messageBody { font-size: 14px; line-height: 1.45; }
            #messageStatus { color: #8a6d3b; font-size: 11px; }
            """
        )

    def _refresh_conversations(self, selected_id=None):
        if selected_id is None:
            selected_id = self.current_conversation_id
        conversations = self.store.list_conversations()
        self.conversation_list.blockSignals(True)
        self.conversation_list.clear()
        selected_item = None
        for conversation in conversations:
            item = QListWidgetItem(conversation["title"])
            item.setData(Qt.ItemDataRole.UserRole, conversation["id"])
            self.conversation_list.addItem(item)
            if conversation["id"] == selected_id:
                selected_item = item
        if selected_item is None and self.conversation_list.count():
            selected_item = self.conversation_list.item(0)
        if selected_item:
            self.conversation_list.setCurrentItem(selected_item)
            self.current_conversation_id = selected_item.data(Qt.ItemDataRole.UserRole)
        self.conversation_list.blockSignals(False)
        self._render_current_conversation()

    def _on_conversation_selected(self, current, _previous):
        if current is None:
            return
        self.current_conversation_id = current.data(Qt.ItemDataRole.UserRole)
        self._render_current_conversation()

    def _new_conversation(self):
        conversation_id = self.store.create_conversation()
        self.current_conversation_id = conversation_id
        self._refresh_conversations(conversation_id)
        self.composer.setFocus()
        self._set_status("Nueva conversación")

    def _clear_messages(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_current_conversation(self):
        self._clear_messages()
        if not self.current_conversation_id:
            return

        conversations = self.store.list_conversations()
        conversation = next(
            (entry for entry in conversations if entry["id"] == self.current_conversation_id),
            None,
        )
        self.chat_title.setText(conversation["title"] if conversation else "Nuevo chat")
        messages = self.store.get_messages(self.current_conversation_id)

        if not messages:
            welcome = QLabel("¿En qué puedo ayudarte?\nPuedes escribir o dictar una consulta.")
            welcome.setObjectName("welcomeMessage")
            welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome.setStyleSheet("color: #777777; font-size: 19px; padding: 35px;")
            self.messages_layout.addWidget(welcome)

        for message in messages:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            bubble = MessageBubble(
                message["role"],
                message["content"],
                message["status"],
            )
            if message["role"] == "user":
                row_layout.addStretch(1)
                row_layout.addWidget(bubble)
            else:
                row_layout.addWidget(bubble)
                row_layout.addStretch(1)
            self.messages_layout.addWidget(row)

        self.messages_layout.addStretch(1)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _send_message(self):
        if self.chat_busy or self.audio_busy:
            return
        message = self.composer.toPlainText().strip()
        if not message:
            return
        if not self.current_conversation_id:
            self._new_conversation()

        conversation_id = self.current_conversation_id
        user_message_uid = self.store.add_user_message(conversation_id, message)
        model_history = self.store.get_model_history(conversation_id)
        self.composer.clear()
        self._refresh_conversations(conversation_id)
        self._set_status("Pensando…")

        worker = ChatWorker(
            self.store.database_path,
            conversation_id,
            user_message_uid,
            OllamaConfig.MAIN_PROMPT,
            model_history,
            message,
        )
        worker.setParent(self)
        worker.completed.connect(self._on_chat_completed)
        worker.failed.connect(self._on_chat_failed)
        worker.finished.connect(self._on_chat_worker_finished)
        self.chat_worker = worker
        self.chat_busy = True
        self._update_controls()
        worker.start()

    def _on_chat_completed(self, conversation_id, _answer):
        self._refresh_conversations(self.current_conversation_id)
        if conversation_id == self.current_conversation_id:
            self._set_status("Listo")

    def _on_chat_failed(self, conversation_id, error_message):
        self._refresh_conversations(self.current_conversation_id)
        if conversation_id == self.current_conversation_id:
            self._set_status(error_message)

    def _on_chat_worker_finished(self):
        worker = self.sender()
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.chat_worker = None
        self.chat_busy = False
        self._update_controls()
        self._maybe_close_after_workers()

    def _toggle_audio(self):
        if self.chat_busy:
            return
        if self.audio_recording:
            self.audio_recording = False
            self.audio_button.setEnabled(False)
            self.audio_button.setText("🎙  Hablar")
            self._set_status("Procesando audio…")
            self.audio_worker.request_stop()
            return

        if self.audio_busy:
            return
        self.audio_busy = True
        self.audio_recording = True
        self.audio_button.setText("⏹  Detener")
        self._update_controls()
        self._set_status("Preparando grabación…")
        self.audio_worker.start_recording()

    def _on_transcription(self, text):
        self.audio_busy = False
        self.audio_recording = False
        self.audio_button.setText("🎙  Hablar")
        self.audio_button.setEnabled(True)
        if text:
            existing = self.composer.toPlainText().strip()
            self.composer.setPlainText(f"{existing} {text}".strip())
            self.composer.setFocus()
            self._set_status("Transcripción lista. Revísala y envíala.")
        else:
            self._set_status("No se reconoció voz; puedes volver a intentarlo.")
        self._update_controls()

    def _on_audio_error(self, error_message):
        self.audio_busy = False
        self.audio_recording = False
        self.audio_button.setText("🎙  Hablar")
        self.audio_button.setEnabled(True)
        self._set_status(f"Error de audio: {error_message}")
        self._update_controls()

    def _update_controls(self):
        can_compose = not self.chat_busy and not self.audio_busy
        self.composer.setEnabled(can_compose)
        self.send_button.setEnabled(can_compose)
        self.audio_button.setEnabled(not self.chat_busy and (not self.audio_busy or self.audio_recording))

    def _set_status(self, text):
        self.status_label.setText(text)

    def _maybe_close_after_workers(self):
        audio_running = hasattr(self, "audio_worker") and self.audio_worker.isRunning()
        chat_running = self.chat_worker is not None and self.chat_worker.isRunning()
        if self.close_waiting_for_workers and not audio_running and not chat_running:
            if hasattr(self, "audio_worker"):
                self.audio_worker.wait()
            QTimer.singleShot(0, self.close)

    def close_event(self, event):
        """Handle window close event, waiting for workers to finish if needed."""
        audio_running = hasattr(self, "audio_worker") and self.audio_worker.isRunning()
        chat_running = self.chat_worker is not None and self.chat_worker.isRunning()
        if audio_running or chat_running:
            event.ignore()
            if not self.close_waiting_for_workers:
                self.close_waiting_for_workers = True
                self._set_status("Cerrando… espera a que terminen las tareas activas.")
                if audio_running:
                    self.audio_worker.finished.connect(self._maybe_close_after_workers)
                    self.audio_worker.shutdown()
                if chat_running:
                    self.chat_worker.finished.connect(self._maybe_close_after_workers)
                QTimer.singleShot(0, self._maybe_close_after_workers)
            return
        event.accept()
