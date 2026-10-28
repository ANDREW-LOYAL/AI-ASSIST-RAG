# IA-Assist-RAG

IA Assist RAG es un asistente de escritorio que permite conversar con un modelo de lenguaje local. Puedes hacer preguntas usando sus conocimientos generales y, cuando necesites información de tus propios documentos, pedirle que busque en una base de conocimiento creada a partir de archivos PDF.

La aplicación ofrece una interfaz de chat con conversaciones guardadas en el equipo. También permite dictar mensajes por micrófono: el audio se transcribe y aparece en el cuadro de texto para que puedas revisarlo antes de enviarlo.

## Qué hace

- Conversa con un modelo local mediante Ollama.
- Busca información en una colección vectorial de Qdrant cuando el modelo decide que la consulta necesita documentos o cuando se lo pides.
- Procesa PDF desde una carpeta de entrada y archiva los que se indexaron correctamente.
- Conserva conversaciones e historial del modelo en una base SQLite local.
- Transcribe dictados con Whisper. La aplicación no genera respuestas habladas.

## Requisitos

- Python 3.10 o posterior.
- [Ollama](https://ollama.com/) instalado y en ejecución.
- Un modelo de chat y un modelo de embeddings disponibles en Ollama. La configuración inicial del proyecto usa `gemma4:latest` y `nomic-embed-text`.
- Qdrant disponible en `http://localhost:6333` para indexar o consultar documentos.
- Micrófono funcional para usar el dictado por voz.

## Instalación y ejecución

Desde la carpeta raíz del proyecto, crea y activa un entorno virtual e instala las dependencias:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Descarga en Ollama los modelos configurados en `src/config.py`, Puedes modificarlos a tu gusto, pero para el RAG se recomienda mantener `nomic-embed-text`:

```powershell
ollama pull gemma4:latest
ollama pull nomic-embed-text
```

### Ejecutar Ollama y Qdrant con Docker Compose

También puedes iniciar ambos servicios con [`compose.yaml`](compose.yaml):

```powershell
docker compose up -d
docker compose exec ollama ollama pull gemma4:latest
docker compose exec ollama ollama pull nomic-embed-text
```

La aplicación de escritorio continúa ejecutándose en Windows y se conecta a Ollama por `http://localhost:11434` y a Qdrant por `http://localhost:6333`. Los modelos de Ollama y los datos de Qdrant persisten en volúmenes Docker. Para detener los servicios, ejecuta `docker compose down`; los volúmenes se conservan.

En Docker Desktop para Windows, la documentación de GPU passthrough para contenedores Linux cubre NVIDIA. Esta configuración no asigna una Intel ARC al contenedor, por lo que Ollama en Docker podría usar CPU. Hay que validar una ruta compatible con Intel Arc antes de contar con aceleración GPU. Para el desarollo se uso Intel ARC arquitecura Xe2 aka Battlemage, solo
disponible su uso mediante la aplicacion de ollama desktop y SYCL.

Inicia Ollama y Qdrant. La aplicación espera encontrar Qdrant en `http://localhost:6333`; puedes cambiar esa dirección en `src/config.py`. Después, inicia la interfaz:

```powershell
python main.py
```

La primera vez que uses el micrófono se cargará el modelo Whisper `base`, lo que puede tardar y requerir una descarga del modelo.

## Añadir e indexar documentos PDF

1. Copia los PDF que quieras incorporar en `data/`.
2. Con Ollama y Qdrant en ejecución, lanza el indexador desde la raíz del proyecto:

   ```powershell
   python main_indexer.py
   ```

3. Los PDF procesados correctamente se mueven a `data_processed/`. Los que fallen permanecen en `data/` para que puedas corregir el problema e intentarlo de nuevo.

El indexador extrae texto, divide los documentos en fragmentos de 600 caracteres con 100 caracteres de solapamiento, genera embeddings con el modelo configurado y guarda los vectores en la colección `ia_context`. Verifica en Qdrant la huella, versión del proceso y la lista completa de fragmentos antes de marcar un documento como activo. `indexing.log` guarda eventos JSON con fecha, archivo y resultado; es un registro de auditoría y no determina el estado de la indexación. No se usa una base de datos de manifiesto para los PDF.

Los archivos PDF, las bases de datos locales y el registro de indexación están excluidos de Git.

## Cómo funciona técnicamente

### Chat y uso del RAG

La interfaz PySide6 envía los mensajes a Ollama desde un hilo de trabajo para mantener la ventana receptiva. Ollama recibe el prompt del sistema, el historial de la conversación y la definición de la herramienta `rag`.

El modelo puede responder directamente con sus conocimientos generales. Si decide que necesita información de los documentos —o el usuario solicita una búsqueda—, llama a `rag` con una consulta. La herramienta genera un embedding con `nomic-embed-text`, busca hasta diez fragmentos en Qdrant y devuelve el contexto al modelo. Ollama usa ese resultado para redactar la respuesta final. Se permiten hasta cuatro rondas de llamadas a herramientas por turno.

### Indexación

`src/indexing/pdf_indexer.py` coordina el flujo y delega extracción, auditoría, archivo y acceso a Qdrant en módulos con responsabilidades separadas. Calcula un SHA-256, extrae las páginas con PyPDF, divide el texto con `RecursiveCharacterTextSplitter` y genera embeddings por lotes. Los nuevos fragmentos primero se suben con estado provisional; tras comprobar en Qdrant que existen todos los índices de fragmento esperados, se activan y se retira la versión anterior. Una carga incompleta queda fuera de las búsquedas y puede reintentarse. Los PDF fallidos permanecen en la bandeja de entrada.

### Historial y concurrencia

`src/gui/chat_history_store.py` persiste conversaciones, mensajes y el historial completo usado por Ollama —incluidas las interacciones con herramientas— en `chat_history.sqlite3`. Cada hilo de trabajo usa conexiones SQLite independientes. `src/gui/workers.py` ejecuta las consultas del modelo y la captura/transcripción de audio fuera del hilo de interfaz.

### Audio

`src/audio/audio_recorder.py` captura audio con `sounddevice`, detecta voz y silencio, y transcribe con `faster-whisper`. La grabación finaliza al detectar silencio, al alcanzar el límite de tiempo o cuando se detiene desde la interfaz. El texto transcrito se devuelve al compositor; el usuario decide cuándo enviarlo.

## Estructura del proyecto

```text
.
├── data/                    # PDF pendientes de indexación
├── data_processed/          # PDF indexados correctamente
├── src/
│   ├── audio/               # Captura, transcripción y salida de voz
│   ├── gui/                 # Ventana, historial y trabajadores Qt
│   ├── health/              # Comprobaciones de servicios externos
│   ├── indexing/            # Lectura, archivo e indexación de PDF
│   ├── ollama/              # Chat, tool calling y embeddings
│   ├── qdrant/              # Cliente, búsqueda y gestión de colección
│   └── rag/                 # Coordinación de recuperación RAG
├── main.py                  # Inicio de la aplicación
|── main_indexer.py          # Cuando tenga pdfs en data, ejecute este main para indexarlos
└── requirements.txt
```

## Configuración

Los valores principales están en `src/config.py`:

- `OllamaConfig.MODEL`: modelo conversacional.
- `OllamaConfig.EMBEDDING_MODEL`: modelo para embeddings.
- `QdrantConfig.QDRANT_URL`: dirección de Qdrant.
- `QdrantConfig.COLLECTION_NAME`: colección vectorial.
- `WhisperConfig.WHISPER_MODEL`: tamaño del modelo de transcripción.
- `VADConfig`: tiempos de silencio y duración de grabación.

## Autoría y contribuciones

### Trabajo previo del autor del proyecto

La base de IA Assist y sus módulos originales fueron desarrollados por el autor del proyecto PEGASUS-WOLF aka ANDREW-LOYAL. Esto incluye la integración inicial con Ollama y Qdrant, el procesamiento de audio/voz y la estructura inicial de la aplicación. La atribución detallada de cada archivo o componente debe verificarse con el historial de Git del repositorio.

### Cambios realizados con asistencia de Codex - LUNA 6 - Medium

Durante esta colaboración se trabajó en:

- El flujo de tool calling para que Ollama decida cuándo consultar la herramienta RAG y pueda responder también sin consultar documentos.
- La persistencia del historial del modelo por conversación.
- El flujo de indexación de PDF desde `data/`, verificación de integridad directamente en Qdrant, registro de actividad y archivo en `data_processed/`.
- La interfaz de escritorio tipo chat, las conversaciones persistentes y el dictado de voz revisable antes del envío.
- La organización y configuración asociadas a esos cambios.

Codex actuó como asistente de programación; el proyecto y las decisiones de producto pertenecen a su autor ANDREW-LOYAL.
