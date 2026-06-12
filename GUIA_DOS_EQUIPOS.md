# Guía: dos equipos (Estudio + Reproductor)

Cómo tener **un equipo que procesa una sola vez** (genera el audio) y **otro
equipo ultra-liviano que solo reproduce** y recuerda por dónde vas, sincronizados
automáticamente por GitHub.

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│  PC A — "EL ESTUDIO"          │         │  PC B — "EL REPRODUCTOR"      │
│  procesa UNA vez              │         │  a duras penas reproduce      │
│                               │         │                               │
│  app completa (puerto 9001)   │         │  player_lite/ (puerto 9002)   │
│  · Kokoro / Edge / Ollama TTS │         │  · Python puro, CERO pip      │
│  · sube PDFs, genera TODO     │         │  · su propia DB local         │
│  · Docker o nativo            │         │  · guarda "por dónde vas"     │
└───────────────┬───────────────┘         └───────────────▲───────────────┘
                │ publica ZIP por libro                    │ revisa cada 5 min
                ▼                                          │ baja e importa solo
            ┌─────────────────────────────────────────────┴──┐
            │   GitHub Releases (repo PRIVADO) = el "bus"      │
            │   1 release por libro, tag  book-<id>            │
            └─────────────────────────────────────────────────┘
```

La regla de oro: **solo PC A genera audio.** PC B nunca procesa — no tiene
motores TTS instalados, físicamente no puede. Solo lee archivos del disco.

---

## Parte 0 — Preparar GitHub (una sola vez)

GitHub Releases es el punto de encuentro. Es gratis y soporta archivos grandes
(hasta 2 GB por libro) sin inflar el repositorio de código.

1. Crea un repositorio **privado** (los libros y el audio se subirán ahí).
   Puede ser el mismo repo del código o uno aparte solo para los Releases.
2. Crea un **token de acceso**:
   `https://github.com/settings/tokens` → *Generate new token (classic)* →
   marca el scope **`repo`** → genera y copia el token (`ghp_...`).
3. Guarda dos datos, los usarás en ambos equipos:
   - `GITHUB_REPO` = `tu-usuario/tu-repo`
   - `GITHUB_TOKEN` = `ghp_...`

> El repo **debe ser privado**: subes el texto de los libros y el audio completo.

---

## Parte 1 — PC A: el Estudio

### Opción A1 — Con Docker (recomendado)

Requiere Docker Desktop.

```bash
# 1. Crea el .env en la raíz del proyecto con tus datos de GitHub
copy .env.example .env       # luego edítalo: GITHUB_TOKEN y GITHUB_REPO

# 2. Levanta el estudio
docker compose up -d --build

# (opcional) con Ollama/Orpheus en vez de Kokoro:
docker compose --profile ollama up -d --build
```

- App en **http://localhost:9001**
- La biblioteca (DB + libros + audio) vive en `./data` y **persiste** aunque
  recrees el contenedor.
- Si activaste Ollama: en la app → *Configuración*, pon
  `ollama_url = http://ollama:11434` y descarga el modelo dentro del contenedor
  con `docker compose exec ollama ollama pull legraphista/Orpheus:latest`.

### Opción A2 — Nativo (sin Docker, Windows)

```bash
run.bat
```

Crea el venv, instala dependencias, inicializa la DB y arranca en
**http://localhost:9001**. (Para el auto-sync, crea igualmente el `.env` con
`GITHUB_TOKEN` y `GITHUB_REPO`.)

### Flujo de trabajo en PC A

1. Abre http://localhost:9001 y **sube** un PDF/EPUB/TXT.
2. Pulsa **Generar todo el audio**. Esto es lo único pesado y se hace **una vez**.
3. Al terminar, PC A **publica el libro solo** a GitHub (lo dispara
   `routers/audio.py` → `scripts/sync_to_github.py`).

Publicar a mano (si quieres forzarlo):

```bash
# todos los libros
python scripts/sync_to_github.py
# uno solo
python scripts/sync_to_github.py --book-id 3
# ver qué subiría, sin subir
python scripts/sync_to_github.py --dry-run

# dentro de Docker:
docker compose exec studio python scripts/sync_to_github.py
```

