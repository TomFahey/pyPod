/* ════════════════════════════════════════════════════════════════════
   Floating Python REPL widget — pyPod edition
   Loads Pyodide lazily on first open, shimming the pypod module so
   add_track(), show_lyrics(), show_timestamp() etc. update a mini
   MP3-player simulation panel in the browser.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const PYODIDE_VERSION = '0.29.4';
  const PYODIDE_INDEX   = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

  let pyodide   = null;
  let pyReady   = false;
  let pyLoading = false;
  let panelOpen = false;

  // ── Build widget DOM ────────────────────────────────────────────────────
  function buildWidget() {
    const w = document.createElement('div');
    w.id = 'repl-widget';
    w.innerHTML = `
<button id="repl-fab" title="Open Python playground">
  <span>🐍</span><span>Python</span>
</button>
<div id="repl-panel" aria-hidden="true" aria-label="Python playground">
  <div id="repl-header">
    <span>🐍 Try it in Python</span>
    <button id="repl-close" title="Minimise" aria-label="Close">✕</button>
  </div>

  <!-- ── Song list simulation ── -->
  <div id="repl-songlist-wrap">
    <div class="repl-section-label">🎵 Song List</div>
    <ul id="sim-songlist"></ul>
    <div id="sim-songlist-empty" class="repl-empty-hint">No tracks yet — try calling <code>add_track()</code></div>
  </div>

  <!-- ── Now-playing simulation ── -->
  <div id="repl-nowplaying-wrap">
    <div class="repl-section-label">🎤 Now Playing</div>
    <div id="sim-nowplaying" class="repl-nowplaying-default">Nothing playing</div>
    <div class="repl-progress-row">
      <span id="sim-timestamp" class="repl-timestamp">0:00</span>
      <div class="repl-progress-bg">
        <div id="sim-progress" class="repl-progress-fill"></div>
      </div>
    </div>
    <div id="sim-lyrics" class="repl-lyrics"></div>
  </div>

  <!-- ── Code editor ── -->
  <div id="repl-editor">
    <textarea id="repl-code"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
              placeholder="Type Python here, then press Run (or Ctrl+Enter)…"></textarea>
    <div id="repl-toolbar">
      <button id="repl-run" disabled>▶ Run</button>
      <button id="repl-clear">Clear</button>
      <span class="repl-hint">Ctrl+Enter to run</span>
    </div>
  </div>

  <!-- ── Output ── -->
  <div id="repl-output-wrap">
    <div id="repl-status"></div>
    <pre id="repl-output"></pre>
  </div>
</div>`;
    document.body.appendChild(w);
  }

  // ── Pyodide loading ─────────────────────────────────────────────────────
  function loadPyodideScript() {
    return new Promise((resolve, reject) => {
      if (window.loadPyodide) { resolve(); return; }
      const s = document.createElement('script');
      s.src = PYODIDE_INDEX + 'pyodide.js';
      s.onload  = resolve;
      s.onerror = () => reject(new Error('Failed to load Pyodide script'));
      document.head.appendChild(s);
    });
  }

  async function initPyodide() {
    if (pyReady || pyLoading) return;
    pyLoading = true;
    setStatus('Loading Python… (first time takes ~5 seconds)');
    try {
      await loadPyodideScript();
      pyodide = await window.loadPyodide({ indexURL: PYODIDE_INDEX });

      // Install pypod shim + mock SD-card filesystem
      await pyodide.runPythonAsync(`
import sys, types, os

_mod = types.ModuleType('pypod')

# ── Create mock SD-card filesystem ────────────────────────────────────────
os.makedirs('/sd/music', exist_ok=True)
os.makedirs('/sd/transcripts', exist_ok=True)

for _fn in ['Wonderwall (Oasis).mp3',
            'Never Gonna Give You Up (Rick Astley).mp3',
            'Bohemian Rhapsody (Queen).mp3']:
    open('/sd/music/' + _fn, 'w').close()

with open('/sd/transcripts/Wonderwall.txt', 'w') as _f:
    _f.write("0:04\\t[Intro]\\n")
    _f.write("0:26\\tToday is gonna be the day\\n")
    _f.write("0:30\\tThat they're gonna throw it back to you\\n")
    _f.write("0:34\\tBy now you should've somehow realized what you gotta do\\n")
    _f.write("0:43\\tI don't believe that anybody feels the way I do about you now\\n")

with open('/sd/transcripts/Never Gonna Give You Up.txt', 'w') as _f:
    _f.write("0:18\\t[Intro]\\n")
    _f.write("0:43\\tWe're no strangers to love\\n")
    _f.write("0:47\\tYou know the rules and so do I\\n")
    _f.write("0:51\\tA full commitment's what I'm thinking of\\n")
    _f.write("0:55\\tYou wouldn't get this from any other guy\\n")

with open('/sd/transcripts/Bohemian Rhapsody.txt', 'w') as _f:
    _f.write("0:00\\t[Intro]\\n")
    _f.write("0:49\\tIs this the real life?\\n")
    _f.write("0:52\\tIs this just fantasy?\\n")
    _f.write("0:55\\tCaught in a landslide,\\n")
    _f.write("0:58\\tNo escape from reality\\n")

# ── Internal state ─────────────────────────────────────────────────────────
_tracks = []
_current_track = None
_on_song_selected_fn = None
_on_track_ended_fn   = None
_on_tick_fn          = None

# ── DOM helpers ────────────────────────────────────────────────────────────
def _js_el(_id):
    from js import document
    return document.getElementById(_id)

def _set_text(_id, text):
    el = _js_el(_id)
    if el: el.textContent = str(text)

# ── Track class ────────────────────────────────────────────────────────────
class Track:
    def __init__(self, title='', artist='', file_path=None, lyrics=None):
        self.title     = title
        self.artist    = artist
        self.file_path = file_path
        self.lyrics    = lyrics or []
    def __repr__(self):
        return f'Track("{self.title}", "{self.artist}")'

# ── Public API ─────────────────────────────────────────────────────────────
def add_track(track):
    global _tracks
    _tracks.append(track)
    el    = _js_el('sim-songlist')
    empty = _js_el('sim-songlist-empty')
    if el:
        from js import document
        li = document.createElement('li')
        li.textContent = f'{track.title} — {track.artist}'
        el.appendChild(li)
    if empty:
        empty.style.display = 'none'

def clear_tracks():
    global _tracks
    _tracks = []
    el    = _js_el('sim-songlist')
    empty = _js_el('sim-songlist-empty')
    if el:
        while el.firstChild:
            el.removeChild(el.firstChild)
    if empty:
        empty.style.display = 'block'

def list_music_files():
    try:
        return sorted(f for f in os.listdir('/sd/music') if f.endswith('.mp3'))
    except Exception:
        return ['Wonderwall (Oasis).mp3',
                'Never Gonna Give You Up (Rick Astley).mp3',
                'Bohemian Rhapsody (Queen).mp3']

def music_path(filename):
    return '/sd/music/' + filename

def lyrics_path(title):
    return '/sd/transcripts/' + title + '.txt'

def play(track):
    global _current_track
    _current_track = track
    el = _js_el('sim-nowplaying')
    if el:
        el.textContent = f'\\u25b6 {track.title} \\u2014 {track.artist}'
        el.className   = 'repl-nowplaying-active'

def pause():
    el = _js_el('sim-nowplaying')
    if el and el.textContent.startswith('\\u25b6'):
        el.textContent = '\\u23f8 ' + el.textContent[2:]

def resume():
    el = _js_el('sim-nowplaying')
    if el and el.textContent.startswith('\\u23f8'):
        el.textContent = '\\u25b6 ' + el.textContent[2:]

def stop():
    global _current_track
    _current_track = None
    el = _js_el('sim-nowplaying')
    if el:
        el.textContent = 'Nothing playing'
        el.className   = 'repl-nowplaying-default'

def next_track():     pass
def previous_track(): pass
def set_volume(v):    pass
def get_volume():     return 60
def is_playing():     return False
def get_elapsed():    return 0
def show_now_playing(track): play(track)

def show_progress(elapsed, total):
    el = _js_el('sim-progress')
    if el and total > 0:
        pct = min(int(elapsed * 100 / total), 100)
        el.style.width = f'{pct}%'

def show_timestamp(elapsed):
    mins = int(elapsed) // 60
    secs = int(elapsed) % 60
    _set_text('sim-timestamp', f'{mins}:{secs:02d}')

def show_lyrics(text):
    _set_text('sim-lyrics', str(text))

def on_song_selected(fn):
    global _on_song_selected_fn
    _on_song_selected_fn = fn
    return fn

def on_track_ended(fn):
    global _on_track_ended_fn
    _on_track_ended_fn = fn
    return fn

def on_tick(fn):
    global _on_tick_fn
    _on_tick_fn = fn
    return fn

def start():
    n = len(_tracks)
    print(f'\\u2705 pyPod started! (browser simulation)')
    print(f'   {n} track{"s" if n != 1 else ""} in the song list.')
    if n:
        for t in _tracks:
            print(f'   \\u2022 {t.title} \\u2014 {t.artist}')

# ── Populate the module ────────────────────────────────────────────────────
_API = ['Track', 'add_track', 'clear_tracks', 'list_music_files',
        'music_path', 'lyrics_path', 'play', 'pause', 'resume', 'stop',
        'next_track', 'previous_track', 'set_volume', 'get_volume',
        'is_playing', 'get_elapsed', 'show_progress', 'show_timestamp',
        'show_lyrics', 'show_now_playing', 'on_song_selected',
        'on_track_ended', 'on_tick', 'start']

_g = globals()
for _name in _API:
    setattr(_mod, _name, _g[_name])

sys.modules['pypod'] = _mod
`);
      pyReady   = true;
      pyLoading = false;
      setStatus('');
      document.getElementById('repl-run').disabled = false;
      document.getElementById('repl-code').focus();
    } catch (err) {
      pyLoading = false;
      setStatus('⚠ Could not load Python — check your internet connection.');
      console.error('Pyodide load error:', err);
    }
  }

  // ── Run code ────────────────────────────────────────────────────────────
  async function runCode() {
    if (!pyReady) return;
    const codeEl = document.getElementById('repl-code');
    const outEl  = document.getElementById('repl-output');
    const runBtn = document.getElementById('repl-run');
    const code   = codeEl.value;
    if (!code.trim()) return;

    outEl.textContent = '';
    outEl.className   = '';
    runBtn.disabled   = true;

    let stdout = '';
    pyodide.setStdout({ batched: (s) => { stdout += s + '\n'; } });
    pyodide.setStderr({ batched: (s) => { stdout += s + '\n'; } });

    try {
      await pyodide.runPythonAsync(code);
      if (stdout.trim()) {
        outEl.textContent = stdout.trimEnd();
        outEl.className   = 'has-output repl-ok';
      }
    } catch (err) {
      outEl.textContent = friendlyError(err);
      outEl.className   = 'has-output repl-err';
    } finally {
      runBtn.disabled = false;
      codeEl.focus();
    }
  }

  // Strip Pyodide internal stack frames, keep only useful Python traceback.
  function friendlyError(err) {
    const msg    = err.message || String(err);
    const lines  = msg.split('\n');
    const filtered = lines.filter(l =>
      !l.includes('/lib/python') &&
      !l.includes('pyodide-') &&
      !l.trim().startsWith('at ')
    );
    return filtered.join('\n').trim();
  }

  // ── Reset simulation panels (called on Clear) ───────────────────────────
  function resetSim() {
    const songList  = document.getElementById('sim-songlist');
    const emptyHint = document.getElementById('sim-songlist-empty');
    const nowPlay   = document.getElementById('sim-nowplaying');
    const progress  = document.getElementById('sim-progress');
    const timestamp = document.getElementById('sim-timestamp');
    const lyrics    = document.getElementById('sim-lyrics');

    if (songList)  { while (songList.firstChild) songList.removeChild(songList.firstChild); }
    if (emptyHint) { emptyHint.style.display = 'block'; }
    if (nowPlay)   { nowPlay.textContent = 'Nothing playing'; nowPlay.className = 'repl-nowplaying-default'; }
    if (progress)  { progress.style.width = '0%'; }
    if (timestamp) { timestamp.textContent = '0:00'; }
    if (lyrics)    { lyrics.textContent = ''; }

    // Also reset Python-side state so add_track() doesn't re-append to old list
    if (pyReady) {
      pyodide.runPythonAsync(`
_tracks = []
_current_track = None
`).catch(() => {});
    }
  }

  // ── Panel open/close ────────────────────────────────────────────────────
  function openPanel() {
    panelOpen = true;
    document.getElementById('repl-panel').classList.add('repl-open');
    document.getElementById('repl-panel').setAttribute('aria-hidden', 'false');
    document.getElementById('repl-fab').classList.add('repl-fab-open');
    initPyodide();
  }

  function closePanel() {
    panelOpen = false;
    document.getElementById('repl-panel').classList.remove('repl-open');
    document.getElementById('repl-panel').setAttribute('aria-hidden', 'true');
    document.getElementById('repl-fab').classList.remove('repl-fab-open');
  }

  function setStatus(msg) {
    const el = document.getElementById('repl-status');
    if (el) el.textContent = msg;
  }

  // ── "Try it" buttons on code blocks ────────────────────────────────────
  // Targets all <pre><code> blocks; add data-norun to any that shouldn't run.
  function addTryButtons() {
    document.querySelectorAll('pre > code:not([data-norun])').forEach((codeEl) => {
      const pre = codeEl.parentElement;
      const btn = document.createElement('button');
      btn.className   = 'repl-try-btn';
      btn.textContent = '▶ Try it in Python';
      btn.title       = 'Copy this code to the Python playground and run it';
      btn.addEventListener('click', () => {
        // textContent strips all HTML span tags, giving clean Python source
        document.getElementById('repl-code').value = codeEl.textContent;
        // Clear output and reset sim panels
        const outEl = document.getElementById('repl-output');
        outEl.textContent = '';
        outEl.className   = '';
        resetSim();
        if (!panelOpen) openPanel();
        if (pyReady) runCode();
      });
      const wrap = document.createElement('div');
      wrap.className = 'repl-try-wrap';
      wrap.appendChild(btn);
      pre.insertAdjacentElement('afterend', wrap);
    });
  }

  // ── Wire up events ──────────────────────────────────────────────────────
  function wireEvents() {
    document.getElementById('repl-fab')
      .addEventListener('click', () => panelOpen ? closePanel() : openPanel());

    document.getElementById('repl-close')
      .addEventListener('click', closePanel);

    document.getElementById('repl-run')
      .addEventListener('click', runCode);

    document.getElementById('repl-clear')
      .addEventListener('click', () => {
        document.getElementById('repl-code').value = '';
        const outEl = document.getElementById('repl-output');
        outEl.textContent = '';
        outEl.className   = '';
        resetSim();
        setStatus(pyReady ? '' : 'Loading Python…');
        document.getElementById('repl-code').focus();
      });

    document.getElementById('repl-code')
      .addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
          e.preventDefault();
          runCode();
        }
        // Tab → 4 spaces
        if (e.key === 'Tab') {
          e.preventDefault();
          const ta    = e.target;
          const start = ta.selectionStart;
          const end   = ta.selectionEnd;
          ta.value = ta.value.substring(0, start) + '    ' + ta.value.substring(end);
          ta.selectionStart = ta.selectionEnd = start + 4;
        }
      });
  }

  // ── Kick off after DOM ready ────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    buildWidget();
    wireEvents();
    setTimeout(addTryButtons, 0);
  });

})();
