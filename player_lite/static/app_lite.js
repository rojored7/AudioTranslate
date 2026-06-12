const API_URL = window.location.origin;

// ============ LIBRARY PAGE ============

async function initLibrary() {
    setupImport();
    loadBooks();
    await initSyncBar();
    startSyncPolling();
}

function setupImport() {
    const importBox = document.getElementById('importBox');
    const fileInput = document.getElementById('fileInput');

    importBox.addEventListener('click', () => fileInput.click());

    importBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        importBox.classList.add('upload-box--drag');
    });
    importBox.addEventListener('dragleave', () => importBox.classList.remove('upload-box--drag'));
    importBox.addEventListener('drop', (e) => {
        e.preventDefault();
        importBox.classList.remove('upload-box--drag');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            importZip();
        }
    });

    fileInput.addEventListener('change', importZip);
}

async function importZip() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    document.getElementById('importBox').style.display = 'none';
    document.getElementById('importProgress').style.display = 'block';
    document.getElementById('importStatus').textContent = 'Importando libro...';
    document.getElementById('progressFill').style.width = '30%';

    try {
        const response = await fetch(`${API_URL}/books/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: file,
        });
        const data = await response.json();
        if (response.ok) {
            document.getElementById('progressFill').style.width = '100%';
            document.getElementById('importStatus').textContent = `¡Importado: ${escapeHtml(data.title)}!`;
            setTimeout(() => {
                document.getElementById('importBox').style.display = '';
                document.getElementById('importProgress').style.display = 'none';
                fileInput.value = '';
                loadBooks();
            }, 1500);
        } else {
            throw new Error(data.detail || 'Error importando');
        }
    } catch (error) {
        alert('Error importando: ' + error.message);
        document.getElementById('importBox').style.display = '';
        document.getElementById('importProgress').style.display = 'none';
    }
}

async function loadBooks() {
    try {
        const response = await fetch(`${API_URL}/books/`);
        const data = await response.json();
        const booksList = document.getElementById('booksList');
        booksList.innerHTML = '';

        if (!data.books || data.books.length === 0) {
            booksList.innerHTML = '<p class="loading">Sin libros. Importa un archivo .zip exportado desde PC A.</p>';
            return;
        }

        for (const book of data.books) {
            const readPct = Math.round((book.current_segment / book.total_segments) * 100) || 0;
            const audioCached = book.audio_cached || 0;
            const audioPct = Math.round((audioCached / book.total_segments) * 100) || 0;
            const audioLabel = audioCached >= book.total_segments
                ? '✓ Audio completo'
                : `${audioCached} / ${book.total_segments} segmentos con audio`;

            const card = document.createElement('div');
            card.className = 'book-card';
            card.innerHTML = `
                <h3>${escapeHtml(book.title)}</h3>
                <p><strong>${escapeHtml(book.author || 'Autor desconocido')}</strong></p>
                <p style="font-size:0.85em;color:#999;">${(book.format || '').toUpperCase()} · ${book.total_segments} segmentos</p>

                <div class="book-progress">
                    <div class="progress-label">Lectura: ${readPct}%</div>
                    <div class="progress-bar-small">
                        <div class="progress-fill" style="width:${readPct}%"></div>
                    </div>
                </div>

                <div class="book-progress" style="margin-top:8px;">
                    <div class="progress-label">${audioLabel}</div>
                    <div class="progress-bar-small">
                        <div class="progress-fill" style="width:${audioPct}%;background:var(--warning)"></div>
                    </div>
                </div>

                <div class="book-actions">
                    <button class="btn btn-primary" onclick="goToPlayer(${book.id})">▶ Escuchar</button>
                    <button class="btn btn-secondary" onclick="resetBook(${book.id})">↺ Reiniciar</button>
                </div>
            `;
            booksList.appendChild(card);
        }
    } catch (error) {
        document.getElementById('booksList').innerHTML = '<p class="loading">Error cargando libros</p>';
    }
}

function goToPlayer(bookId) {
    window.location.href = `/static/player.html?book_id=${bookId}`;
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

// ============ PLAYER PAGE ============

async function initPlayer() {
    const params = new URLSearchParams(window.location.search);
    const bookId = parseInt(params.get('book_id'));
    if (!bookId) { window.location.href = '/'; return; }

    document.getElementById('backBtn').addEventListener('click', () => { window.location.href = '/'; });
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
            item.title = isCached ? 'Audio disponible' : 'Sin audio';
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
        const noAudioBox = document.getElementById('noAudioBox');

        const statusRes = await fetch(`${API_URL}/audio/${bookId}/${segmentIndex}/status`);
        const status = await statusRes.json();

        if (status.cached) {
            if (noAudioBox) noAudioBox.style.display = 'none';
            audioPlayer.src = `${API_URL}/audio/${bookId}/${segmentIndex}`;
            const speedEl = document.getElementById('speedSelect');
            if (speedEl) audioPlayer.playbackRate = parseFloat(speedEl.value);
            syncPlayPauseBtn(audioPlayer);
            audioPlayer.play().catch(() => {});
        } else {
            if (noAudioBox) noAudioBox.style.display = 'flex';
            audioPlayer.src = '';
            syncPlayPauseBtn(audioPlayer, 'no-audio');
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
        if (audioPlayer.paused) audioPlayer.play().catch(() => {});
        else audioPlayer.pause();
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

// ============ SYNC BAR ============

async function initSyncBar() {
    try {
        const resp = await fetch(`${API_URL}/sync/status`);
        const data = await resp.json();
        if (!data.enabled) return;
        document.getElementById('syncBar').style.display = 'flex';
        updateSyncBar(data);
    } catch (e) { /* sync no disponible, dejar barra oculta */ }
}

function updateSyncBar(data) {
    const bar = document.getElementById('syncBar');
    const txt = document.getElementById('syncStatusText');
    if (!bar) return;
    bar.classList.toggle('sync-error', !!data.last_error);
    if (data.last_error) {
        txt.textContent = `Error de sync: ${data.last_error}`;
    } else if (data.last_sync_at) {
        const last = new Date(data.last_sync_at).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
        const next = data.next_sync_at
            ? new Date(data.next_sync_at).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
            : '—';
        txt.textContent = `Última sync: ${last} · Próxima: ${next} · Repo: ${data.github_repo}`;
    } else {
        txt.textContent = 'Esperando primera sincronización...';
    }
}

async function triggerSync() {
    const txt = document.getElementById('syncStatusText');
    if (txt) txt.textContent = 'Sincronizando con GitHub...';
    try {
        await fetch(`${API_URL}/sync/now`, { method: 'POST' });
        setTimeout(async () => {
            try {
                const resp = await fetch(`${API_URL}/sync/status`);
                const data = await resp.json();
                updateSyncBar(data);
                loadBooks();
            } catch (e) {}
        }, 3000);
    } catch (e) {
        if (txt) txt.textContent = 'Error al iniciar sincronización';
    }
}

let _syncPollTimer = null;
function startSyncPolling() {
    if (_syncPollTimer) clearInterval(_syncPollTimer);
    _syncPollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`${API_URL}/sync/status`);
            const data = await resp.json();
            if (data.enabled) updateSyncBar(data);
        } catch (e) {}
    }, 30000);
}

// ============ UTILITIES ============

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('player.html')) {
        initPlayer();
    } else {
        initLibrary();
    }
});
