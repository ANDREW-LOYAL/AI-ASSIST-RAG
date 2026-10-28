"""Tool schemas and dispatch functions exposed to Ollama."""
from src.rag.rag_service import rag_search

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "rag",
            "description": "Busca información en la base de conocimientos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta que se realizará en la base de conocimientos.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# Kept as a short alias for integrations that used the previous name.
tools = TOOL_DEFINITIONS


def execute_tool(name, arguments):
    """Execute a tool requested by the model and return text for its next turn."""
    if name != "rag":
        raise ValueError(f"Herramienta desconocida: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("Los argumentos de rag deben ser un objeto.")

    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("La herramienta rag requiere una consulta no vacía.")

    return str(rag_search(query.strip()))
