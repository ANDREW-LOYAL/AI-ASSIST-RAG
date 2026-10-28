"""Ollama checker"""
import requests


def ping_verify(url='http://localhost:11434'):
    """Ping ollama"""
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except requests.RequestException:
        return False

def ollama_state():
    """Check if Ollama is running and available."""
    if ping_verify():
        return True
    else:
        print("Ollama no esta iniciado.")
        return False
