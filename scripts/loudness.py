#!/usr/bin/env python3
"""Bring a finished render to Reels loudness: about -14 LUFS integrated, true peak at most -1 dBTP.

Usage:  PY loudness.py <render.mp4> [--target -14]
Measures with ebur128, applies ONE linear gain plus a peak limiter (no dynamic normalisation, which makes a voice
"pump"), copies the video stream untouched and replaces the file ONLY with a result that is better than what was there.
Does nothing when the render is already within 1 LU of the target with the true peak at or under -1 dBTP.

Why (local patch): the test reel shipped at -19.4 LUFS. Instagram plays everything at about the same level, so a
quiet upload sounds weaker and noisier than the reels around it. Filming without a microphone makes this worse.
Second real reel (with a microphone, -14.8 LUFS, peak -1.0): an earlier version of this script "corrected" it to
-15.1 LUFS with heavy limiting and overwrote the render. Hence the 1 LU tolerance, the cap on extra gain and the
better-or-keep rule.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF = skillenv.tool('ffmpeg')
MAX_TP = -1.0     # dBTP; Reels and most platforms want the true peak at or under -1
TOL = 1.0         # LU; closer than this to the target is left alone (platforms normalise anyway)
EXTRA = 2.0       # dB; never add more gain than the measured shortfall plus this (limiter compensation)


def measure(f):
    err = subprocess.run([FF, '-hide_banner', '-nostats', '-i', f, '-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         **skillenv.TEXT).stderr
    summ = err[err.rfind('Summary:'):]
    lufs = float(re.search(r'I:\s+(-?[\d.]+) LUFS', summ).group(1))
    peak = float(re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', summ).group(1))
    return lufs, peak


def render(f, out, gain, ceiling):
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', f, '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy',
                    '-af', f'volume={gain:.2f}dB,alimiter=limit={10 ** (ceiling / 20):.4f}:attack=5:release=50:level=false:latency=true',
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', out], check=True)
    return measure(out)


def main():
    skillenv.utf8_stdio()
    f = skillenv.path_arg(sys.argv[1])
    target = float(sys.argv[sys.argv.index('--target') + 1]) if '--target' in sys.argv else -14.0
    lufs, peak = measure(f)
    print(f'before: {lufs:.1f} LUFS, true peak {peak:.1f} dBTP')
    # alimiter's latency compensation (FFmpeg 5.1+) keeps the voice in sync; without it the audio would shift ~5 ms
    # and lose its last samples, so an older FFmpeg gets no correction rather than a slightly broken one
    if 'latency' not in subprocess.run([FF, '-hide_banner', '-h', 'filter=alimiter'], **skillenv.TEXT).stdout:
        print('NOT changed: this FFmpeg is too old for a sync-safe limiter (needs 5.1 or newer); render left as it was')
        return
    if abs(lufs - target) <= TOL and peak <= MAX_TP:
        print('already right, nothing changed')
        return
    tmp = os.path.splitext(f)[0] + '.loudness-tmp.mp4'
    base_gain = target - lufs
    gain, ceiling = base_gain, MAX_TP - 1.0
    best = None   # (distance to target, gain, ceiling, lufs, peak)
    for _ in range(4):
        l2, p2 = render(f, tmp, gain, ceiling)
        if p2 <= MAX_TP and (best is None or abs(l2 - target) < best[0]):
            best = (abs(l2 - target), gain, ceiling, l2, p2)
        if p2 <= MAX_TP and abs(l2 - target) <= .5:
            break
        if p2 > MAX_TP:
            ceiling -= p2 - MAX_TP + .2          # only the overshoot, plus a little margin
        else:
            gain = min(gain + (target - l2), base_gain + EXTRA)   # limiter ate some gain; capped
    # keep the original unless the best attempt is genuinely better (closer to the target, peak in bounds)
    orig_dist = abs(lufs - target) if peak <= MAX_TP else float('inf')
    if best is None or best[0] >= orig_dist:
        if os.path.exists(tmp):
            os.remove(tmp)
        print('NOT changed: no attempt beat the original (closer to the target with the true peak under '
              f'{MAX_TP} dBTP); render left as it was')
        return
    if (best[1], best[2]) != (gain, ceiling) or abs(best[3] - l2) > 1e-6:
        render(f, tmp, best[1], best[2])          # the last attempt was not the best one: redo the best
    os.replace(tmp, f)
    print(f'after:  {best[3]:.1f} LUFS, true peak {best[4]:.1f} dBTP (gain {best[1]:+.1f} dB, video untouched)')


if __name__ == '__main__':
    main()
