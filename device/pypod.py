# pypod.py — Teacher-written wrapper module for the pyPod CodeClub project
#
# This module hides all hardware and UI complexity (LVGL, audio driver, MicroPython
# timers, interrupt scheduling) behind a simple, English-like API.
#
# Students import from this module in their main.py and never need to see or
# understand the internals below.
#
# ── Public API summary ────────────────────────────────────────────
#
#  CLASS
#    Track(title, artist, file_path=None, lyrics=None)
#
#  SONG LIST
#    add_track(track)          — add a Track to the on-screen song list
#    clear_tracks()            — remove all tracks from the song list
#
#  FILE HELPERS
#    list_music_files()        — return list of .mp3 filenames from /sd/music/
#    music_path(filename)      — return full path for a music filename
#    lyrics_path(title)        — return full path for a lyrics file
#
#  PLAYBACK
#    play(track)               — start playing a Track
#    pause()                   — pause playback
#    resume()                  — resume after pause
#    next_track()              — skip to next track
#    previous_track()          — go back to previous track (or restart if > 3 s in)
#    set_volume(level)         — set volume 0–100
#    get_volume()              — return current volume (0–100)
#
#  STATE
#    is_playing()              — True if a track is currently playing
#    get_elapsed()             — seconds elapsed in the current track
#
#  UI UPDATES
#    show_progress(elapsed, total)  — update progress bar (seconds)
#    show_timestamp(elapsed)        — update the time label
#    show_lyrics(text)              — display text in the lyrics area
#    show_now_playing(track)        — update title and artist labels
#
#  CALLBACKS  (can also be used as decorators with @)
#    on_song_selected(fn)      — fn(track) called when user taps a song
#    on_track_ended(fn)        — fn()      called when a track finishes
#    on_tick(fn)               — fn(elapsed) called every 500 ms while playing
#
#  LIFECYCLE
#    start()                   — initialise hardware and start the app loop
#
# ─────────────────────────────────────────────────────────────────

import os, time
import micropython
from machine import Timer
import M5
from M5 import *
import m5ui
import lvgl as lv
import audio

# ── Internal constants ────────────────────────────────────────────
_MUSIC_DIR   = "/sd/music"
_LYRICS_DIR  = "/sd/transcripts"
_UPDATE_MS   = 500
_DEFAULT_VOL = 60

# ── Internal colour palette ───────────────────────────────────────
_BG                  = 0x121212
_SURFACE             = 0x1E1E2E
_ACCENT              = 0x89B4FA
_PURPLE              = 0xCBA6F7
_TEXT                = 0xCDD6F4
_LYRICS_BG           = 0x4D4D4D
_LYRICS_HIGHLIGHT    = 0xE0E0E0
_MEDIA_BTN_BG        = 0x4D6170
_MEDIA_BTN_HIGHLIGHT = 0x80AFB7
_VOLUME_BG           = 0xE7E3E7

# ── GC roots — LVGL objects must stay reachable ───────────────────
_pages     = []
_widgets   = []
_cbs       = []
_song_btns = []

# ── Widget references (populated by _build_ui) ────────────────────
_ui = {}

# ── Playback state ────────────────────────────────────────────────
_player         = None
_tracks_list    = []
_current_idx    = -1
_is_playing_val = False
_play_start_ms  = 0
_elapsed_offset = 0

# ── Student-registered callbacks ──────────────────────────────────
_on_song_selected_fn = None
_on_track_ended_fn   = None
_on_tick_fn          = None


# ══════════════════════════════════════════════════════════════════
#  Track — the student-facing data class
# ══════════════════════════════════════════════════════════════════

class Track:
    """Represents a single song.

    Arguments
    ---------
    title       — the song title (string)
    artist      — the artist name (string)
    file_path   — full path to the .mp3 file (optional)
    lyrics      — list of (seconds, lyric_text) pairs (optional)

    Examples
    --------
    track = Track("Wonderwall", "Oasis")
    track = Track("Never Gonna Give You Up", "Rick Astley",
                  file_path="/sd/music/Never Gonna Give You Up (Rick Astley).mp3")
    """
    def __init__(self, title="", artist="", file_path=None, lyrics=None):
        self.title     = title
        self.artist    = artist
        self.file_path = file_path
        self.lyrics    = lyrics   # list of (int_seconds, str), or None


