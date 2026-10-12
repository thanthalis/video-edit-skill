#!/usr/bin/env python3
"""Frame-exact QA of a render: the last frame before and first frame after every cut, in one strip, plus a phone copy.

Usage:  PY check_cuts.py <project_dir> <render.mp4> [--phone] [--strip]
Writes work/cut_check.jpg (pairs left->right: before|after for each cut). LOOK at it: every 'after' frame must show the
new shot with that section's look and no leftovers (room plates, cutout of the previous shot, stale captions).
Snapshots from `hyperframes snapshot` seek approximately at cuts; only frames pulled from the final render are proof.
--phone also writes <render>-phone.mp4 (720p, crf 26; SendUserFile uploads over ~5MB often fail, drop to crf 28).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

skillenv.utf8_stdio()
FF = skillenv.tool('ffmpeg')
proj, render = skillenv.path_arg(sys.argv[1]), skillenv.path_arg(sys.argv[2])
with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
    segs = json.load(fh)
cf = os.path.join(proj, 'work', 'cf')
sheet = os.path.join(proj, 'work', 'cut_check.jpg')
os.makedirs(cf, exist_ok=True)
pngs = []
for s in segs[1:]:
    for n in (s['frame'] - 1, s['frame']):
        p = os.path.join(cf, f'f{n}.png')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', f'select=eq(n\\,{n}),scale=150:-2', '-frames:v', '1', p], check=True)
        pngs.append(p)
ins = sum((['-i', p] for p in pngs), [])
subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', f'hstack={len(pngs)}', sheet], check=True)
print('cuts at frames', [s['frame'] for s in segs[1:]], '->', sheet)


def probe_duration(f):
    return float(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f],
                                **skillenv.TEXT).stdout.strip())


if '--strip' in sys.argv:
    # local patch (from browser-use/video-use): per cut a filmstrip -1.5s..+1.5s with the waveform under it, plus the
    # first and last 2s, then duration and loudness. A critic sub-agent reads cut_strips.jpg; see SKILL.md step 7.
    dur = probe_duration(render)
    rows, sdir = [], os.path.join(proj, 'work', 'strips')
    os.makedirs(sdir, exist_ok=True)
    spots = [('start', 0.0, 2.0)] + [(s['id'], s['frame'] / 30 - 1.5, 3.0) for s in segs[1:]] + [('end', max(dur - 2.0, 0), 2.0)]
    for k, (name, t0, span) in enumerate(spots):
        t0 = max(t0, 0.0)
        span = min(span, dur - t0)
        fr = []
        for j in range(6):
            p = os.path.join(sdir, f'r{k}_{j}.png')
            subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f'{t0 + span * j / 5 - (0.04 if j == 5 else 0):.3f}', '-i', render,
                            '-frames:v', '1', '-vf', 'scale=120:214', p], check=True)
            fr.append(p)
        wave = os.path.join(sdir, f'r{k}_wave.png')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{span:.3f}', '-i', render, '-filter_complex',
                        'aformat=channel_layouts=mono,showwavespic=s=720x60:colors=white,drawbox=x=358:y=0:w=4:h=60:color=red@0.8:t=fill',
                        '-frames:v', '1', wave], check=True)
        row = os.path.join(sdir, f'row{k}.png')
        ins = sum((['-i', p] for p in fr + [wave]), [])
        subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', 'hstack=6[f];[f][6]vstack', row], check=True)
        rows.append(row)
        print(f'row {k + 1}: {name} {t0:.2f}-{t0 + span:.2f}s' + ('  (cut = red line in the middle)' if name not in ('start', 'end') else ''))
    strips = os.path.join(proj, 'work', 'cut_strips.jpg')
    ins = sum((['-i', p] for p in rows), [])
    subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', f'vstack={len(rows)}' if len(rows) > 1 else 'null', strips], check=True)
    expect = (segs[-1]['frame'] + segs[-1]['frames']) / 30
    err = subprocess.run([FF, '-hide_banner', '-nostats', '-i', render, '-af', 'ebur128=peak=true', '-f', 'null', '-'], **skillenv.TEXT).stderr
    summ = err[err.rfind('Summary:'):]
    lufs = next((ln.split()[1] for ln in summ.splitlines() if ln.strip().startswith('I:')), '?')
    peak = next((ln.split()[1] for ln in summ.splitlines() if ln.strip().startswith('Peak:')), '?')
    print(f'duration {dur:.2f}s (cut list {expect:.2f}s)' + ('' if abs(dur - expect) < 0.1 else '  << MISMATCH'))
    print(f'loudness {lufs} LUFS, true peak {peak} dBTP (Reels: about -14 LUFS, peak under -1)')
    print('->', strips)
if '--phone' in sys.argv:
    out = os.path.splitext(render)[0] + '-phone.mp4'
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', 'scale=720:-2', '-c:v', 'libx264', '-crf', '26', '-preset', 'slow',
                    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out], check=True)
    print('phone copy', out, f'{os.path.getsize(out) / 1e6:.1f} MB')
