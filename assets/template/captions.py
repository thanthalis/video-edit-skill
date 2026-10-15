"""Full captions for a reel: every spoken word, 2-4 at a time, from the cut's words.json (local patch).

Use from build.py (the template copies this file into the project):

    from captions import Captions
    CAP = Captions(segments=SEGL, dur=DUR, zoomed={'editor', 'ciao'},          # ids of punched-in segments
                   fixes={'cloud': 'claude'}, keywords={'tijd', 'feedback'},
                   style=CAPTION_STYLE)                                       # see DEFAULT_STYLE
    cap_html, cap_tweens = CAP.build(card_spans=[(a, b), ...])                # cards: captions move to the top
    # put cap_html inside #root (it starts with its own <style>), add cap_tweens to the timeline

Rules (SKILL.md hard rule 8): captions say what was said (fix Whisper with `fixes`), break only between words and
preferably at punctuation or a pause, a lone short word ("de", "ai") is glued to the chunk before it, a chunk never
spans two shots (it would sit in the wrong place after the cut), the keyword of a chunk takes the accent colour.
Style comes from the user's house-rules ("Captions" section) through CAPTION_STYLE; nothing here is personal.
"""
import json
from html import escape as html_escape

DEFAULT_STYLE = {
    'font': "'Inter Tight'", 'weight': 900, 'size': 78, 'color': '#fff', 'accent': '#FAE67A',
    'case': 'lower',                       # 'lower' or 'as-said'
    'background': 'shadow',                # 'shadow' (no box), 'pill' or 'box'
    'bg_color': 'rgba(0,0,0,.58)',         # for pill / box
    'top_full': 1210, 'top_zoom': 236,     # full shots: chest band; punch-ins: above the head (measure per reel)
    'top_card': None,                      # while the camera is a small card on top (None = top_zoom)
    'position': 'auto',                    # 'auto' (as above) or 'bottom' (always top_full)
    'max_words': 4, 'max_chars': 18, 'gap': .25,
    'max_width': 940,                      # px a caption may take (1080 minus the safe sides and some air)
    'min_size': 46,                        # px; never shrink below this (readable on a phone, rule 8 asks >= 34)
    'char_w': .56,                         # average glyph width in em; .56 fits Inter Tight 900, raise it for wider fonts
}