# ══════════════════════════════════════════════════════════════════
#  Public API — Song list management
# ══════════════════════════════════════════════════════════════════

def add_track(track):
    """Add a Track to the song selection list on screen."""
    _tracks_list.append(track)
    _render_track_row(track, len(_tracks_list) - 1)


def clear_tracks():
    """Remove all tracks from the song list and the screen."""
    _tracks_list.clear()
    _song_btns.clear()
    # Rebuild the list widget in place
    song_list = _ui.get("list_widget")
    if song_list is not None:
        song_list.clean()


# ══════════════════════════════════════════════════════════════════
#  Public API — File helpers
# ══════════════════════════════════════════════════════════════════

def list_music_files():
    """Return a list of .mp3 filenames found in /sd/music/."""
    try:
        return sorted(f for f in os.listdir(_MUSIC_DIR) if f.lower().endswith(".mp3"))
    except Exception:
        return []


def music_path(filename):
    """Return the full file path for a music filename.

    Example: music_path("Wonderwall (Oasis).mp3")
             → "/sd/music/Wonderwall (Oasis).mp3"
    """
    return _MUSIC_DIR + "/" + filename


def lyrics_path(title):
    """Return the full file path for a lyrics file, given a track title.

    Example: lyrics_path("Wonderwall")
             → "/sd/transcripts/Wonderwall.txt"
    """
    return _LYRICS_DIR + "/" + title + ".txt"


# ══════════════════════════════════════════════════════════════════
#  Public API — Playback controls
# ══════════════════════════════════════════════════════════════════

def play(track):
    """Start playing a Track.

    Also switches the screen to the Now Playing page and resets the
    progress bar, timestamp, and lyrics display.
    """
    global _current_idx, _is_playing_val, _play_start_ms, _elapsed_offset
    if not track.file_path:
        return
    idx = _tracks_list.index(track) if track in _tracks_list else -1
    _current_idx    = idx
    _elapsed_offset = 0
    _play_start_ms  = time.ticks_ms()
    _is_playing_val = True
    _player.play("file://" + track.file_path)
    _show_now_playing_page(track)
    _update_play_btn()


def pause():
    """Pause the currently playing track."""
    global _is_playing_val, _elapsed_offset
    if _is_playing_val:
        _elapsed_offset = _elapsed_ms()
        _player.pause()
        _is_playing_val = False
        _update_play_btn()


def resume():
    """Resume a paused track."""
    global _is_playing_val, _play_start_ms
    if not _is_playing_val and _current_idx >= 0:
        _play_start_ms  = time.ticks_ms()
        _player.resume()
        _is_playing_val = True
        _update_play_btn()


def next_track():
    """Skip to the next track in the list."""
    if _tracks_list and _current_idx >= 0:
        play(_tracks_list[(_current_idx + 1) % len(_tracks_list)])


def previous_track():
    """Go back to the previous track.

    If more than 3 seconds have elapsed the current track restarts instead.
    """
    if not _tracks_list or _current_idx < 0:
        return
    if get_elapsed() > 3:
        play(_tracks_list[_current_idx])
    else:
        play(_tracks_list[(_current_idx - 1) % len(_tracks_list)])


def set_volume(level):
    """Set the playback volume. level should be between 0 and 100."""
    if _player:
        _player.set_vol(max(0, min(100, int(level))))


def get_volume():
    """Return the current volume level (0–100)."""
    return _player.get_vol() if _player else 0


# ══════════════════════════════════════════════════════════════════
#  Public API — State queries
# ══════════════════════════════════════════════════════════════════

def is_playing():
    """Return True if a track is currently playing."""
    return _is_playing_val


