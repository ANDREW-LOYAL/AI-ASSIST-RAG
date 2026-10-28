"""Conversation client for Ollama, including model-directed tool calling."""
import ollama

from src.config import OllamaConfig
from src.ollama.tools import execute_tool, TOOL_DEFINITIONS


class OllamaSender:
    """Send turns to Ollama and preserve the model's tool-aware history."""

    def __init__(self, prompt, client=None):
        self.prompt = prompt
        self.history = []
        self.client = client or ollama.Client()

    def send_message(self, message):
        """Answer one user turn, allowing Ollama to request tools as needed."""
        messages = [
            {"role": "system", "content": self.prompt},
            *self.history,
            {"role": "user", "content": message},
        ]
        tool_rounds = 0

        while True:
            answer = self.client.chat(
                model=OllamaConfig.MODEL,
                messages=messages,
                tools=(
                    TOOL_DEFINITIONS
                    if tool_rounds < OllamaConfig.MAX_TOOL_ROUNDS
                    else None
                ),
                options={"temperature": OllamaConfig.TEMPERATURE},
            )

            assistant_message = answer.message.model_dump(exclude_none=True)
            messages.append(assistant_message)
            tool_calls = answer.message.tool_calls or []

            if not tool_calls:
                self.history = messages[1:]
                return answer.message.content or ""

            if tool_rounds >= OllamaConfig.MAX_TOOL_ROUNDS:
                fallback = (
                    "No pude completar la respuesta: se alcanzó el límite "
                    "de llamadas a herramientas."
                )
                messages[-1] = {"role": "assistant", "content": fallback}
                self.history = messages[1:]
                return fallback

            for tool_call in tool_calls:
                function = tool_call.function
                try:
                    result = execute_tool(function.name, dict(function.arguments))
                except Exception as error:
                    result = f"La herramienta {function.name} falló: {error}"

                messages.append({
                    "role": "tool",
                    "tool_name": function.name,
                    "content": result,
                })

            tool_rounds += 1

    def clear_history(self):
        """Start a new conversation in this sender instance."""
        self.history.clear()
