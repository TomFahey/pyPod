# pyPod — M5Stack Core S3 / UIFlow2 MicroPython
#
# Two pages
# ---------
#   Song List   — scrollable list of songs scanned from SD card
#   Now Playing — time-synced lyrics + playback controls
#
# Navigation
# ----------
#   Tap a song  →  Now Playing page  (starts playback)
#   Tap "Back"  →  Song List page    (pauses playback)

import os, sys, io, time
import M5
from M5 import *
import m5ui
import lvgl as lv
import audio

# ── Constants ─────────────────────────────────────────────────────
MUSIC_DIR       = "/sd/music"
LYRICS_DIR      = "/sd/transcripts"
LYRIC_LOOKAHEAD = 2      # show a lyric this many seconds before its timestamp
LYRIC_LINES     = 5      # number of lyric lines visible at once
UPDATE_MS       = 500    # how often the playback UI refreshes (ms)
DEFAULT_VOL     = 60     # startup volume (0–100); arc init value = DEFAULT_VOL // 2
MAX_VOLUME      = 50     # Soft cap on volume

# ── Colour palette ────────────────────────────────────────────────
BG                  = 0x121212
SURFACE             = 0x1E1E2E
ACCENT              = 0x89B4FA
PURPLE              = 0xCBA6F7
TEXT                = 0xCDD6F4
DIM                 = 0x6C7086
LYRICS_BG           = 0x4D4D4D
LYRICS_HIGHLIGHT    = 0xE0E0E0
MEDIA_BTN_BG        = 0x4D6170
MEDIA_BTN_HIGHLIGHT = 0x80AFB7
VOLUME_BG           = 0xE7E3E7
SPEAKER_ICON_COLOR  = 0xECECEC

# ── Custom Font ───────────────────────────────────────────────────
#custom_font = lv.binfont_create("S:/flash/res/font/CustomFont-20px.bin")

# ── Icon Unicode Values ───────────────────────────────────────────
play_icon           = "\uF04B"
pause_icon          = "\uF04C"
stop_icon           = "\uF04D"
next_song_icon      = "\uF050"
previous_song_icon  = "\uF049"
back_circle_icon    = "\uF137"
home_icon           = "\uF015"
settings_icon       = "\uF013"
speaker_icon        = "\uF028"

# ── GC root lists — LVGL objects must be reachable to survive GC ──
_pages     = []
_widgets   = []
_callbacks = []
_song_btns = []

# ── Widget references populated during build; used by loop & handlers ──
_ui = {}

# ── Playback state ────────────────────────────────────────────────
_player         = None   # audio.Player instance
_tracks         = []     # list of Track objects from SD card
_current_idx    = -1     # index of currently selected / playing track
_is_playing     = False
_play_start_ms  = 0      # ticks_ms when last play/resume began
_elapsed_offset = 0      # ms accumulated before current play session
_last_update_ms = 0      # ticks_ms of last UI refresh (for throttling)
_volume         = DEFAULT_VOL


# ══════════════════════════════════════════════════════════════════
#  Track — represents one MP3 file on the SD card
# ══════════════════════════════════════════════════════════════════
class Track:
    def __init__(self, title, artist, audio_path, lyrics_path):
        self.title       = title
        self.artist      = artist
        self.audio_path  = audio_path
        self.lyrics_path = lyrics_path
        self._lyrics     = None   # lazy-loaded: list of (int_seconds, str)

    @property
    def lyrics(self):
        if self._lyrics is None:
            self._lyrics = _load_lyrics(self.lyrics_path)
        return self._lyrics


# ── SD card scanning ──────────────────────────────────────────────
def scan_tracks():
    """Read /sd/music/, parse filenames 'Song Title (Artist).mp3' → Track list."""
    result = []
    try:
        for fname in sorted(os.listdir(MUSIC_DIR)):
            if not fname.lower().endswith(".mp3"):
                continue
            stem = fname[:-4]   # strip .mp3
            if "(" in stem and stem.endswith(")"):
                paren  = stem.rfind("(")
                title  = stem[:paren].strip()
                artist = stem[paren + 1:-1].strip()
            else:
                title  = stem
                artist = ""
            result.append(Track(
                title,
                artist,
                MUSIC_DIR  + "/" + fname,
                LYRICS_DIR + "/" + title + ".txt",
            ))
    except Exception as ex:
        print("scan_tracks:", ex)
    return result


