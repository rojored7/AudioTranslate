# 📚 AudioBook Player Local

Un reproductor de audiolibros 100% local que convierte libros (PDF, EPUB, TXT) en audio con modelos TTS descargados desde HuggingFace.

## Características

✅ **Completamente local** - Sin dependencias en la nube  
✅ **Múltiples motores TTS** - Ollama/Orpheus o Kokoro ONNX  
✅ **Gestión de libros** - Soporta PDF, EPUB, y TXT  
✅ **Progreso persistente** - Pausa/continúa en cualquier momento  
✅ **Caché de audio** - Los audios generados se guardan localmente  
✅ **Interfaz simple** - Sin frameworks complejos, puro HTML/JS  

## Requisitos

- Python 3.8+
- Windows 10+, macOS, o Linux

## Instalación rápida (Windows)

### Opción 1: Script automático (recomendado)

```bash
run.bat
```

El script:
1. Crea un entorno virtual Python
2. Instala dependencias
3. Inicializa la base de datos
4. Inicia el servidor

### Opción 2: Manual

```bash
# Crear entorno virtual
python -m venv venv

# Activar (Windows)
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Inicializar base de datos
python -c "from db import init_db; init_db()"

# Iniciar servidor
python main.py
```

## Uso

### 1. Abrir en el navegador

```
http://localhost:8000
```

### 2. Configurar el motor TTS (opcional)

Por defecto usa **Kokoro ONNX** (se descarga automáticamente).

Si quieres usar **Ollama/Orpheus**:

1. Instala Ollama desde https://ollama.com
2. Descarga el modelo:
   ```bash
   ollama pull legraphista/orpheus:q8_0
   ```
3. En la app, ve a "⚙️ Configuración" y selecciona "Ollama/Orpheus"

### 3. Subir un libro

- Arrastra un PDF, EPUB o TXT a la zona de descarga
- O haz clic para seleccionar archivo
- El app extrae el texto y lo divide en segmentos (~500 palabras c/u)

### 4. Reproducir

- Haz clic en "▶️ Continuar" o "▶️ Empezar"
- Se abre el reproductor con el texto visible
- Controles: play/pause, anterior/siguiente
- El progreso se guarda automáticamente

## Arquitectura

```
AudioTranslate/
├── main.py                 # FastAPI app
├── db.py                   # SQLite
├── tts_engine.py           # Abstracción TTS (Ollama/Kokoro)
├── book_parser.py          # Extrae texto de libros
├── routers/                # API endpoints
│   ├── books.py
│   ├── audio.py
│   ├── progress.py
│   └── settings.py
├── static/                 # Frontend
│   ├── index.html          # Biblioteca
│   ├── player.html         # Reproductor
│   ├── app.js              # Lógica JS
│   └── style.css           # Estilos
└── data/
    ├── books/              # Libros subidos
    ├── audio_cache/        # WAV generados
    └── audiobookplayer.db  # SQLite
```

## Motores TTS

### Kokoro ONNX (defecto)

- **Tamaño**: ~300 MB (se descarga una sola vez)
- **Velocidad**: Real-time en CPU moderno
- **Calidad**: Buena
- **GPU**: Opcional
- **Ventaja**: Funciona sin instalación adicional

### Ollama/Orpheus

- **Tamaño**: ~3.5 GB (GGUF)
- **Velocidad**: Más lento que Kokoro
- **Calidad**: Muy buena
- **GPU**: Recomendado
- **Ventaja**: Mejor calidad de audio

## Base de datos

Usa SQLite con las siguientes tablas:

- `books` - Metadatos de libros
- `segments` - Texto dividido en chunks
- `reading_progress` - Posición actual por libro
- `settings` - Configuración del usuario (motor TTS, voz, etc.)

El archivo `audiobookplayer.db` se crea automáticamente en `data/`.

## Audio cacheado

Los audios generados se guardan en `data/audio_cache/`:
- Formato: WAV
- Naming: `{book_id}_{segment_index}.wav`
- Reutilización: Si eliminas el modelo TTS, los audios siguen funcionando

## API Endpoints

```
# Libros
POST   /books/upload              # Subir libro
GET    /books/                    # Listar libros
GET    /books/{id}                # Detalle
DELETE /books/{id}                # Eliminar

# Audio
GET    /audio/{book_id}/{seg_idx}          # Obtener/generar audio
GET    /audio/{book_id}/{seg_idx}/status   # Estado del audio
POST   /audio/{book_id}/generate-all       # Generar todos (background)

# Progreso
GET    /progress/{book_id}                 # Obtener posición
POST   /progress/{book_id}                 # Actualizar posición

# Configuración
GET    /settings/                          # Obtener settings
POST   /settings/                          # Actualizar setting
POST   /settings/test-voice                # Probar voz
```

## Solución de problemas

### "TTS not available"
- Verifica que el motor TTS esté correctamente configurado
- Para Kokoro: Necesita conexión a internet en primer uso (descarga modelo)
- Para Ollama: Asegúrate de que Ollama está corriendo y el modelo está descargado

### Audio lento o con lag
- Primera generación es más lenta mientras se descarga el modelo
- Generaciones subsecuentes son más rápidas (caché)
- Si es muy lento, considera bajar el tamaño de segmentos en `book_parser.py`

### Errores de dependencias
```bash
pip install --upgrade -r requirements.txt
```

### Base de datos corrompida
```bash
# Elimina la BD y reinicia
rm data/audiobookplayer.db
python main.py
```

## Personalización

### Cambiar tamaño de segmentos

En `book_parser.py`, función `split_into_segments()`:
```python
max_words=500  # Cambiar a 300 para segmentos más pequeños
```

### Agregar más voces Kokoro

Editar `routers/settings.py` y agregar en el select:
```html
<option value="af_sky">AF Sky</option>
```

## Limitaciones actuales

- Ollama/Orpheus: La decodificación de tokens SNAC es una versión simplificada
- No soporta marcapáginas o notas
- La búsqueda dentro del libro aún no está implementada

## Roadmap

- [ ] Búsqueda de texto dentro de libros
- [ ] Marcapáginas y anotaciones
- [ ] Soporte para audiobooks online (Audible API)
- [ ] Interfaz web mejorada (responsive)
- [ ] Sincronización entre dispositivos (servidor centralizado)

## Licencia

MIT

## Contacto

Para reportar bugs o sugerencias, abre un issue en el repo.

---

**¡Feliz lectura!** 📚🎧
