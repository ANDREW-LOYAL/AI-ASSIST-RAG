"""Services Main Checker"""
from src.health.checks.qdrant_check import qdrant_state
from src.health.checks.ollama_check import ollama_state


def run_services_check(required_services=("Ollama",)):
    """Check services; only the explicitly required services block startup."""
    services = {
        "Ollama": ollama_state,
        "Qdrant": qdrant_state
    }

    all_working = True
    print("Verificando Estado de Servicios")

    for name, check_function in services.items():
        is_working = check_function()
        status = "Funciona" if is_working else "Fallo"
        print(f"El Servicio {name}: Estado {status} ")

        if not is_working and name in required_services:
            all_working = False
            print(f"Servicio {name} no está iniciado.")
        elif not is_working:
            print(f"Servicio {name} no está iniciado; sus funciones estarán disponibles cuando vuelva.")

    return all_working
