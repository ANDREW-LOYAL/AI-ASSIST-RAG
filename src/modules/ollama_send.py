"""Send messages to Ollama, run requested tools, and retain conversation history."""
import ollama
from src.config import OllamaConfig
from src.modules.tools import execute_tool, tools


class OllamaSender:
    """Clase para gestionar una conversación con Ollama."""

    def __init__(self, prompt):
        self.prompt = prompt
        self.history = []

    def send_message(self, message):
        """Answer a user turn, allowing Ollama to request tools as needed."""
        messages = [
            {"role": "system", "content": self.prompt},
            *self.history,
            {"role": "user", "content": message},
        ]
        tool_rounds = 0

        while True:
            answer = ollama.chat(
                model=OllamaConfig.MODEL,
                messages=messages,
                tools=tools if tool_rounds < OllamaConfig.MAX_TOOL_ROUNDS else None,
                options={"temperature": OllamaConfig.TEMPERATURE},
            )

            assistant_message = answer.message.model_dump(exclude_none=True)
            messages.append(assistant_message)
            tool_calls = answer.message.tool_calls or []

            if not tool_calls:
                self.history = messages[1:]
                return answer.message.content or ""

            if tool_rounds >= OllamaConfig.MAX_TOOL_ROUNDS:
                # Defensive fallback for a model that emits a tool call after
                # tool definitions have been removed.
                fallback = "No pude completar la respuesta: se alcanzó el límite de llamadas a herramientas."
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
        """Start a fresh conversation in this process."""
        self.history.clear()
