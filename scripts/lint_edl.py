#!/usr/bin/env python3
"""Check every in/out point of edl.json against the source audio BEFORE assembling (no render, seconds to run).

Usage:  PY lint_edl.py <project_dir> [--fix]
Reads each source's audio (work/<clip>.wav from islands.py, else extracts it) and, when present,
work/words_<clip>_islands.json for word names in the notes.
Rule (local patch, tuned on a real reel): a cut must sit in a pause or in the dip between two words, at least 10 dB
under the median of the clip's speech frames. OK / CHECK (dip within 60 ms, move the point there) / UNSAFE (out-point with no dip: chops a sound; an in-point
with no dip is only CHECK, tuned by ear).
--fix moves every CHECK edge that has a dip within 60 ms onto that dip and rewrites edl.json (the old one is kept as
work/edl_before_fix.json); UNSAFE edges and in-points that start on sound are left for the user.
Exit code 1 when any edge is UNSAFE. assemble.py already puts a 20/30 ms audio fade on every join.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402


MIN_SEG = 0.3   # --fix never makes a segment shorter than this (seconds)


def load(p):
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def energy(proj, clip, src):
    """10 ms loudness (dB) of a source clip, from work/<clip>.wav (made by islands.py, else extracted here)."""
    import wave
    import numpy as np
    wav = os.path.join(proj, 'work', f'{clip}.wav')
    if not os.path.exists(wav):
        subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
    with wave.open(wav) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = len(a) // 160
    return 20 * np.log10(np.sqrt(np.mean(a[:n * 160].reshape(n, 160) ** 2, axis=1) + 1e-12))


def dip_level(db):
    """dB under which a frame counts as a pause / word gap: 10 dB under the median of the SPEECH frames (frames 10 dB+
    over the room floor). A median over the whole clip measures the silence when pauses fill more than half of it."""
    import numpy as np
    floor = float(np.percentile(db, 10))
    talk = db[db > floor + 10]
    if len(talk) < max(10, len(db) // 20):     # (almost) no speech: anything near the floor is a pause
        return floor + 6
    return max(float(np.median(talk)) - 10, floor + 6)


def edge(t, db, gap, words, side):
    """OK = the cut sits in a pause or the dip between two words; CHECK = a dip is within 60 ms (move the cut there);
    UNSAFE = no dip near: the cut chops a sound. Measured on the test reel: approved cuts sit 10-20 dB under the speech
    median, a fast talker rarely leaves 0.4s pauses, so 'only cut in long silences' would flag almost every cut."""
    move = None
    k = min(int(round(t * 100)), len(db) - 1)
    win = db[max(k - 6, 0):k + 7]
    j = int(win.argmin()) + max(k - 6, 0)
    if db[k] <= gap:
        level, notes = 'OK', [f'{db[k]:.0f} dB at the cut (dip)']
    elif db[j] <= gap:
        level, notes = 'CHECK', [f'{db[k]:.0f} dB at the cut, dip at {j / 100:.2f} ({(j - k) * 10:+d} ms): move it there']
        move = j / 100
    elif side == 'in':
        # tuned by ear on the test reel: an in-point that starts on sound sounded perfect (the 20 ms fade-in hides it,
        # nothing before the cut is heard), an out-point with no dip was audibly clipped ("wilt," -> cta, 2026-10-12)
        level, notes = 'CHECK', [f'{db[k]:.0f} dB at the cut: starts on sound, fine when the first word is whole']
    else:
        level, notes = 'UNSAFE', [f'{db[k]:.0f} dB at the cut and no dip within 60 ms: it chops the sound, move it']
    inside = next((w for w in words if w['start'] + 0.03 < t < w['end'] - 0.03), None)
    if inside:
        notes.append(f'whisper puts it inside "{inside["text"]}" (word times can be ~0.5s off)')
    if side == 'in':
        nxt = next((w for w in words if w['start'] >= t - 0.02), None)
        if nxt and nxt['start'] - t > 0.25:
            notes.append(f'{(nxt["start"] - t) * 1000:.0f} ms of air before "{nxt["text"]}"')
    else:
        prv = next((w for w in reversed(words) if w['end'] <= t + 0.02), None)
        if prv and t - prv['end'] > 0.3:
            notes.append(f'{(t - prv["end"]) * 1000:.0f} ms of air after "{prv["text"]}"')
    return level, '; '.join(notes), move


def main():
    skillenv.utf8_stdio()
    proj = skillenv.path_arg(sys.argv[1])
    work = os.path.join(proj, 'work')
    edl = load(os.path.join(proj, 'edl.json'))
    import numpy as np
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        src = json.load(fh)
    fix = '--fix' in sys.argv
    bad, cache, moved = 0, {}, []
    for n, s in enumerate(edl):
        c = s['clip']
        if c not in cache:
            db = energy(proj, c, src[c])
            wp = os.path.join(work, f'words_{c}_islands.json')
            cache[c] = (db, dip_level(db), load(wp) if os.path.exists(wp) else [])
        db, gap, words = cache[c]
        for side, t in (('in', s['in']), ('out', s['out'])):
            level, why, move = edge(t, db, gap, words, side)
            bad += level == 'UNSAFE'
            print(f"{level:6s} {s['id']:10s} {side:3s} {t:7.2f}  {why}")
            if fix and move is not None:
                # never let a move overlap the neighbouring segment of the same clip (that would play audio twice)
                prv = edl[n - 1] if n and edl[n - 1]['clip'] == c else None
                nxt = edl[n + 1] if n + 1 < len(edl) and edl[n + 1]['clip'] == c else None
                if side == 'in' and prv and prv['out'] <= t + 0.001 and move < prv['out']:
                    print(f"       {s['id']:10s} in  not moved: would overlap the end of {prv['id']}")
                elif side == 'out' and nxt and nxt['in'] >= t - 0.001 and move > nxt['in']:
                    print(f"       {s['id']:10s} out not moved: would overlap the start of {nxt['id']}")
                elif (s['out'] - move if side == 'in' else move - s['in']) < MIN_SEG:
                    # both edges of a short segment can find the same dip; keep it long enough for assemble.py's fades
                    print(f"       {s['id']:10s} {side:3s} not moved: the segment would get shorter than {MIN_SEG}s")
                else:
                    moved.append((s['id'], side, t, move))
                    s[side] = move
    if moved:
        import shutil
        shutil.copyfile(os.path.join(proj, 'edl.json'), os.path.join(work, 'edl_before_fix.json'))
        with open(os.path.join(proj, 'edl.json'), 'w', encoding='utf-8') as fh:
            json.dump(edl, fh, indent=1, ensure_ascii=False)
        for i, side, old, new in moved:
            print(f'moved  {i:10s} {side:3s} {old:7.2f} -> {new:.2f}')
        print('edl.json updated (old one in work/edl_before_fix.json); assemble again and listen to these joins')
    elif fix:
        print('nothing to move')
    print(f'{bad} unsafe edge(s)' if bad else 'no unsafe edges')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
