# ChatCut as a supplier (optional)

ChatCut (chatcut.io) is an AI editor with its own timeline, available as a ChatGPT plugin, a Claude Code plugin and a
desktop app with an MCP server. In this skill it is a **supplier of extra footage, never the editor**: the reel is
still cut, captioned and rendered here. Idea and rules from Jeroen Van Poeyer's setup (2026-10-15).

## When it fits
- The script needs a picture the talking head cannot show: stock footage, a short generated clip (a product, a place,
  an object), a sound effect or a music bed the user asked for.
- Never to replace the speaker, change the camera angle of the user's own footage, or "fix" a take. A generated
  second angle of the speaker failed in testing (Google Omni changed nothing twice); use the fake second camera from
  `references/techniques.md` instead.

## Rules
1. **Ask before anything that costs credits.** Name the clip, model, length and that it uses paid credits; wait for a
   clear yes. Video generation needs a paid ChatCut plan or credits; on a free account it returns an entitlement error.
2. **Upload only what the clip needs** (one reference still, never the whole project or other people's material).
3. Order **silent 9:16 clips** at 1080x1920 when possible; the reel's own voice and mix stay in charge.
4. **AI footage is never shown as real proof** (no fake results, screenshots, reviews or people). Label it in the
   cut list as generated.
5. Music only when the user asks, always ducked under the voice.
6. Place the delivered file in `<project>/assets/broll/` and treat it like any other insert: it lands on its spoken
   word, it never covers the face, and frames are checked in the final render.

## How
- With the ChatCut Desktop MCP connected: confirm the active project first, then follow its own video/image/music
  skills for the request; download the result to `assets/broll/`.
- Without it: tell the user what to generate (prompt, length, 9:16, silent) and ask them to drop the file into
  `assets/broll/`.