# ── Lyric file loading ────────────────────────────────────────────
def _load_lyrics(path):
    """Parse a timestamped lyrics file.

    Each non-blank line should look like:
        m:ss    lyric text
    Returns a list of (seconds: int, text: str) sorted by time.
    """
    entries = []
    try:
        with open(path, "r") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                parts = raw.split(None, 1)   # split on first whitespace (tab or spaces)
                if len(parts) < 2:
                    continue
                ts, text = parts
                if ":" in ts:
                    try:
                        m, s   = ts.split(":", 1)
                        entries.append((int(m) * 60 + int(s), text))
                    except Exception:
                        pass
    except Exception:
        pass
    return entries


# ── Elapsed time helpers ──────────────────────────────────────────
def _elapsed_ms():
    if _is_playing:
        return _elapsed_offset + time.ticks_diff(time.ticks_ms(), _play_start_ms)
    return _elapsed_offset

def _elapsed_sec():
    return _elapsed_ms() // 1000

def _fmt_time(secs):
    s = int(secs)
    return "{}:{:02d}".format(s // 60, s % 60)


# ── Audio player state callback ───────────────────────────────────
def _on_player_state(state):
    """Fired by audio.Player when playback state changes.
    A state value of 0 means idle/stopped in UIFlow2 — treat as track-end."""
    if state == 0 and _is_playing:
        _next_track()


# ── Playback control ──────────────────────────────────────────────
def play_track(idx):
    """Start playing the track at position idx in _tracks."""
    global _current_idx, _is_playing, _play_start_ms, _elapsed_offset
    if not _tracks:
        return
    idx = idx % len(_tracks)
    track = _tracks[idx]
    if not track.audio_path:
        return
    _current_idx    = idx
    _elapsed_offset = 0
    _play_start_ms  = time.ticks_ms()
    _is_playing     = True
    _player.play("file:/" + track.audio_path, pos=0, volume=_volume, sync=False)
    _refresh_now_playing(track)
    _update_play_btn()


def toggle_play():
    """Toggle between play and pause for the current track."""
    global _is_playing, _play_start_ms, _elapsed_offset
    if _current_idx < 0:
        return
    if _is_playing:
        _elapsed_offset = _elapsed_ms()
        _player.pause()
        _is_playing = False
    else:
        _play_start_ms = time.ticks_ms()
        _player.resume()
        _is_playing = True
    _update_play_btn()


def _next_track():
    if _tracks:
        play_track((_current_idx + 1) % len(_tracks))


def _prev_track():
    if _tracks:
        if _elapsed_sec() > 3:
            play_track(_current_idx)   # restart if more than 3 s in
        else:
            play_track((_current_idx - 1) % len(_tracks))


def set_volume(arc_val):
    global _volume
    """Map the arc value (0–50) to audio player volume (0–100)."""
    if _player:
        _volume = min(arc_val, MAX_VOLUME)  
        _player.set_vol(_volume)


# ── UI refresh helpers ────────────────────────────────────────────
def _update_play_btn():
    btn = _ui.get("play_btn")
    if btn:
        btn.set_btn_text(lv.SYMBOL.PAUSE if _is_playing else lv.SYMBOL.PLAY)


def _refresh_now_playing(track):
    """Update title/artist/lyrics display when a new track starts."""
    if "title"    in _ui: _ui["title"].set_text(track.title)
    if "artist"   in _ui: _ui["artist"].set_text(track.artist if track.artist else "")
    if "lyrics"   in _ui: _ui["lyrics"].set_text("")
    if "timestamp" in _ui: _ui["timestamp"].set_text("0:00")
    if "progress" in _ui:
        try:
            _ui["progress"].set_value(0, False)
        except Exception:
            pass


def _get_lyric_text(lyrics, secs):
    """Return LYRIC_LINES lines of lyrics for the current playback position.

    Lines are shown LYRIC_LOOKAHEAD seconds before their timestamp so the
    viewer can read them just before they are sung.
    """
    if not lyrics:
        return ""
    look    = secs + LYRIC_LOOKAHEAD
    current = -1
    for i, (ts, _) in enumerate(lyrics):
        if ts <= look:
            current = i
        else:
            break
    window = lyrics[current : current + LYRIC_LINES] if current >= 0 else lyrics[:LYRIC_LINES]
    return "\n".join(text for _, text in window)


def _update_playback_ui():
    """Throttled refresh called from loop(); updates progress bar, timestamp, lyrics."""
    global _last_update_ms
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_update_ms) < UPDATE_MS:
        return
    _last_update_ms = now

    if _current_idx < 0:
        return
    track = _tracks[_current_idx]
    secs  = _elapsed_sec()

    if "timestamp" in _ui:
        _ui["timestamp"].set_text(_fmt_time(secs))

    if "progress" in _ui and _is_playing:
        try:
            # Progress bar max_value=400 s; use elapsed seconds directly
            _ui["progress"].set_value(int(secs), False)
        except Exception:
            pass

    if "lyrics" in _ui and _is_playing:
        _ui["lyrics"].set_text(_get_lyric_text(track.lyrics, secs))