class Captions:
    def __init__(self, segments, dur, zoomed=(), fixes=None, keywords=(), style=None, words_path='words.json'):
        self.segs, self.dur, self.zoomed = segments, dur, set(zoomed)
        self.fixes, self.keys = {k.lower(): v for k, v in (fixes or {}).items()}, {k.lower() for k in keywords}
        self.st = {**DEFAULT_STYLE, **(style or {})}
        with open(words_path, encoding='utf-8') as fh:
            self.raw = json.load(fh)

    def seg_end(self, sid):
        k = next(n for n, s in enumerate(self.segs) if s['id'] == sid)
        return self.segs[k + 1]['frame'] / 30 if k + 1 < len(self.segs) else self.dur

    def seg_at(self, t):
        return next(s['id'] for s in reversed(self.segs) if s['frame'] / 30 <= t + 1e-6)

    def owner(self, w):
        """the shot a word belongs to: where its MIDDLE is (Whisper often starts a shot's first word a few frames before
        the cut; a word that really starts just before a cut keeps its middle in that shot)"""
        return self.seg_at((w['start'] + w['end']) / 2)

    def words(self):
        out = []
        for w in self.raw:
            t = w['text'].strip()
            if not t:
                continue
            if t.startswith('-') and out:                  # "auto" + "-editie": Whisper splits hyphenated words
                out[-1]['text'] += t
                out[-1]['end'] = w['end']
                continue
            core = t.rstrip('.,')
            punct = t[len(core):]
            fixed = self.fixes.get(core.lower(), core)
            if self.st['case'] == 'lower':
                fixed = fixed.lower()
            keep = '' if punct in ('.', ',') else punct
            out.append({'text': fixed + keep, 'brk': bool(punct), 'start': w['start'], 'end': w['end']})
        for w in out:                                      # fixes may target the joined form too ("auto-editie")
            w['text'] = self.fixes.get(w['text'].lower(), w['text'])
        return out

    def chunks(self):
        st, res, cur = self.st, [], []
        for w in self.words():
            if cur:
                gap = w['start'] - cur[-1]['end']
                n_chars = len(' '.join(x['text'] for x in cur + [w]))
                if (cur[-1]['brk'] or gap > st['gap'] or len(cur) >= st['max_words'] or n_chars > st['max_chars']
                        or self.owner(w) != self.owner(cur[0])):
                    res.append(cur)
                    cur = []
            cur.append(w)
        if cur:
            res.append(cur)
        merged = []
        for c in res:
            if (merged and len(c) == 1 and len(c[0]['text']) <= 3
                    and self.owner(c[0]) == self.owner(merged[-1][0])
                    and c[0]['start'] - merged[-1][-1]['end'] <= st['gap']   # never across a pause
                    # and only up to the normal size plus that one short word, so merges cannot snowball off-screen
                    and len(merged[-1]) + 1 <= st['max_words'] + 1
                    and len(' '.join(w['text'] for w in merged[-1] + c)) <= st['max_chars'] + 4):
                merged[-1] = merged[-1] + c
            else:
                merged.append(c)
        return merged

    def css(self):
        st = self.st
        base = (f".cap{{position:absolute;left:0;right:0;text-align:center;z-index:8;white-space:nowrap;"
                f"font:{st['weight']} {st['size']}px/1.05 {st['font']};letter-spacing:-.035em;color:{st['color']}}}"
                f".cap .k{{color:{st['accent']}}}")
        if st['background'] == 'shadow':
            return base + ".cap{text-shadow:0 6px 24px rgba(0,0,0,.75),0 0 3px rgba(0,0,0,.7)}"
        radius = 999 if st['background'] == 'pill' else 18
        return base + (f".cap span.box{{display:inline-block;padding:.12em .45em .18em;border-radius:{radius}px;"
                       f"background:{st['bg_color']}}}")

    def build(self, card_spans=()):
        # the stylesheet travels with the captions: the template has no .cap rules of its own
        st, html, tw, ch = self.st, [f'<style>{self.css()}</style>'], [], self.chunks()
        own = [self.owner(c[0]) for c in ch]
        # appear with the first word, never before the owning shot's cut
        starts = [max(c[0]['start'] - .05, next(s['frame'] / 30 for s in self.segs if s['id'] == o)) for c, o in zip(ch, own)]
        for k, c in enumerate(ch):
            a = starts[k]
            nxt = starts[k + 1] if k + 1 < len(ch) else self.dur
            # gone by the next caption and never past the owning shot (after the cut it would sit in the wrong place)
            b = min(nxt, c[-1]['end'] + .6, self.seg_end(own[k]))   # hard limits: next caption, end of the shot
            fade_in, fade_out = min(.12, (b - a) / 3), min(.08, (b - a) / 3)   # short slots get shorter fades
            on_card = any(x - .3 <= c[0]['start'] <= y for x, y in card_spans)
            if on_card and (st['position'] == 'auto' or st['top_card'] is not None):   # 'bottom' stays bottom unless told
                top = st['top_card'] if st['top_card'] is not None else st['top_zoom']
            else:
                top = st['top_zoom'] if st['position'] == 'auto' and own[k] in self.zoomed else st['top_full']
            # escaped at the HTML boundary (a tutorial can say "<div>" or "&copy;"); keyword matching uses the raw text
            words = ' '.join(f'<span class="{"k" if w["text"].rstrip("!?").lower() in self.keys else ""}">{html_escape(w["text"])}</span>' for w in c)
            if st['background'] != 'shadow':
                words = f'<span class="box">{words}</span>'
            cid = f'cap{k}'
            # a long Dutch compound can be wider than the frame: shrink that caption, never split the word
            text = ' '.join(w['text'] for w in c)
            pad = 1.0 if st['background'] == 'shadow' else 1.12
            est = len(text) * st['size'] * st['char_w'] * pad
            fit = '' if est <= st['max_width'] else f";font-size:{max(st['min_size'], int(st['size'] * st['max_width'] / est))}px"
            if est * st['min_size'] / st['size'] > st['max_width']:
                # still too wide at the minimum size (a very long word or a wide font): wrap between words instead
                # of letting overflow:hidden crop it
                fit += f";white-space:normal;max-width:{st['max_width']}px;margin:0 auto"
            html.append(f'<div id="{cid}" class="cap" style="top:{top}px{fit}">{words}</div>')
            tw += [f"gsap.set('#{cid}',{{autoAlpha:0}});",
                   f"tl.fromTo('#{cid}',{{autoAlpha:0,scale:1.12}},{{autoAlpha:1,scale:1,duration:{fade_in:.3f},ease:'power3.out',immediateRender:false}},{a:.3f});"]
            if b < self.dur - .01:
                tw += [f"tl.to('#{cid}',{{autoAlpha:0,duration:{fade_out:.3f}}},{b - fade_out:.3f});", f"tl.set('#{cid}',{{autoAlpha:0}},{b:.3f});"]
        return html, tw
