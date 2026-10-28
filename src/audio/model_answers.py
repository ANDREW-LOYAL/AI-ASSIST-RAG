"""Tools calling checker module."""
import json

def tool_calling_checker(answer):
    """Comprueba si Ollama ha solicitado ejecutar una herramienta."""

    message = getattr(answer, "message", None)

    if message is None:
        print(answer)
        return None

    tool_calls = getattr(message, "tool_calls", None) or []

    for tool in tool_calls:
        function = tool.function

        if function.name == "rag":
            arguments = function.arguments

            if isinstance(arguments, str):
                arguments = json.loads(arguments)

            return arguments.get("query")

    print(message.content)
    return None