Cada libro queda como un **Release** con tag `book-<id>` y un `.zip` adjunto que
contiene `metadata.json` (texto + estructura) y la carpeta `audio/`.

---

## Parte 2 — PC B: el Reproductor

A PC B solo hay que llevarle **UN archivo: `instalar_equipo2.bat`**
(mándalo por correo, WhatsApp, USB, lo que sea). Todo lo demás se lo
descarga él solo desde GitHub.

1. Doble clic en **`instalar_equipo2.bat`**.
2. La primera vez pide dos datos (los mismos de PC A): el repo
   (`usuario/repositorio`) y el token (`ghp_...`).
3. Descarga el código del repo, lo instala en una carpeta `AudioBookLite`
   junto al .bat, guarda el `.env` y arranca `run.bat` → abre solo en
   **http://localhost:9002**.

**Actualizar PC B** = volver a ejecutar `instalar_equipo2.bat`. Baja la
última versión del código sin tocar los libros, el audio ni el progreso.

(Alternativa sin GitHub: copiar la carpeta `player_lite/` completa por USB
y hacer doble clic en su `run.bat`; ver `player_lite/LEEME.txt`.)

**Python se instala solo:** `run.bat` analiza el equipo; si no encuentra
Python ≥ 3.10 lo instala automáticamente (primero con `winget`, si no
descargando el instalador oficial de python.org en modo silencioso). Solo
hace falta internet la primera vez. Si tras instalar pide "cierra esta
ventana y vuelve a ejecutar run.bat", basta con relanzarlo. Sin internet:
instalar Python a mano desde python.org (marcar *"Add Python to PATH"*).

Qué hace PC B:

- Cada **5 minutos** revisa GitHub y baja los libros nuevos que aún no tenga
  (deduplica por `github_sync_log`, no re-descarga lo que ya importó).
- Botón **"Sincronizar ahora"** para no esperar.
- Guarda en su **propia** base (`player_lite/data/player_lite.db`) los libros,
  el audio y **por dónde vas en cada uno**.
- **Sin internet:** arrastra un `.zip` (pasado por USB desde el Release o el
  botón *Exportar* de PC A) a la ventana → se importa igual.

Ajustes opcionales en `player_lite/.env`:

```
SYNC_INTERVAL_MINUTES=5    # cada cuánto revisar GitHub
```

---

## Parte 3 — Operación del día a día

| Acción | Dónde | Cómo |
|--------|-------|------|
| Agregar un libro | PC A | Subir archivo + "Generar todo el audio" |
| Publicar a GitHub | PC A | Automático al terminar (o `sync_to_github.py`) |
| Recibir el libro | PC B | Automático (≤5 min) o "Sincronizar ahora" |
| Escuchar / continuar | PC B | Abrir el libro; recuerda el segmento |
| Reiniciar un libro (volver al 0%) | PC A o PC B | Botón **↺ Reiniciar** en la tarjeta del libro |
| Mover B a otra máquina | PC B | Copiar la carpeta `player_lite/data/` |

---

## Solución de problemas

**PC B dice "Sync desactivado".**
Falta `GITHUB_TOKEN` o `GITHUB_REPO` en `player_lite/.env`. Revísalos y reinicia
`run.bat`.

**PC B no baja un libro nuevo.**
1. ¿PC A lo publicó? Revisa la pestaña *Releases* del repo (debe existir el tag
   `book-<id>` con su `.zip`).
2. ¿El token de B tiene scope `repo` y acceso al repo privado?
3. Pulsa "Sincronizar ahora" y mira la ventana negra: imprime el error exacto.

**El audio no suena en PC B.**
El `.zip` se importó pero sin audio: en PC A asegúrate de **generar TODO** el
audio *antes* de publicar (un libro sin audio sube solo el texto).

**La imagen de Docker pesa mucho.**
Es normal: incluye PyTorch (para SNAC/Orpheus). Si solo usas Edge TTS o Kokoro,
puedes quitar `snac` de `requirements.txt` y reconstruir para adelgazarla.

**El `.env` no se sube por error.**
Ya está en `.gitignore` (junto con `*.db` y `data/`). No lo quites de ahí.
