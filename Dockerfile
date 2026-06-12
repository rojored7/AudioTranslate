# ── AudioTranslate — PC A "EL ESTUDIO" ────────────────────────────────────────
# Imagen del equipo que SÍ procesa: sube libros, genera audio (Kokoro/Edge),
# y publica los libros a GitHub Releases para que PC B los reproduzca.
#
# PC B NO usa esta imagen. PC B corre player_lite/ con Python puro, sin Docker.

FROM python:3.11-slim

# libsndfile1 → requerido por soundfile (Kokoro escribe WAV con él).
# ffmpeg      → utilidad de audio por si se añade post-proceso.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Torch CPU-only PRIMERO (es dependencia de snac). Sin esto, pip bajaría la
# rueda CUDA (~2 GB) aunque el estudio sea CPU. Esto satisface a snac después.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# (Opcional) Kokoro — voces en inglés CPU. Descomenta si lo usas:
# RUN pip install --no-cache-dir kokoro

COPY . .

# data/ se monta como volumen (ver docker-compose.yml) → la DB, los libros y el
# audio_cache sobreviven a recreaciones del contenedor.
RUN mkdir -p data/books data/audio_cache

EXPOSE 9001

CMD ["python", "main.py"]
