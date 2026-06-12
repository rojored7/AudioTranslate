const API_URL = window.location.origin;

window.ttsAvailable = false;

// ============ TTS DETECTION ============

async function detectTTSMode() {
    try {
        const res = await fetch(`${API_URL}/settings/tts-status`);
        const data = await res.json();
        window.ttsAvailable = data.available;
        applyTTSMode(data.available, data.engine, data.model);
    } catch {
        window.ttsAvailable = false;
        applyTTSMode(false, null, null);
    }
}

function applyTTSMode(available, engine, model) {
    // Library page banner
    const banner = document.getElementById('ttsBanner');
    if (banner) {
        if (available) {
            banner.textContent = `TTS activo — ${engine || 'Ollama'} (${model || ''})`;
            banner.className = 'tts-banner tts-banner--on';
        } else {
            banner.textContent = 'TTS no disponible — solo se reproducen audios ya generados.';
            banner.className = 'tts-banner tts-banner--off';
        }
        banner.style.display = 'block';
    }

    // Player header status dot
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    if (statusDot && statusText) {
        if (available) {
            statusDot.className = 'status-dot available';
            statusText.textContent = `${engine || 'Ollama'} activo`;
        } else {
            statusDot.className = 'status-dot unavailable';
            statusText.textContent = 'TTS no disponible';
        }
    }
}

// ============ LIBRARY PAGE ============

async function initLibrary() {
    if (!document.getElementById('booksList')) return;
    await detectTTSMode();
    setupUpload();
    setupSettingsModal();
    loadBooks();
}