def get_elapsed():
    """Return the number of seconds elapsed in the current track."""
    return _elapsed_ms() // 1000


# ══════════════════════════════════════════════════════════════════
#  Public API — UI update helpers
# ══════════════════════════════════════════════════════════════════

def show_progress(elapsed, total):
    """Update the progress bar.

    elapsed — seconds played so far
    total   — total length of the track in seconds
    """
    bar = _ui.get("progress")
    if bar and total > 0:
        pct = int(elapsed * 100 / total)
        try:
            bar.set_value(min(pct, 100), False)
        except Exception:
            pass


def show_timestamp(elapsed):
    """Update the timestamp label with a formatted time string (m:ss)."""
    lbl = _ui.get("timestamp")
    if lbl:
        s = int(elapsed)
        lbl.set_text("{}:{:02d}".format(s // 60, s % 60))


def show_lyrics(text):
    """Display text in the lyrics area on the Now Playing page."""
    ta = _ui.get("lyrics")
    if ta:
        ta.set_text(str(text))


def show_now_playing(track):
    """Update the title and artist labels on the Now Playing page."""
    if "title"  in _ui: _ui["title"].set_text(track.title)
    if "artist" in _ui: _ui["artist"].set_text(track.artist or "")


# ══════════════════════════════════════════════════════════════════
#  Public API — Callback registration
# ══════════════════════════════════════════════════════════════════

def on_song_selected(fn):
    """Register a function to call when the user taps a song in the list.

    The function receives one argument: the Track that was selected.

    Can be used as a decorator:

        @on_song_selected
        def handle_selection(track):
            play(track)

    Or called directly:

        on_song_selected(handle_selection)
    """
    global _on_song_selected_fn
    _on_song_selected_fn = fn
    return fn


def on_track_ended(fn):
    """Register a function to call when the current track finishes.

    The function takes no arguments.

    Can be used as a decorator:

        @on_track_ended
        def handle_end():
            next_track()
    """
    global _on_track_ended_fn
    _on_track_ended_fn = fn
    return fn


def on_tick(fn):
    """Register a function to call every 500 ms while a track is playing.

    The function receives one argument: elapsed seconds (int).

    Can be used as a decorator:

        @on_tick
        def update_display(elapsed):
            show_timestamp(elapsed)
            show_progress(elapsed, 240)

    Registering a new on_tick handler replaces the previous one.
    """
    global _on_tick_fn
    _on_tick_fn = fn
    return fn


# ══════════════════════════════════════════════════════════════════
#  Public API — App lifecycle
# ══════════════════════════════════════════════════════════════════

def start():
    """Initialise the hardware, build the UI, and start the app.

    Call this once at the very end of main.py, after all tracks have been
    added and all callbacks registered.
    """
    global _player
    M5.begin()
    m5ui.init()
    _player = audio.Player(_on_player_state_cb)
    _player.set_vol(_DEFAULT_VOL)
    _build_ui()
    Timer(0).init(period=_UPDATE_MS, mode=Timer.PERIODIC, callback=_timer_cb)
    while True:
        M5.update()


# ══════════════════════════════════════════════════════════════════
#  Internal helpers  (not part of the student API)
# ══════════════════════════════════════════════════════════════════

def _elapsed_ms():
    if _is_playing_val:
        return _elapsed_offset + time.ticks_diff(time.ticks_ms(), _play_start_ms)
    return _elapsed_offset


def _update_play_btn():
    btn = _ui.get("play_btn")
    if btn:
        btn.set_text(lv.SYMBOL.PAUSE if _is_playing_val else lv.SYMBOL.PLAY)


def _show_now_playing_page(track):
    show_now_playing(track)
    show_lyrics("")
    show_timestamp(0)
    bar = _ui.get("progress")
    if bar:
        try: bar.set_value(0, False)
        except Exception: pass
    now_page = _ui.get("now_page")
    if now_page:
        now_page.screen_load()


def _on_player_state_cb(state):
    """Fired by audio.Player when playback state changes (state 0 = finished)."""
    if state == 0 and _is_playing_val and _on_track_ended_fn:
        _on_track_ended_fn()


def _timer_cb(t):
    """Hardware timer ISR — schedules tick onto the main thread."""
    if _is_playing_val:
        micropython.schedule(_tick, None)


def _tick(_arg):
    """Called on the main thread every UPDATE_MS while playing."""
    if _on_tick_fn:
        _on_tick_fn(get_elapsed())


# ── Internal LVGL event handler classes ──────────────────────────

class _SongRowHandler:
    def __init__(self, track):
        self._track = track

    def handler(self, e):
        if e.code == lv.EVENT.CLICKED and _on_song_selected_fn:
            _on_song_selected_fn(self._track)


class _BackHandler:
    def __init__(self, list_page_ref):
        self._ref = list_page_ref

    def handler(self, e):
        if e.code == lv.EVENT.CLICKED and self._ref[0]:
            self._ref[0].screen_load()


class _PlayBtnHandler:
    def handler(self, e):
        if e.code == lv.EVENT.CLICKED:
            if _is_playing_val:
                pause()
            else:
                resume()


class _NextBtnHandler:
    def handler(self, e):
        if e.code == lv.EVENT.CLICKED:
            next_track()


class _PrevBtnHandler:
    def handler(self, e):
        if e.code == lv.EVENT.CLICKED:
            previous_track()


class _VolumeHandler:
    def __init__(self, arc):
        self._arc = arc

    def handler(self, e):
        if e.code == lv.EVENT.VALUE_CHANGED:
            set_volume(self._arc.get_value() * 2)


# ── UI construction ───────────────────────────────────────────────

def _build_ui():
    """Build both pages. Called once from start()."""
    list_page_ref = [None]

    # ── Now Playing page ──────────────────────────────────────────
    now_page = m5ui.M5Page(bg_c=_BG)
    _ui["now_page"] = now_page
    _pages.append(now_page)

    back_btn = m5ui.M5Button(lv.SYMBOL.LIST, x=3, y=8, bg_c=_BG, text_c=_ACCENT,
                              font=lv.font_montserrat_24, parent=now_page)
    back_btn.set_style_shadow_opa(0, lv.PART.MAIN)
    _widgets.append(back_btn)

    title_lbl = m5ui.M5Label("Select a track", x=53, y=9, text_c=_TEXT, bg_c=_BG,
                               bg_opa=0, font=lv.font_montserrat_24, parent=now_page)
    title_lbl.set_width(200)
    title_lbl.set_height(25)
    title_lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    _widgets.append(title_lbl)
    _ui["title"] = title_lbl

    artist_lbl = m5ui.M5Label("", x=53, y=35, text_c=_TEXT, bg_c=_BG, bg_opa=0,
                                font=lv.font_montserrat_14, parent=now_page)
    artist_lbl.set_width(200)
    artist_lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    _widgets.append(artist_lbl)
    _ui["artist"] = artist_lbl

    lyrics_ta = m5ui.M5TextArea(text="", placeholder="No lyrics", x=10, y=66,
                                 w=300, h=100, font=lv.font_montserrat_12,
                                 bg_c=_LYRICS_BG, border_c=_LYRICS_HIGHLIGHT,
                                 text_c=0xffffff, parent=now_page)
    lyrics_ta.get_label().set_long_mode(lv.label.LONG_MODE.WRAP)
    _widgets.append(lyrics_ta)
    _ui["lyrics"] = lyrics_ta

    progress_bar = m5ui.M5Bar(x=10, y=173, w=300, h=15, min_value=0, max_value=100,
                               value=0, bg_c=0x8CBEE8, color=0x2193F3, parent=now_page)
    _widgets.append(progress_bar)
    _ui["progress"] = progress_bar

    timestamp_lbl = m5ui.M5Label("0:00", x=10, y=194, text_c=0xffffff, bg_c=_BG,
                                  bg_opa=0, font=lv.font_montserrat_14, parent=now_page)
    _widgets.append(timestamp_lbl)
    _ui["timestamp"] = timestamp_lbl

    play_btn = m5ui.M5Button(lv.SYMBOL.PLAY, x=137, y=194, bg_c=_MEDIA_BTN_BG,
                              text_c=_MEDIA_BTN_HIGHLIGHT, font=lv.font_montserrat_18,
                              parent=now_page)
    play_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(play_btn)
    _ui["play_btn"] = play_btn

    next_btn = m5ui.M5Button(lv.SYMBOL.NEXT, x=191, y=194, bg_c=_MEDIA_BTN_BG,
                              text_c=_MEDIA_BTN_HIGHLIGHT, font=lv.font_montserrat_18,
                              parent=now_page)
    next_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(next_btn)

    prev_btn = m5ui.M5Button(lv.SYMBOL.PREV, x=83, y=194, bg_c=_MEDIA_BTN_BG,
                              text_c=_MEDIA_BTN_HIGHLIGHT, font=lv.font_montserrat_18,
                              parent=now_page)
    prev_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(prev_btn)

    vol_arc = m5ui.M5Arc(x=255, y=6, w=60, h=60, value=_DEFAULT_VOL // 2,
                          min_value=0, max_value=50, rotation=0,
                          mode=lv.arc.MODE.NORMAL, bg_c=_VOLUME_BG,
                          bg_c_indicator=_PURPLE, bg_c_knob=_PURPLE, parent=now_page)
    _widgets.append(vol_arc)

    spk_lbl = m5ui.M5Label(lv.SYMBOL.VOLUME_MAX, x=275, y=26, text_c=0xECECEC,
                             bg_c=0xffffff, bg_opa=0, font=lv.font_montserrat_18,
                             parent=now_page)
    _widgets.append(spk_lbl)

    # Wire up internal Now Playing handlers
    bh = _BackHandler(list_page_ref); _cbs.append(bh)
    back_btn.add_event_cb(bh.handler, lv.EVENT.ALL, None)

    ph = _PlayBtnHandler(); _cbs.append(ph)
    play_btn.add_event_cb(ph.handler, lv.EVENT.ALL, None)

    nh = _NextBtnHandler(); _cbs.append(nh)
    next_btn.add_event_cb(nh.handler, lv.EVENT.ALL, None)

    pvh = _PrevBtnHandler(); _cbs.append(pvh)
    prev_btn.add_event_cb(pvh.handler, lv.EVENT.ALL, None)

    vh = _VolumeHandler(vol_arc); _cbs.append(vh)
    vol_arc.add_event_cb(vh.handler, lv.EVENT.ALL, None)

    # ── Song List page ────────────────────────────────────────────
    list_page = m5ui.M5Page(bg_c=_BG)
    _ui["list_page"] = list_page
    _pages.append(list_page)
    list_page_ref[0] = list_page

    hdr = m5ui.M5Label(lv.SYMBOL.GPS + " pyPod", x=5, y=7, text_c=0xFFFFFF,
                        bg_c=_BG, bg_opa=255, font=lv.font_montserrat_24,
                        parent=list_page)
    hdr.set_width(315)
    hdr.set_height(36)
    _widgets.append(hdr)

    song_list = m5ui.M5List(x=0, y=38, w=320, h=202, parent=list_page)
    _widgets.append(song_list)
    _ui["list_widget"] = song_list

    list_page.screen_load()


def _render_track_row(track, idx):
    """Add a single row to the song list widget for the given track."""
    song_list = _ui.get("list_widget")
    if song_list is None:
        return
    label = track.title
    if track.artist:
        label += "  —  " + track.artist
    btn = song_list.add_button(
        lv.SYMBOL.AUDIO, label, h=46,
        bg_c=_SURFACE, bg_opa=255,
        text_c=_TEXT, text_opa=255,
        font=lv.font_montserrat_14,
    )
    _song_btns.append(btn)
    h = _SongRowHandler(track)
    _cbs.append(h)
    btn.add_event_cb(h.handler, lv.EVENT.ALL, None)
