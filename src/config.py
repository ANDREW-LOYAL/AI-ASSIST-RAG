"""main configuration file for the application"""
import os
from pathlib import Path

class PathConfig:
    """path configuration for the application"""
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    SRC_DIR = PROJECT_ROOT / "src"
    DATA_DIR = PROJECT_ROOT / "data"
<<<<<<< HEAD
    DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
    INDEX_LOG_PATH = PROJECT_ROOT / "indexing.log"
    CHAT_HISTORY_PATH = PROJECT_ROOT / "chat_history.sqlite3"
=======
    PDF_DIR = DATA_DIR
    DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
    INDEX_MANIFEST_PATH = PROJECT_ROOT / "index_manifest.sqlite3"
    INDEX_LOG_PATH = PROJECT_ROOT / "indexing.log"
    CHAT_HISTORY_PATH = PROJECT_ROOT / "chat_history.sqlite3"
    MODULES_DIR = SRC_DIR / "modules"
    QDRANT_DB = PROJECT_ROOT / "qdrant_db"
>>>>>>> 62b0e5e12e28d4fa64463c9d6bf708e53378ac46

class OllamaConfig:
    """Clase de configuración para Ollama"""
    MAX_TOKENS = 500 # Número máximo de tokens para la respuesta generada por Ollama
    TEMPERATURE = 0.5 # Temperatura para la generación de respuestas
    EMBEDDING_MODEL = "nomic-embed-text" # Modelo de Ollama para generar embeddings
    MODEL = "gemma4:latest" #Modelo de Ollama a utilizar
    MAIN_PROMPT = """Eres un asistente útil y conversacional. Responde directamente usando tus
<<<<<<< HEAD
    conocimientos generales cuando sea suficiente. Usa la herramienta "rag" si el usuario pide
    buscar en la base de conocimiento en este caso Qdrant, pregunta por información que dependa de sus documentos,
    o necesitas verificar un dato que podría estar allí. No llames a RAG para todas las preguntas.
    Cuando recibas resultados de RAG, intégralos con tus conocimientos y responde con tus propias
    palabras. Si la búsqueda no aporta información suficiente, dilo claramente."""
=======
conocimientos generales cuando sea suficiente. Usa la herramienta "rag" si el usuario pide
buscar en la base de conocimiento, pregunta por información que dependa de sus documentos,
o necesitas verificar un dato que podría estar allí. No llames a RAG para todas las preguntas.
Cuando recibas resultados de RAG, intégralos con tus conocimientos y responde con tus propias
palabras. Si la búsqueda no aporta información suficiente, dilo claramente."""
>>>>>>> 62b0e5e12e28d4fa64463c9d6bf708e53378ac46
    MAX_TOOL_ROUNDS = 4

#-----

class AudioConfig:
    """Clase de configuración para la grabación de audio"""
    SAMPLE_RATE = 16000  # Frecuencia de muestreo para la grabación de audio en Hz
    CHANNELS = 1  # Número de canales de audio (1 para mono, 2 para estéreo)
    DATA_TYPE = 'float32'  # Tipo de datos para los muestras de audio
    AUDIO_DEVICE = 'Microphone (MT-MC13), MME'  # Dispositivo de entrada de audio predeterminado

#-----

class VADConfig:
    """Clase de configuración para la detección de actividad vocal (VAD)"""
    MAX_SILENCE_DURATION = 2 # Duración máxima de silencio (en segundos) antes de dejar de grabar
    INITIAL_SILENCE_TIMEOUT = 10 # Tiempo máximo esperando voz al iniciar una grabación
    MAX_RECORDING_DURATION = 120 # Duración máxima de una grabación en segundos
    MIN_SPEECH_DURATION_MS = 250 # Duración mínima de la voz (en milisegundos)
    MIN_SEGMENT_DURATION_MS = 500 # Duración mínima de cada segmento(en milisegundos)
    HUMAN_PROBABILITY_THRESHOLD = 0.5 #Probabilidad para considerar que hay voz humana (0.0 a 1.0)
    FRECUENCY = 16000 # Frecuencia de muestreo para la detección de voz humana (en Hz)
    BLOCK_SIZE = 8192 # Tamaño del bloque de audio para el procesamiento

#-----

class WhisperConfig:
    """Clase de configuración para el modelo Whisper"""
    LANGUAGE = None # Idioma para la transcripción.
    DATA_TYPE_RATE = 'float32' # Tipo de datos para el modelo Whisper.
    WHISPER_MODEL = 'base' # Tamaño del modelo Whisper
    CPU_THREADS = max(1, os.cpu_count() -2) #Número de hilos de CPU.
    WHISPER_DEVICE = 'cuda' if os.getenv('CUDA_VISIBLE_DEVICES') else 'cpu' #Check CUDA.


class QdrantConfig:
    """Clase de configuración para Qdrant"""
    COLLECTION_NAME = "ia_context" #Nombre de la colección en Qdrant
    QDRANT_URL = "http://localhost:6333" #URL del servidor Qdrant
    LIMIT = 10 #Número máximo de resultados a recuperar en las búsquedas en Qdrant
<<<<<<< HEAD
    QDRANT_TIMEOUT = 30 #Tiempo de espera para las solicitudes a Qdrant (en segundos)
    CHUNK_SIZE = 600 #Tamaño de los fragmentos de texto para la indexación en Qdrant
    CHUNK_OVERLAP = 100 #Superposición de los fragmentos de texto para la indexación en Qdrant
    EMBEDDING_BATCH_SIZE = 16 #Cantidad de fragmentos que se envían juntos al modelo de embeddings para convertirlos en vectores.
    SCROLL_PAGE_SIZE = 256 #Cantidad de registros que se leen de Qdrant por cada página al recorrer la colección para verificar el índice
=======
>>>>>>> 62b0e5e12e28d4fa64463c9d6bf708e53378ac46

#-----