# ══════════════════════════════════════════════════════════════════
#  Handler classes — instances stored in _callbacks to survive GC
# ══════════════════════════════════════════════════════════════════

class SongHandler:
    """Handles a tap on a song-list row; captures the track index safely."""
    def __init__(self, idx, now_page):
        self._idx      = idx
        self._now_page = now_page

    def handler(self, e):
        if e.code == lv.EVENT.CLICKED:
            play_track(self._idx)
            self._now_page.screen_load()


class BackHandler:
    def __init__(self, list_page_ref):
        self._ref = list_page_ref   # mutable container filled after both pages are built

    def handler(self, e):
        if e.code == lv.EVENT.CLICKED and self._ref[0] is not None:
            self._ref[0].screen_load()


class VolumeHandler:
    def __init__(self, arc):
        self._arc = arc

    def handler(self, e):
        if e.code == lv.EVENT.VALUE_CHANGED:
            set_volume(self._arc.get_value())


class MediaBtnHandler:
    """Generic handler that calls a no-arg action on click."""
    def __init__(self, action):
        self._action = action

    def handler(self, e):
        if e.code == lv.EVENT.CLICKED:
            self._action()


# ══════════════════════════════════════════════════════════════════
#  PAGE: Now Playing
#
#  Layout (320 × 240)
#  ┌──────────────────────────────────┐  y 0
#  │  (<) Speed of Sound        (spk) │   
#  |      Coldplay                    |
#  |  ─────────────────────────────   |
#  │  |Look up, I look up at night|   │
#  │  |Planets are moving at the  |   │  
#  │  |speed of light             |   │
#  │  ─────────────────────────────   |
#  │   ───●                           │  
#  |   0:12  [|<<] [||] [>>|]         |
#  └──────────────────────────────────┘  y 240
# ══════════════════════════════════════════════════════════════════
def _build_now_playing(list_page_ref):
    global _ui
    page = m5ui.M5Page(bg_c=BG)
    
    # Back button
    back_btn = m5ui.M5Button(
        text=lv.SYMBOL.LIST, 
        x=3, y=8, 
        bg_c=BG, 
        text_c=ACCENT, 
        font=lv.font_montserrat_24, 
        parent=page)
    back_btn.set_style_shadow_opa(0, lv.PART.MAIN)
    _widgets.append(back_btn)
    
    # Song title — truncated with dots if too long
    title_lbl = m5ui.M5Label(
        "Select a track", 
        x=53, y=9, 
        text_c=TEXT, 
        bg_c=BG, 
        bg_opa=0, 
        font=lv.font_montserrat_24, 
        parent=page)
    title_lbl.set_width(200)
    title_lbl.set_height(25)
    title_lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    _widgets.append(title_lbl)
    
    # Artist label
    artist_lbl = m5ui.M5Label(
        "", 
        x=53, y=35, 
        text_c=TEXT, 
        bg_c=BG, 
        bg_opa=0, 
        font=lv.font_montserrat_14, 
        parent=page)
    artist_lbl.set_width(200)
    artist_lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    _widgets.append(artist_lbl)
    
    # Lyric text area
    lyrics_text_area = m5ui.M5TextArea(
        text="", 
        placeholder="No lyrics found", 
        x=10, y=66, 
        w=300, h=100, 
        font=lv.font_montserrat_12, 
        bg_c=LYRICS_BG, 
        border_c=LYRICS_HIGHLIGHT, 
        text_c=0xffffff, 
        parent=page
    )
    lyrics_lbl = lyrics_text_area.get_label()
    lyrics_lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
    _widgets.append(lyrics_text_area)
    
    ## Media Controls
    # Play / Pause button — starts as PLAY since nothing is playing yet
    play_btn = m5ui.M5Button(
        lv.SYMBOL.PLAY,
        x=137, y=194, 
        bg_c=MEDIA_BTN_BG, 
        text_c=MEDIA_BTN_HIGHLIGHT, 
        font=lv.font_montserrat_18, 
        parent=page
    )
    play_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(play_btn)

    # Next Track button
    next_track_btn = m5ui.M5Button(
        lv.SYMBOL.NEXT,
        x=191, y=194, 
        bg_c=MEDIA_BTN_BG, 
        text_c=MEDIA_BTN_HIGHLIGHT, 
        font=lv.font_montserrat_18, 
        parent=page
    )
    next_track_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(next_track_btn)

    # Previous Track button
    previous_track_btn = m5ui.M5Button(
        lv.SYMBOL.PREV,
        x=83, y=194, 
        bg_c=MEDIA_BTN_BG, 
        text_c=MEDIA_BTN_HIGHLIGHT, 
        font=lv.font_montserrat_18, 
        parent=page
    )
    previous_track_btn.set_style_radius(20, lv.PART.MAIN)
    _widgets.append(previous_track_btn)
    
    ## Volume control
    # Arc range 0–50; mapped to audio volume 0–100 in set_volume()
    volume_arc = m5ui.M5Arc(
        x=255, y=6, 
        w=60, h=60, 
        value=DEFAULT_VOL // 2, 
        min_value=0, 
        max_value=100, 
        rotation=0, 
        mode=lv.arc.MODE.NORMAL, 
        bg_c=VOLUME_BG, 
        bg_c_indicator=PURPLE, 
        bg_c_knob=PURPLE, 
        parent=page
    )
    _widgets.append(volume_arc)

    # Speaker icon (sits inside the arc)
    speaker_lbl = m5ui.M5Label(
        lv.SYMBOL.VOLUME_MAX,
        x=275, y=26, 
        text_c=SPEAKER_ICON_COLOR, 
        bg_c=0xffffff, 
        bg_opa=0, 
        font=lv.font_montserrat_18, 
        parent=page
    )
    _widgets.append(speaker_lbl)
    
    ## Progress widgets
    # Progress bar — max_value=400 treats bar range as 0–400 seconds (~6.7 min)
    progress_bar = m5ui.M5Bar(
        x=10, y=173, 
        w=300, h=15, 
        min_value=0, 
        max_value=400, 
        value=0, 
        bg_c=0x8CBEE8, 
        color=0x2193F3, 
        parent=page
    )
    _widgets.append(progress_bar)

    # Timestamp label
    timestamp_lbl = m5ui.M5Label(
        "0:00", 
        x=10, y=194, 
        text_c=0xffffff, 
        bg_c=BG, 
        bg_opa=0, 
        font=lv.font_montserrat_14, 
        parent=page
    )
    _widgets.append(timestamp_lbl)
    
    # ── Store widget references used by playback helpers ──────────
    _ui["title"]     = title_lbl
    _ui["artist"]    = artist_lbl
    _ui["lyrics"]    = lyrics_text_area   # set_text() updates the displayed text
    _ui["play_btn"]  = play_btn
    _ui["progress"]  = progress_bar
    _ui["timestamp"] = timestamp_lbl

    # ── Event handlers ────────────────────────────────────────────
    back_h = BackHandler(list_page_ref)
    _callbacks.append(back_h)
    back_btn.add_event_cb(back_h.handler, lv.EVENT.ALL, None)

    play_h = MediaBtnHandler(toggle_play)
    _callbacks.append(play_h)
    play_btn.add_event_cb(play_h.handler, lv.EVENT.ALL, None)

    next_h = MediaBtnHandler(_next_track)
    _callbacks.append(next_h)
    next_track_btn.add_event_cb(next_h.handler, lv.EVENT.ALL, None)

    prev_h = MediaBtnHandler(_prev_track)
    _callbacks.append(prev_h)
    previous_track_btn.add_event_cb(prev_h.handler, lv.EVENT.ALL, None)

    vol_h = VolumeHandler(volume_arc)
    _callbacks.append(vol_h)
    volume_arc.add_event_cb(vol_h.handler, lv.EVENT.ALL, None)
    
    _pages.append(page)
    return page


