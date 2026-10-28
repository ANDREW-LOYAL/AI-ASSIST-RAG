"""Checker for Qdrant availability"""
import requests

def ping_verify(url='http://localhost:6333'):
    """Ping Qdrant"""
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except requests.RequestException:
        return False

def qdrant_state():
    """Check if Qdrant is running and available."""
    if ping_verify():
        return True
    else:
        print("Qdrant no esta iniciado, Verifica Docker.")
        return False
