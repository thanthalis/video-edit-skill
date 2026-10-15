#!/usr/bin/env python3
"""Islands of sound: split a source clip at its silences, transcribe every island on its own, propose keep/cut.

Usage:  PY islands.py <project_dir> <clip_id> ["names and keywords: Claude, Remotion"] [--noise <dB, default: room floor + 10>] [--min-sil 0.15]
Writes work/takes_<clip>.tsv (one row per island: keep / CUT / CHECK + reason + text), work/words_<clip>_islands.json
(every word with source times, fillers included) and work/silence_<clip>.json (used by lint_edl.py).

Why per island (local patch, idea from vincentventalon/claude-code-video-editing-skill): one Whisper pass over the
whole clip merges a retake into the take before it and drops "euh"; an island that is only breath, a click or a filler
then hides inside a sentence. Transcribed alone, such an island comes back empty or as fillers only, and a false start
looks like the start of the island after it. The TSV is a PROPOSAL for approval gate 1, never applied blindly.
"""
import difflib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FILLERS = {'euh', 'eh', 'ehm', 'uhm', 'uh', 'um', 'hm', 'hmm', 'mm', 'ah', 'eum', 'euhm', 'em'}
FILLER_PROMPT = 'Euh, ehm, eh, uhm... '


def opt(name, default):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def silences(audio, min_sil, noise=None):
    """Energy-based silence on 20 ms frames. The threshold follows the room: noise floor (10th percentile) + 10 dB,
    because a fixed -35 dB missed every pause of a fast talker in a room with background hum (test reel, 2026-10-12)."""
    import numpy as np
    hop = 320
    n = len(audio) // hop
    rms = np.sqrt(np.mean(audio[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = noise if noise is not None else float(min(np.percentile(db, 10) + 10, -30))
    quiet = db < thr
    out, k = [], 0
    while k < n:
        if quiet[k]:
            j = k
            while j < n and quiet[j]:
                j += 1
            if (j - k) * 0.02 >= min_sil:
                out.append({'start': round(k * 0.02, 3), 'end': round(j * 0.02, 3)})
            k = j
        else:
            k += 1
    return out, thr


# spoken notes to the editor and self-corrections (NL + EN); a hit makes the island CHECK, the user decides
NOTES = ('foutje', 'mag eruit', 'mag er uit', 'mag ik er', 'knip dit', 'opnieuw', 'nog een keer', 'nog eens', 'sorry',
         'cut this', 'let me redo', 'once more', 'start over', 'take two')
CORRECTION = re.compile(r'(^|[.,!?] )(nee|neen|no|wacht|wait)[,.!] ', re.I)


# Whisper "hears" subtitle credits in near-silence (seen on a real reel: "Closed Captioning by GetTranscribed.com" on three
# breath/click islands). Any island whose text contains one of these is noise, never speech.
HALLUCINATIONS = ('closed captioning', 'captioning by', 'gettranscribed', 'transcribed by', 'ondertiteling', 'ondertiteld door',
                  'bedankt voor het kijken', 'thanks for watching', 'subtitles by', 'amara.org', 'tv gelderland')


def hallucination(words):
    text = ' '.join(w['text'] for w in words).lower()
    hit = next((h for h in HALLUCINATIONS if h in text), None)
    if hit:
        return hit
    # Whisper's other habit in near-silence: one word or phrase looped ("thank you, thank you, thank you, ...")
    toks = [re.sub(r'[^\w]', '', w['text'].lower()) for w in words]
    toks = [t for t in toks if t]
    for n in (1, 2):
        grams = [' '.join(toks[k:k + n]) for k in range(0, len(toks) - n + 1, n)]
        if len(grams) >= 3 and len(set(grams)) == 1:
            return f'"{grams[0]}" repeated'
    return None


def speech(words):
    """Whisper writes noises as *clap*, [music], (laughs): those are not speech."""
    return [w for w in words if w['text'].strip()[:1] not in '*[(' and w['text'].strip('*.[]() ')]


def norm(words):
    return [re.sub(r'[^\w]', '', w['text'].lower()) for w in words if re.sub(r'[^\w]', '', w['text'].lower())]


def main():
    skillenv.utf8_stdio()
    args = [a for i, a in enumerate(sys.argv) if not a.startswith('--') and not (i > 0 and sys.argv[i - 1].startswith('--'))]
    proj, clip = skillenv.path_arg(args[1]), args[2]
    names = args[3] if len(args) > 3 else ''
    noise, min_sil = (opt('--noise', 0) if '--noise' in sys.argv else None), opt('--min-sil', 0.15)
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        src = json.load(fh)[clip]
    work = os.path.join(proj, 'work')
    os.makedirs(work, exist_ok=True)
    wav = os.path.join(work, f'{clip}.wav')
    if not os.path.exists(wav):
        subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)

    from faster_whisper import WhisperModel, decode_audio
    import numpy as np
    audio = decode_audio(wav, sampling_rate=16000)
    total = len(audio) / 16000
    sil, noise = silences(audio, min_sil, noise)
    print(f'silence = below {noise:.1f} dB for {min_sil}s or longer: {len(sil)} pauses', flush=True)
    with open(os.path.join(work, f'silence_{clip}.json'), 'w', encoding='utf-8') as fh:
        json.dump({'noise': round(noise, 1), 'min_sil': min_sil, 'total': round(total, 3), 'silences': sil}, fh, indent=1)

    # islands = the sound between silences
    isl, t = [], 0.0
    for s in sil + [{'start': total, 'end': total}]:
        if s['start'] - t >= 0.12:
            isl.append({'start': round(t, 3), 'end': round(s['start'], 3)})
        t = s['end']

    model, lang = skillenv.whisper_settings('cut')
    m = WhisperModel(model, compute_type='int8')
    allw = []
    for k, i in enumerate(isl):
        a, b = max(0, int((i['start'] - 0.05) * 16000)), min(len(audio), int((i['end'] + 0.05) * 16000))
        segs, _ = m.transcribe(audio[a:b], word_timestamps=True, vad_filter=False, language=lang, suppress_tokens=[],
                               initial_prompt=FILLER_PROMPT + names, condition_on_previous_text=False)
        off = a / 16000
        i['words'] = [{'text': w.word.strip(), 'start': round(w.start + off, 3), 'end': round(w.end + off, 3)}
                      for s in segs for w in s.words if w.word.strip()]
        allw += i['words']
        print(f'island {k + 1}/{len(isl)} {i["start"]:.2f}-{i["end"]:.2f}', flush=True)

    # proposals
    for k, i in enumerate(isl):
        i['words'] = speech(i['words'])
        ws = norm(i['words'])
        hal = hallucination(i['words'])
        if hal:
            # Whisper "captions" breaths and clicks; real speech (an outro: "bedankt voor het kijken") is loud.
            # Only an island whose loudest 20 ms stays near the silence threshold is noise; anything else stays CHECK.
            seg = audio[int(i['start'] * 16000):int(i['end'] * 16000)]
            n = len(seg) // 320
            peak_db = float(20 * np.log10(np.sqrt(np.mean(seg[:n * 320].reshape(n, 320) ** 2, axis=1) + 1e-12)).max()) if n else -120.0
            if peak_db < noise + 12:
                i['words'], i['verdict'], i['why'] = [], 'CUT', f'Whisper hallucination in near-silence ("{hal}", peak {peak_db:.0f} dB)'
            else:
                i['verdict'], i['why'] = 'CHECK', f'sounds like a Whisper hallucination ("{hal}"), but it has voice level: listen'
            continue
        content = [w for w in ws if w not in FILLERS]
        i['verdict'], i['why'] = 'keep', ''
        if not ws:
            i['verdict'], i['why'] = 'CUT', 'no speech (breath, click, noise)'
        elif not content:
            i['verdict'], i['why'] = 'CUT', 'fillers only'
        else:
            for j in range(k + 1, min(k + 3, len(isl))):
                nxt = [w for w in norm(isl[j].get('words', [])) if w not in FILLERS]
                if not nxt:
                    continue
                n = min(len(content), len(nxt))
                if n >= 2 and content[:n] == nxt[:n] and len(content) < len(nxt):
                    i['verdict'], i['why'] = 'CUT', f'false start, retaken in island {j + 1}'
                    break
                r = difflib.SequenceMatcher(None, content, nxt).ratio()
                if r >= 0.7 and len(content) >= 3:
                    i['verdict'], i['why'] = 'CHECK', f'retake? {int(r * 100)}% like island {j + 1} (usually keep the LAST take)'
                    break
            text = ' '.join(w['text'] for w in i['words'])
            note = next((n for n in NOTES if n in text.lower()), None) or (CORRECTION.search(text) and 'correction ("nee, ...")')
            if i['verdict'] == 'keep' and note:
                i['verdict'], i['why'] = 'CHECK', f'spoken note or correction: {note} (usually cut from there)'
            fill = [w for w in ws if w in FILLERS]
            if i['verdict'] == 'keep' and fill:
                i['verdict'], i['why'] = 'CHECK', f'contains filler(s): {" ".join(fill)} (cut inside the island at a silence)'

    with open(os.path.join(work, f'words_{clip}_islands.json'), 'w', encoding='utf-8') as fh:
        json.dump(allw, fh, indent=1, ensure_ascii=False)
    tsv = os.path.join(work, f'takes_{clip}.tsv')
    with open(tsv, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('n\tstart\tend\tdur\tverdict\twhy\ttext\n')
        for k, i in enumerate(isl):
            txt = ' '.join(w['text'] for w in i['words'])
            fh.write(f'{k + 1}\t{i["start"]:.2f}\t{i["end"]:.2f}\t{i["end"] - i["start"]:.2f}\t{i["verdict"]}\t{i["why"]}\t{txt}\n')
    for k, i in enumerate(isl):
        txt = ' '.join(w['text'] for w in i['words'])
        print(f'{k + 1:3d} {i["start"]:6.2f}-{i["end"]:6.2f} {i["verdict"]:5s} {txt[:70]}' + (f'   [{i["why"]}]' if i['why'] else ''))
    longest = max((i['end'] - i['start'] for i in isl), default=0)
    if longest > 10:
        print(f'note: longest island {longest:.1f}s (few pauses); pick takes inside it from the words, islands only mark the joins')
    print('->', tsv)


if __name__ == '__main__':
    main()