function setupUpload() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');

    uploadBox.addEventListener('click', () => fileInput.click());

    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.classList.add('upload-box--drag');
    });

    uploadBox.addEventListener('dragleave', () => {
        uploadBox.classList.remove('upload-box--drag');
    });

    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('upload-box--drag');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            uploadFile();
        }
    });

    fileInput.addEventListener('change', uploadFile);
}

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    document.getElementById('uploadBox').style.display = 'none';
    document.getElementById('uploadProgress').style.display = 'block';
    document.getElementById('uploadStatus').textContent = 'Procesando libro...';

    try {
        const response = await fetch(`${API_URL}/books/upload`, {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();

        if (response.ok) {
            document.getElementById('uploadStatus').textContent = `Listo: ${data.message}`;
            document.getElementById('progressFill').style.width = '100%';
            setTimeout(() => {
                document.getElementById('uploadBox').style.display = '';
                document.getElementById('uploadProgress').style.display = 'none';
                fileInput.value = '';
                loadBooks();
            }, 1200);
        } else {
            throw new Error(data.detail || 'Error al subir libro');
        }
    } catch (error) {
        alert('Error: ' + error.message);
        document.getElementById('uploadBox').style.display = '';
        document.getElementById('uploadProgress').style.display = 'none';
    }
}

async function loadBooks() {
    try {
        const response = await fetch(`${API_URL}/books/`);
        const data = await response.json();
        const booksList = document.getElementById('booksList');
        booksList.innerHTML = '';

        if (!data.books || data.books.length === 0) {
            booksList.innerHTML = '<p class="loading">Sin libros. Sube un PDF, EPUB o TXT para comenzar.</p>';
            return;
        }

        for (const book of data.books) {
            const readPct = Math.round((book.current_segment / book.total_segments) * 100) || 0;
            const audioCached = book.audio_cached || 0;
            const audioPct = Math.round((audioCached / book.total_segments) * 100) || 0;
            const audioLabel = audioCached >= book.total_segments
                ? '✓ Audio completo'
                : `${audioCached} / ${book.total_segments} segmentos generados`;

            const card = document.createElement('div');
            card.className = 'book-card';
            card.id = `book-card-${book.id}`;
            card.innerHTML = `
                <h3>${escapeHtml(book.title)}</h3>
                <p><strong>${escapeHtml(book.author || 'Autor desconocido')}</strong></p>
                <p style="font-size:0.85em;color:#999;">${book.format.toUpperCase()} · ${book.total_segments} segmentos</p>

                <div class="book-progress">
                    <div class="progress-label">Lectura: ${readPct}%</div>
                    <div class="progress-bar-small">
                        <div class="progress-fill" style="width:${readPct}%"></div>
                    </div>
                </div>

                <div class="book-progress" style="margin-top:8px;">
                    <div class="progress-label" id="audio-label-${book.id}">${audioLabel}</div>
                    <div class="progress-bar-small">
                        <div class="progress-fill" id="audio-fill-${book.id}" style="width:${audioPct}%;background:var(--warning)"></div>
                    </div>
                </div>

                <p id="gen-status-${book.id}" class="gen-status" style="display:none;"></p>

                <div class="book-actions">
                    ${window.ttsAvailable ? `<button class="btn btn-secondary" id="gen-btn-${book.id}" onclick="startGeneration(${book.id}, ${book.total_segments})">⚡ Generar Audio</button>` : ''}
                    <button class="btn btn-primary" onclick="goToPlayer(${book.id})">▶ Escuchar</button>
                    <button class="btn btn-secondary" id="export-btn-${book.id}" onclick="exportBook(${book.id}, '${escapeHtml(book.title)}')">📦 Exportar</button>
                    <button class="btn btn-secondary" onclick="resetBook(${book.id})">↺ Reiniciar</button>
                    <button class="btn btn-danger-soft" onclick="deleteBook(${book.id})">Eliminar</button>
                </div>
            `;
            booksList.appendChild(card);
        }
    } catch (error) {
        document.getElementById('booksList').innerHTML = '<p class="loading">Error cargando libros</p>';
    }
}

async function startGeneration(bookId, totalSegments) {
    const btn = document.getElementById(`gen-btn-${bookId}`);
    const statusEl = document.getElementById(`gen-status-${bookId}`);
    if (!btn) return;

    btn.disabled = true;
    btn.textContent = '⏳ Generando...';
    if (statusEl) { statusEl.style.display = 'block'; statusEl.textContent = 'Iniciando...'; }

    try {
        const res = await fetch(`${API_URL}/audio/${bookId}/generate-all`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            if (statusEl) statusEl.textContent = 'Error: ' + (err.detail || 'No se pudo iniciar');
            btn.disabled = false;
            btn.textContent = '⚡ Generar Audio';
            return;
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = 'Error: ' + e.message;
        btn.disabled = false;
        btn.textContent = '⚡ Generar Audio';
        return;
    }

    // Poll progress every 5 seconds using the file-based progress endpoint
    const poll = setInterval(async () => {
        try {
            const r = await fetch(`${API_URL}/audio/${bookId}/progress`);
            const data = await r.json();
            const cached = data.cached;
            const pct = Math.round((cached / totalSegments) * 100);

            const fill = document.getElementById(`audio-fill-${bookId}`);
            const label = document.getElementById(`audio-label-${bookId}`);
            if (fill) fill.style.width = pct + '%';
            if (label) label.textContent = `${cached} / ${totalSegments} segmentos generados`;
            if (statusEl) statusEl.textContent = `Progreso: ${pct}%`;

            if (cached >= totalSegments) {
                clearInterval(poll);
                if (label) label.textContent = '✓ Audio completo';
                if (statusEl) statusEl.textContent = '✓ Generación completada';
                btn.textContent = '✓ Audio listo';
                btn.disabled = false;
            }
        } catch (_) {}
    }, 5000);
}

function goToPlayer(bookId) {
    window.location.href = `/static/player.html?book_id=${bookId}`;
}

async function exportBook(bookId, bookTitle) {
    const btn = document.getElementById(`export-btn-${bookId}`);
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = '⏳ Exportando...';
    try {
        const response = await fetch(`${API_URL}/books/${bookId}/export`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Error exportando');
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audiobook_${bookTitle.replace(/[^a-z0-9]/gi, '_')}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        btn.textContent = '✓ Descargado';
        setTimeout(() => { btn.textContent = '📦 Exportar'; btn.disabled = false; }, 2000);
    } catch (e) {
        alert('Error exportando: ' + e.message);
        btn.textContent = '📦 Exportar';
        btn.disabled = false;
    }
}

async function resetBook(bookId) {
    if (!confirm('¿Reiniciar el progreso de este libro? Volverás al inicio.')) return;
    try {
        const response = await fetch(`${API_URL}/progress/${bookId}/reset`, { method: 'POST' });
        if (response.ok) loadBooks();
        else alert('Error reiniciando progreso');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function deleteBook(bookId) {
    if (!confirm('¿Eliminar este libro y sus audios cacheados?')) return;
    try {
        const response = await fetch(`${API_URL}/books/${bookId}`, { method: 'DELETE' });
        if (response.ok) loadBooks();
        else alert('Error eliminando libro');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

function setupSettingsModal() {
    const modal = document.getElementById('settingsModal');
    document.getElementById('settingsBtn').addEventListener('click', () => {
        modal.style.display = 'flex';
        loadSettings();
    });
    document.getElementById('closeSettings').addEventListener('click', () => modal.style.display = 'none');
    document.getElementById('cancelSettings').addEventListener('click', () => modal.style.display = 'none');
    document.getElementById('saveSettings').addEventListener('click', saveSettings);
    document.getElementById('testVoiceBtn').addEventListener('click', testVoice);

    document.getElementById('ttsEngine').addEventListener('change', (e) => {
        const v = e.target.value;
        document.getElementById('edgeTtsSettings').style.display = v === 'edge_tts' ? 'block' : 'none';
        document.getElementById('ollamaSettings').style.display = v === 'ollama' ? 'block' : 'none';
        document.getElementById('kokoroSettings').style.display = v === 'kokoro' ? 'block' : 'none';
    });

    window.addEventListener('click', (e) => { if (e.target === modal) modal.style.display = 'none'; });
}

async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/settings/`);
        const settings = await response.json();
        const engine = settings.tts_engine || 'edge_tts';
        document.getElementById('ttsEngine').value = engine;
        document.getElementById('ollamaUrl').value = settings.ollama_url || 'http://localhost:11434';
        document.getElementById('ollamaModel').value = settings.ollama_model || 'legraphista/Orpheus:latest';
        document.getElementById('kokoroVoice').value = settings.kokoro_voice || 'af_heart';
        document.getElementById('edgeTtsVoice').value = settings.edge_tts_voice || 'es-ES-AlvaroNeural';
        document.getElementById('edgeTtsSettings').style.display = engine === 'edge_tts' ? 'block' : 'none';
        document.getElementById('ollamaSettings').style.display = engine === 'ollama' ? 'block' : 'none';
        document.getElementById('kokoroSettings').style.display = engine === 'kokoro' ? 'block' : 'none';
    } catch (_) {}
}

async function saveSettings() {
    const settings = [
        { key: 'tts_engine', value: document.getElementById('ttsEngine').value },
        { key: 'ollama_url', value: document.getElementById('ollamaUrl').value },
        { key: 'ollama_model', value: document.getElementById('ollamaModel').value },
        { key: 'kokoro_voice', value: document.getElementById('kokoroVoice').value },
        { key: 'edge_tts_voice', value: document.getElementById('edgeTtsVoice').value },
    ];
    try {
        for (const s of settings) {
            await fetch(`${API_URL}/settings/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(s),
            });
        }
        document.getElementById('settingsModal').style.display = 'none';
        await detectTTSMode();
        loadBooks();
    } catch (error) {
        alert('Error guardando: ' + error.message);
    }
}

async function testVoice() {
    const testStatus = document.getElementById('testStatus');
    const testBtn = document.getElementById('testVoiceBtn');
    const engine = document.getElementById('ttsEngine').value;
    const voice = engine === 'edge_tts'
        ? document.getElementById('edgeTtsVoice').value
        : engine === 'kokoro'
            ? document.getElementById('kokoroVoice').value
            : null;

    testBtn.disabled = true;
    testStatus.textContent = 'Generando muestra de audio...';
    testStatus.style.color = '';

    try {
        const params = new URLSearchParams({ engine_type: engine });
        if (voice) params.append('voice', voice);
        const response = await fetch(`${API_URL}/settings/preview-voice?${params}`, { method: 'POST' });

        if (!response.ok) {
            const err = await response.json();
            testStatus.textContent = err.detail || 'Error generando audio';
            testStatus.style.color = '#ef4444';
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        audio.play();
        testStatus.textContent = '▶ Reproduciendo muestra...';
        testStatus.style.color = '#10b981';
    } catch (error) {
        testStatus.textContent = 'Error: ' + error.message;
        testStatus.style.color = '#ef4444';
    } finally {
        testBtn.disabled = false;
    }
}

// ============ PLAYER PAGE (solo reproducción) ============

async function initPlayer() {
    const params = new URLSearchParams(window.location.search);
    const bookId = parseInt(params.get('book_id'));
    if (!bookId) { window.location.href = '/'; return; }

    document.getElementById('backBtn').addEventListener('click', () => { window.location.href = '/'; });

    await detectTTSMode();
    await loadBookDetails(bookId);
}

async function loadBookDetails(bookId) {
    try {
        const response = await fetch(`${API_URL}/books/${bookId}`);
        const data = await response.json();
        const { book, segments, current_segment } = data;

        document.getElementById('bookTitle').textContent = escapeHtml(book.title);
        document.getElementById('totalSegments').textContent = segments.length;

        const segmentsList = document.getElementById('segmentsList');
        segmentsList.innerHTML = '';
        for (const seg of segments) {
            const isCached = !!seg.audio_path;
            const item = document.createElement('div');
            item.className = 'segment-item' +
                (seg.segment_index === current_segment ? ' active' : '') +
                (isCached ? ' cached' : '');
            item.innerHTML = `<span class="segment-dot"></span>${seg.segment_index + 1}`;
            item.title = isCached ? 'Audio disponible' : 'Sin audio — genera desde la Biblioteca';
            if (!isCached) item.style.opacity = '0.5';
            item.addEventListener('click', () => loadSegment(bookId, seg.segment_index, segments));
            segmentsList.appendChild(item);
        }

        await loadSegment(bookId, current_segment, segments);
        setupPlayerControls(bookId, segments.length, segments);
    } catch (error) {
        console.error('Error loading book:', error);
    }
}

async function loadSegment(bookId, segmentIndex, segments) {
    try {
        // Save progress
        await fetch(`${API_URL}/progress/${bookId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ segment: segmentIndex }),
        });

        const segment = segments[segmentIndex];
        document.getElementById('segmentText').textContent = segment.text;
        document.getElementById('currentSegment').textContent = segmentIndex + 1;

        document.querySelectorAll('.segment-item').forEach((item, i) => {
            item.classList.toggle('active', i === segmentIndex);
        });

        const audioPlayer = document.getElementById('audioPlayer');
        const generatingBox = document.getElementById('generatingBox');
        const generatingText = document.getElementById('generatingText');
        const audioUrl = `${API_URL}/audio/${bookId}/${segmentIndex}`;

        const statusRes = await fetch(`${API_URL}/audio/${bookId}/${segmentIndex}/status`);
        const status = await statusRes.json();

        if (status.cached) {
            // Restore spinner visibility in case it was hidden
            const spinner = generatingBox ? generatingBox.querySelector('.spinner') : null;
            if (spinner) spinner.style.display = '';
            if (generatingBox) generatingBox.style.display = 'none';

            audioPlayer.src = audioUrl;
            const speedEl = document.getElementById('speedSelect');
            if (speedEl) audioPlayer.playbackRate = parseFloat(speedEl.value);
            syncPlayPauseBtn(audioPlayer);
            audioPlayer.play().catch(() => {});
        } else {
            // No audio yet — tell user to generate from library
            if (generatingBox) {
                const spinner = generatingBox.querySelector('.spinner');
                if (spinner) spinner.style.display = 'none';
                if (generatingText) generatingText.textContent = 'Sin audio — genera el audio desde la Biblioteca.';
                generatingBox.style.display = 'flex';
            }
            syncPlayPauseBtn(audioPlayer, 'no-audio');
            audioPlayer.src = '';
        }

        const pct = Math.round(((segmentIndex + 1) / segments.length) * 100);
        document.getElementById('progressPercent').textContent = pct + '%';
        document.getElementById('progressSlider').value = pct;

    } catch (error) {
        console.error('Error loading segment:', error);
    }
}

function syncPlayPauseBtn(audioPlayer, state) {
    const btn = document.getElementById('playPauseBtn');
    if (!btn) return;
    if (state === 'no-audio') {
        btn.textContent = 'Sin audio';
        btn.disabled = true;
    } else {
        btn.disabled = false;
        btn.textContent = audioPlayer.paused ? '▶ Reproducir' : '⏸ Pausar';
    }
}

function currentSegmentIndex() {
    return parseInt(document.getElementById('currentSegment').textContent) - 1;
}

function setupPlayerControls(bookId, totalSegments, segments) {
    const audioPlayer = document.getElementById('audioPlayer');

    document.getElementById('prevBtn').addEventListener('click', () => {
        const idx = currentSegmentIndex();
        if (idx > 0) loadSegment(bookId, idx - 1, segments);
    });

    document.getElementById('nextBtn').addEventListener('click', () => {
        const idx = currentSegmentIndex();
        if (idx < totalSegments - 1) loadSegment(bookId, idx + 1, segments);
    });

    document.getElementById('playPauseBtn').addEventListener('click', () => {
        if (audioPlayer.paused) {
            audioPlayer.play().catch(() => {});
        } else {
            audioPlayer.pause();
        }
    });

    audioPlayer.addEventListener('play',  () => syncPlayPauseBtn(audioPlayer));
    audioPlayer.addEventListener('pause', () => syncPlayPauseBtn(audioPlayer));
    audioPlayer.addEventListener('ended', () => {
        syncPlayPauseBtn(audioPlayer);
        const idx = currentSegmentIndex();
        if (idx < totalSegments - 1) loadSegment(bookId, idx + 1, segments);
    });

    document.getElementById('progressSlider').addEventListener('change', (e) => {
        const pct = parseInt(e.target.value);
        const idx = Math.min(Math.floor((pct / 100) * totalSegments), totalSegments - 1);
        loadSegment(bookId, idx, segments);
    });

    document.getElementById('speedSelect').addEventListener('change', (e) => {
        audioPlayer.playbackRate = parseFloat(e.target.value);
    });
}

// ============ UTILITIES ============

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('player.html')) {
        initPlayer();
    } else {
        initLibrary();
    }
});
