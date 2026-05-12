# main.py — pyPod student code
#
# This is what a student's main.py looks like after completing all 6 lessons.
# All hardware and UI complexity lives in pypod.py (the teacher-written wrapper).

import os
from pypod import (
    Track,
    add_track,
    play, pause, resume, next_track, previous_track,
    set_volume,
    is_playing, get_elapsed,
    show_progress, show_timestamp, show_lyrics,
    on_song_selected, on_track_ended, on_tick,
    list_music_files, music_path, lyrics_path,
    start,
)


# ── Lesson 3: Load timestamped lyrics from a .txt file ────────────
# Each line in the file looks like:   1:19    lyric text here
# We split each line into a timestamp and the lyric, then convert
# the timestamp into a number of seconds.

def load_lyrics(path):
    entries = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split(None, 1)   # split on first whitespace
                if len(parts) == 2:
                    minutes, seconds = parts[0].split(":")
                    timestamp = int(minutes) * 60 + int(seconds)
                    entries.append((timestamp, parts[1]))
    except Exception:
        pass
    return entries


# ── Lesson 2: Scan the SD card and build a list of Track objects ──
# Filenames are formatted as "Song Title (Artist).mp3"
# We need to pull apart the filename to get the title and artist separately.

def parse_filename(filename):
    """Given a filename like 'Wonderwall (Oasis).mp3', return ('Wonderwall', 'Oasis')."""
    stem       = filename[:-4]          # remove .mp3
    paren      = stem.rfind("(")
    title      = stem[:paren].strip()
    artist     = stem[paren + 1:-1].strip()
    return title, artist


tracks = []

for filename in list_music_files():
    title, artist = parse_filename(filename)
    track = Track(
        title     = title,
        artist    = artist,
        file_path = music_path(filename),
        lyrics    = load_lyrics(lyrics_path(title)),
    )
    tracks.append(track)
    add_track(track)


# ── Lesson 4: Wire up the media controls ─────────────────────────
# A callback is a function that gets called automatically when something
# happens — in this case, when the user taps a song in the list.

current_track = None

@on_song_selected
def handle_selection(track):
    global current_track
    current_track = track
    play(track)

@on_track_ended
def handle_end():
    next_track()


# ── Lessons 5 & 6: Update the display every half-second ──────────
# on_tick calls this function automatically while a song is playing.
# We update the progress bar, the timestamp, and the synced lyrics.

LOOKAHEAD = 2   # show a lyric this many seconds before it is sung

def get_current_lyric(lyrics, elapsed):
    """Find the lyric line that should be showing at 'elapsed' seconds."""
    current_lyric = ""
    for timestamp, text in lyrics:
        if timestamp <= elapsed + LOOKAHEAD:
            current_lyric = text
    return current_lyric

@on_tick
def update_display(elapsed):
    show_timestamp(elapsed)

    if current_track is not None:
        # We don't know the exact track length, so we use a safe upper bound
        # The progress bar will simply stop advancing once the song ends
        show_progress(elapsed, 400)

        if current_track.lyrics:
            show_lyrics(get_current_lyric(current_track.lyrics, elapsed))


# ── Start the app ─────────────────────────────────────────────────
# This must always be the last line in main.py

start()
