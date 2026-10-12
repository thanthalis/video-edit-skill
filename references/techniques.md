# Techniques (any look)

Building blocks that worked on a real reel, independent of colours and fonts. Take the style (font, colour, size) from
the user's house rules or the chosen look; take the mechanics from here. All times come from the word timings
(`W(seg, src_t)` maps a source time to the cut, see the template).

## Hook question with a background swap on the key word
- Open with a separate short clip where the user asks the question the reel answers ("... or is it all hype?").
- On the key word, the wall behind them becomes a photo the user supplies, with the key word big behind their head.
- **Bake it, do not layer it.** Cut the user out of the hook clip only (`HF remove-background hook.mp4 -o hook-subject.webm`),
  then composite with ffmpeg so the render never has to handle an alpha WebM (see gotchas, Windows):
  ```bash
  ffmpeg -i bg.jpg -vf "drawtext=fontfile=Font.ttf:text='hype?':fontsize=300:fontcolor=white:x=(w-text_w)/2:y=420:shadowcolor=black@0.45:shadowy=10" bg_word.png
  ffmpeg -i assets/aroll.mp4 -loop 1 -framerate 30 -i bg_word.png -c:v libvpx-vp9 -i hook-subject.webm \
    -filter_complex "[1:v]format=rgba[bg];[2:v]format=rgba[fg];[bg][fg]overlay=0:0:shortest=1,format=yuv420p,setpts=PTS-STARTPTS[hk];[0:v][hk]overlay=0:0:eof_action=pass:enable='between(t,KEY-0.1,HOOK_END)'[v]" \
    -map "[v]" -map 0:a -c:v libx264 -crf 14 -pix_fmt yuv420p -r 30 -c:a copy assets/aroll_baked.mp4
  ```
  Point the base `<video>` at `aroll_baked.mp4`. Place the word so only the bottom of its letters sits behind the hair.
- A slow push during the question keeps the opening alive: `tl.fromTo('#stage',{scale:1},{scale:1.08,duration:KEY,ease:'none'},0)`.

## Preview card hand-off to the next clip
- Near the end of the hook, show the next clip's first frame as a still in a tilted card, then grow it to full screen
  exactly when that clip starts. Give the hook ~0.3 s of extra tail (silence) so the card is seen before it grows.
- Animate with transforms only (the linter rejects left/top/width/height): a full-size element scaled down.
  ```js
  // #pv: position:absolute; left:0; top:0; width:1080px; height:1920px; border:26px solid #fff; overflow:hidden
  const k = 250/1080;
  gsap.set('#pv',{autoAlpha:0,transformOrigin:'0 0',x:70,y:900,scale:k*.6,rotation:-4,borderRadius:130,borderWidth:26});
  tl.to('#pv',{autoAlpha:1,scale:k,duration:.32,ease:'back.out(1.8)'}, CARD_IN);
  tl.to('#pv',{x:0,y:0,scale:1,rotation:0,borderRadius:0,borderWidth:0,duration:.38,ease:'power3.inOut'}, NEXT_START-.38);
  tl.set('#pv',{autoAlpha:0}, NEXT_START+.03);
  ```
  Give the still the same grade class as the footage so the hand-off does not jump in colour.

## Whip + word chips over a jump cut
- A cut inside the same shot (a removed mistake) reads as a jump. Hide it with a whip and words that land on the
  spoken list ("videos, PDFs, links"), one chip per word, in the punch colour for the middle one.
  ```js
  tl.to('#stage',{x:-140,filter:'blur(18px)',duration:.12,ease:'power2.in'}, CUT-.12);
  tl.fromTo('#stage',{x:140,filter:'blur(18px)'},{x:0,filter:'blur(0px)',duration:.18,ease:'power2.out',immediateRender:false}, CUT);
  tl.set('#stage',{filter:'none'}, CUT+.2);
  ```
  Skip the usual cut punch on that cut, the whip owns it. A whoosh 0.14 s before the cut.

## Fake second camera on a punchline
- AI camera-angle edits (Omni) returned the same frontal shot twice. A hard punch-in sells a second camera for free:
  ```js
  tl.set('#bgv',{scale:1.45,rotation:-1.6,transformOrigin:'50% 70%'}, IN);   // origin low keeps the chin high
  tl.set('#bgv',{scale:1,rotation:0}, OUT);                                     // about one second later
  ```
  Check that words below the face still clear the chin at that zoom.

## Camera as a card for a list
- While explaining a list, shrink the camera to a rounded card at the top and build a card underneath, one row per
  spoken item (see the template's `sources_card()`): `scale:.38, y:226, borderRadius:110` in 0.55 s, back 0.47 s before
  the next cut.

## Fillers
- Transcribe with `initial_prompt` "Euh, ehm, eh..." and `suppress_tokens=[]`; Whisper hides fillers otherwise. Cut them
  unless the user wants one kept.