# ══════════════════════════════════════════════════════════════════
#  PAGE: Song List
#
#  Layout (320 × 240)
#  ┌──────────────────────────────────┐  y 0
#  │  pyPod                          │  y 0–36   header bar
#  ├──────────────────────────────────┤  y 36
#  │  The Speed of Sound             │  ┐
#  │  Viva la Vida                   │  │  scrollable list
#  │  Yellow                         │  │  ~46 px per item
#  │  The Scientist                  │  │
#  │  ...                            │  ┘
#  └──────────────────────────────────┘  y 240
# ══════════════════════════════════════════════════════════════════
def _build_song_list(now_page):
    page = m5ui.M5Page(bg_c=BG)

    # Icon
    icon_lbl = m5ui.M5Label(
        lv.SYMBOL.GPS + " pyPod",
        x=5, y=7,
        text_c=0xFFFFFF,
        bg_c=BG,
        bg_opa=255,
        font=lv.font_montserrat_24,
        parent=page,
    )
    icon_lbl.set_width(315)
    icon_lbl.set_height(36)
    _widgets.append(icon_lbl)
    
    # Scrollable song list
    song_list = m5ui.M5List(x=0, y=38, w=320, h=202, parent=page)
    _widgets.append(song_list)

    tracks_to_show = _tracks if _tracks else [Track("No songs found", "", "", "")]
    for idx, track in enumerate(tracks_to_show):
        label = track.title
        if track.artist:
            label += "  —  " + track.artist
        btn = song_list.add_button(
            lv.SYMBOL.AUDIO,
            label,
            h=46,
            bg_c=SURFACE,
            bg_opa=255,
            text_c=TEXT,
            text_opa=255,
            font=lv.font_montserrat_14,
        )
        _song_btns.append(btn)

        if track.audio_path:
            h = SongHandler(idx, now_page)
            _callbacks.append(h)
            btn.add_event_cb(h.handler, lv.EVENT.ALL, None)

    _pages.append(page)
    return page


# ── Setup ─────────────────────────────────────────────────────────
def setup():
    global _player, _tracks
    M5.begin()
    m5ui.init()

    # Initialise audio player; state callback auto-advances on track end
    _player = audio.Player(_on_player_state)
    _player.set_vol(DEFAULT_VOL)

    # Scan SD card for MP3 files
    _tracks = scan_tracks()

    # Build Now Playing first; back button references list page via mutable container
    list_page_ref = [None]
    now_page = _build_now_playing(list_page_ref)

    # Build Song List and complete the circular reference
    list_page = _build_song_list(now_page)
    list_page_ref[0] = list_page

    list_page.screen_load()


def loop():
    M5.update()
    _update_playback_ui()


if __name__ == "__main__":
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            m5ui.deinit()
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
