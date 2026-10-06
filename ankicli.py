#!/usr/bin/env python3
"""ankicli — push methodology-driven flashcards into Anki via AnkiConnect.

Division of labor:
  * Claude reads source material (transcripts, docs, user input) and writes a
    cards JSON file following the SKILL.md methodology.
  * This CLI mechanically creates the deck + styled note types, adds the notes,
    and (optionally) syncs to AnkiWeb.

No third-party dependencies — stdlib only. Requires Anki running with the
AnkiConnect add-on (code 2055492159) listening on http://127.0.0.1:8765.

Usage:
    python3 ankicli.py setup                 # create deck + note types (idempotent)
    python3 ankicli.py push cards.json       # add notes, then sync to AnkiWeb
    python3 ankicli.py enrich                # add audio+Youglish to existing vocab cards
    python3 ankicli.py sync                  # sync only
    python3 ankicli.py ping                  # check AnkiConnect is reachable

`enrich` retrofits pronunciation onto notes already in a deck: it selects
vocab/idiom cards (skipping concept/grammar/rule/map cards), extracts each
card's term, and appends TTS audio and/or a Youglish link — skipping any note
that already has them. It applies by default; pass --dry-run to preview
without writing. --audio / --youglish do just one (default: both).

setup/push/enrich sync with AnkiWeb on **both ends**: a pre-sync before touching
the collection (so they operate on the latest from AnkiWeb, not a stale local
copy) and a post-sync afterwards (so changes are pushed straight up). This keeps
desktop/phone/AnkiWeb in step and avoids conflicts. Skip either with
--no-pre-sync / --no-sync (offline / no AnkiWeb).

Cards JSON schema (see cards/example.json):
    {
      "deck": "AnkiCardCreator",              # optional; --deck flag overrides. Cards
                                              # auto-route to subdecks: pronunciation/spelling
                                              # to "<deck>::Pronunciation & Spelling", everything
                                              # else to "<deck>::Main" (base stays an empty container).
      "notes": [
        { "family": "recall|recognition|concept|multimedia",
          "front": "...", "back": "...",
          "example": "...", "note": "...", "source": "...",
          "tags": ["english", "idiom"] },
        { "family": "context",                # -> native Cloze note type
          "text": "It's going to {{c1::freeze}} tonight.",
          "extra": "...", "example": "...", "note": "...", "source": "...",
          "tags": ["english", "collocation"] }
      ]
    }

Field values may contain HTML — that is intentional. Use <code>...</code> for
code, <span class="hl">...</span> for highlights, <b>/<i>, etc. See the note
type CSS created by `setup` for the classes available.

Audio (pronunciation) — add a "tts" key to any note. It is spoken by macOS
`say`, encoded to .m4a (Anki-playable), stored in the collection, and embedded
as [sound:file] in a field. Forms:
    "tts": true                              # auto-derive the term from the card
    "tts": "bow out"                         # -> audio on Back (Cloze: Extra)
    "tts": [{"text": "bow out", "field": "Front"},   # listening card
            {"text": "I bowed out at the last minute.", "field": "Example"}]
Optional per-entry: "voice", "prepend": true. Attach an existing file instead:
    "audio": [{"path": "/abs/x.mp3", "field": "Back"}]   # or "url": "https://..."
Audio uses the macOS *system default* voice unless overridden with `--voice
<name>` (list names with `say -v '?'`). Run `push --no-media` to skip audio.

Youglish (real-speaker pronunciation on YouTube) — add a "youglish" key to a
note for a clickable link, a good fallback when the TTS voice is off:
    "youglish": true                 # auto-derive the term from the card
    "youglish": "bow out"            # use an explicit term
    "youglish": {"term": "bow out", "accent": "uk", "field": "Back"}
    "youglish": {"url": "https://youglish.com/getbyid/…"}   # a specific clip
Default accent is US. The link is offline/free and is added even under
`--no-media`.

Read-aloud — on push every text field also gets its own spoken clip (Basic
Front -> FrontAudio field; Cloze Text with the blank filled -> Extra). English
only: HTML, emoji and CJK are stripped. Skipped on pronunciation/spelling
cards. Opt out with "read_aloud": false or `push --no-read-aloud`; retrofit
existing notes with `read-aloud`.

A note with "family": "pronunciation" defaults BOTH "tts" and "youglish" to
true (override by setting either explicitly) — for pronunciation-breakdown
cards whose Back holds IPA + syllable + tips (styled via the .ipa / .pron CSS).
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import urllib.error

ANKI_URL = "http://127.0.0.1:8765"
DEFAULT_DECK = "AnkiCardCreator"
BASIC_MODEL = "AnkiCardCreator Basic"
CLOZE_MODEL = "AnkiCardCreator Cloze"
SPELLING_MODEL = "AnkiCardCreator Spelling"
PRON_SPELL_SUBDECK = "Pronunciation & Spelling"  # pronunciation/spelling families route here
MAIN_SUBDECK = "Main"  # every other family routes here (so it's drilled with its own new/day limit)
DEFAULT_VOICE = None   # None -> use the macOS system default voice (say with no -v).
                       # Override per-run with --voice, or per-entry with "voice".

# ---------------------------------------------------------------------------
# Shared styling for both note types. Dark-mode aware (Anki adds .nightMode).
# ---------------------------------------------------------------------------
CARD_CSS = r"""
.card {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 20px;
  line-height: 1.5;
  color: #1f2933;
  background: #ffffff;
  text-align: left;
  max-width: 640px;
  margin: 0 auto;
  padding: 18px 20px;
}
.nightMode.card, .night_mode .card {
  color: #e4e7eb;
  background: #16181d;
}

/* family label chip */
.tag {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #3b82f6;
  background: rgba(59,130,246,.12);
  border-radius: 999px;
  padding: 2px 10px;
  margin-bottom: 12px;
}

.q { font-size: 22px; font-weight: 600; }
.a { font-size: 21px; margin-top: 4px; }

hr#answer {
  border: none;
  border-top: 2px solid rgba(59,130,246,.35);
  margin: 16px 0;
}

/* inline code */
code {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: .88em;
  background: #f1f5f9;
  color: #b91c1c;
  padding: 1px 6px;
  border-radius: 5px;
  border: 1px solid #e2e8f0;
}
.nightMode code, .night_mode code {
  background: #23262e; color: #ff8f8f; border-color: #333842;
}

/* fenced code block */
pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px 14px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 15px;
  line-height: 1.45;
}
pre code { background: none; color: inherit; border: none; padding: 0; }

/* highlights */
.hl  { background: #fff3b0; color: #1f2933; padding: 0 3px; border-radius: 3px; }
.hl2 { background: #c7f0d2; color: #14532d; padding: 0 3px; border-radius: 3px; }
.nightMode .hl,  .night_mode .hl  { background: #6b5d0f; color: #fff8d6; }
.nightMode .hl2, .night_mode .hl2 { background: #14532d; color: #d7ffe4; }

/* example sentence — quoted, left rule */
.example {
  margin-top: 14px;
  padding: 8px 14px;
  border-left: 3px solid #94a3b8;
  color: #475569;
  font-style: italic;
}
.nightMode .example, .night_mode .example { color: #a9b2bd; border-color: #4b5563; }

/* mnemonic / note callout */
.note {
  margin-top: 14px;
  padding: 10px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 17px;
}
.note::before { content: "💡 "; }
.nightMode .note, .night_mode .note { background: #1c1f26; border-color: #2c3038; }

/* source / provenance */
.source {
  margin-top: 14px;
  font-size: 13px;
  color: #94a3b8;
}

/* native cloze deletion */
.cloze { font-weight: 700; color: #2563eb; }
.nightMode .cloze, .night_mode .cloze { color: #7cb0ff; }

/* Youglish pronunciation link (real people saying the term on YouTube) */
a.yg {
  display: inline-block;
  margin-top: 12px;
  font-size: 14px;
  text-decoration: none;
  color: #2563eb;
  background: rgba(37,99,235,.10);
  border: 1px solid rgba(37,99,235,.28);
  border-radius: 999px;
  padding: 3px 12px;
}
a.yg:hover { background: rgba(37,99,235,.20); }
.nightMode a.yg, .night_mode a.yg {
  color: #7cb0ff; background: rgba(124,176,255,.12); border-color: rgba(124,176,255,.32);
}

/* pronunciation breakdown (IPA + syllables + tips + memory hook) */
.ipa {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 1.05em;
  color: #7c3aed;
  background: rgba(124,58,237,.08);
  padding: 1px 7px;
  border-radius: 5px;
}
.nightMode .ipa, .night_mode .ipa { color: #c4b5fd; background: rgba(124,58,237,.20); }
/* Compact, scannable reference block — smaller body text, demoted section
   labels, and thin separators so the breakdown chunks instead of looming as
   one wall of large text. */
.pron { margin-top: 8px; font-size: 15px; line-height: 1.4; }
.pron > div { margin-top: 9px; padding-top: 9px; border-top: 1px solid #eef2f7; }
.pron > div:first-child { margin-top: 4px; padding-top: 0; border-top: none; }
.nightMode .pron > div, .night_mode .pron > div { border-color: #262a32; }
.pron > div > b {                 /* section label: IPA / Syllables / Tips / Spelling / Hook */
  font-size: 11.5px; font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; color: #64748b;
}
.nightMode .pron > div > b, .night_mode .pron > div > b { color: #94a3b8; }
.pron ul { margin: 3px 0 0; padding-left: 20px; }
.pron li { margin: 2px 0; }
.pron .ipa { font-size: 1.0em; }  /* keep IPA in step with the smaller block */

/* spelling card: type-in-the-answer box + letter-diff + tips callout */
#typeans {
  width: 100%;
  box-sizing: border-box;
  font-size: 20px;
  padding: 8px 10px;
  margin-top: 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
  color: #1f2933;
}
.nightMode #typeans, .night_mode #typeans {
  background: #23262e; color: #e4e7eb; border-color: #333842;
}
.typeGood   { color: #15803d; background: #dcfce7; }
.typeBad    { color: #b91c1c; background: #fee2e2; text-decoration: line-through; }
.typeMissed { color: #92400e; background: #fef3c7; }
.nightMode .typeGood,   .night_mode .typeGood   { color: #86efac; background: #14532d; }
.nightMode .typeBad,    .night_mode .typeBad    { color: #fca5a5; background: #4c1d1d; }
.nightMode .typeMissed, .night_mode .typeMissed { color: #fde68a; background: #4a3610; }
.spell {
  margin-top: 14px; padding: 10px 14px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 17px;
}
.spell::before { content: "✍️ "; }
.nightMode .spell, .night_mode .spell { background: #1c1f26; border-color: #2c3038; }
/* audio: Anki's native play buttons, restyled small, wrapped in a labelled
   pill (<span class="sl" data-l="label" data-src="file">[sound:file]</span>).
   The label is CSS-only (::after), so it is never read aloud or searched. A
   transparent overlay on the button stretches over the whole pill, so tapping
   the label plays too. */
.replay-button { display: inline-flex; vertical-align: middle; margin: 0 2px; }
.replay-button svg { width: 30px; height: 30px; }
.replay-button svg circle { fill: #eef2ff; stroke: #a5b4fc; stroke-width: 3; }
.replay-button svg path { fill: #4f46e5; transform: scale(.8); transform-origin: center; }
.nightMode .replay-button svg circle, .night_mode .replay-button svg circle { fill: #1e1b4b; stroke: #6366f1; }
.nightMode .replay-button svg path, .night_mode .replay-button svg path { fill: #c7d2fe; }
.sl {
  position: relative; display: inline-flex; align-items: center; gap: 2px;
  padding: 1px 10px 1px 2px; margin: 2px; vertical-align: middle;
  border: 1px solid #c7d2fe; border-radius: 999px; background: #eef2ff;
}
.sl::after { content: attr(data-l); font-size: 14px; font-weight: 600; color: #4338ca; }
.sl .replay-button { position: static; }
.sl .replay-button::after { content: ""; position: absolute; inset: 0; }
.sl .replay-button svg circle { stroke: none; }
.nightMode .sl, .night_mode .sl { background: #1e1b4b; border-color: #4338ca; }
.nightMode .sl::after, .night_mode .sl::after { color: #c7d2fe; }

/* HTML5 players (built by AUDIO_JS from the .sl pills): scrub, -5s/+5s,
   restart, 0.75x. */
.aps { margin-top: 14px; }
.ap {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 8px 0;
  padding: 8px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 15px;
}
.ap .l { font-weight: 600; width: 100%; }
.ap audio { width: 100%; height: 36px; }
.ap button {
  font-size: 15px; padding: 6px 12px; border-radius: 8px;
  border: 1px solid #94a3b8; background: #f1f5f9; color: #1f2933;
}
.nightMode .ap, .night_mode .ap { border-color: #333842; }
.nightMode .ap button, .night_mode .ap button { background: #23262e; color: #e4e7eb; border-color: #4b5563; }
"""

BASIC_FRONT = (
    "{{#Type}}<div class=\"tag\">{{Type}}</div>{{/Type}}\n"
    "<div class=\"q\">{{Front}}</div>\n"
    "{{#FrontAudio}}<div class=\"fa\">{{FrontAudio}}</div>{{/FrontAudio}}"
)
BASIC_BACK = (
    "{{FrontSide}}\n<hr id=answer>\n"
    "<div class=\"a\">{{Back}}</div>\n"
    "{{#Example}}<div class=\"example\">{{Example}}</div>{{/Example}}\n"
    "{{#Note}}<div class=\"note\">{{Note}}</div>{{/Note}}\n"
    "{{#Source}}<div class=\"source\">{{Source}}</div>{{/Source}}"
)
CLOZE_FRONT = "<div class=\"q\">{{cloze:Text}}</div>"
CLOZE_BACK = (
    "<div class=\"q\">{{cloze:Text}}</div>\n"
    "{{#Extra}}<div class=\"a\">{{Extra}}</div>{{/Extra}}\n"
    "{{#Example}}<div class=\"example\">{{Example}}</div>{{/Example}}\n"
    "{{#Note}}<div class=\"note\">{{Note}}</div>{{/Note}}\n"
    "{{#Source}}<div class=\"source\">{{Source}}</div>{{/Source}}"
)
# Spelling: hear the word (+ a meaning clue), type the spelling; Anki grades it
# letter-by-letter via {{type:Word}}. Audio is embedded in Clue (front).
SPELLING_FRONT = (
    "<div class=\"tag\">Spelling</div>\n"
    "<div class=\"q\">✍️ Spell the word you hear</div>\n"
    "{{#Clue}}<div class=\"example\">{{Clue}}</div>{{/Clue}}\n"
    "{{type:Word}}"
)
SPELLING_BACK = (
    "<div class=\"tag\">Spelling</div>\n"
    "<div class=\"q\">{{Word}}</div>\n"
    "{{type:Word}}\n"
    "{{#Tips}}<div class=\"spell\">{{Tips}}</div>{{/Tips}}\n"
    "{{#Source}}<div class=\"source\">{{Source}}</div>{{/Source}}"
)

# Builds one HTML5 player per labelled audio pill (.sl[data-src]) at the end of
# the card. Runs on every side; clears earlier players first, so the copy of
# the front inside {{FrontSide}} doesn't double them.
AUDIO_JS = """
<script>
(function () {
  document.querySelectorAll('.aps').forEach(function (e) { e.remove(); });
  var pills = document.querySelectorAll('.sl[data-src]');
  if (!pills.length) return;
  var box = document.createElement('div'), seen = {};
  box.className = 'aps';
  pills.forEach(function (el) {
    var src = el.getAttribute('data-src');
    if (seen[src]) return;
    seen[src] = 1;
    var d = document.createElement('div');
    d.className = 'ap';
    d.innerHTML = '<span class="l">🔊 ' + el.getAttribute('data-l') + '</span>' +
      '<audio controls preload="metadata"></audio>' +
      '<button data-a="back">−5s</button><button data-a="fwd">+5s</button>' +
      '<button data-a="restart">⟲ restart</button><button data-a="speed">🐢 0.75×</button>';
    var a = d.querySelector('audio');
    a.src = src;
    d.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      var k = b.getAttribute('data-a');
      if (k === 'back') a.currentTime = Math.max(0, a.currentTime - 5);
      else if (k === 'fwd') a.currentTime = Math.min(a.duration || 0, a.currentTime + 5);
      else if (k === 'restart') { a.currentTime = 0; a.play(); }
      else {
        a.playbackRate = a.playbackRate === 1 ? 0.75 : 1;
        b.textContent = a.playbackRate === 1 ? '🐢 0.75×' : '1×';
      }
    });
    box.appendChild(d);
  });
  (document.getElementById('qa') || document.body).appendChild(box);
})();
</script>"""
BASIC_FRONT += AUDIO_JS
BASIC_BACK += AUDIO_JS
CLOZE_FRONT += AUDIO_JS
CLOZE_BACK += AUDIO_JS
SPELLING_FRONT += AUDIO_JS
SPELLING_BACK += AUDIO_JS


def invoke(action: str, **params):
    """Call an AnkiConnect action; raise on error, return the result."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Cannot reach AnkiConnect at {ANKI_URL}: {e}\n"
            "Is Anki running with the AnkiConnect add-on installed?"
        )
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect error on {action}: {data['error']}")
    return data.get("result")


def _pre_sync(args):
    """Pull the latest from AnkiWeb before reading/writing the collection, so we
    never operate on a stale deck and create sync conflicts. Opt out with
    --no-pre-sync (e.g. offline, or AnkiWeb not configured)."""
    if getattr(args, "no_pre_sync", False):
        return
    invoke("sync")
    print("Pre-sync: pulled latest from AnkiWeb.")


def _post_sync(args):
    """Push local changes up to AnkiWeb after we've modified the collection, so
    desktop / phone / AnkiWeb stay in step. Opt out with --no-sync (offline, or
    AnkiWeb not configured)."""
    if getattr(args, "no_sync", False):
        return
    invoke("sync")
    print("Post-sync: pushed changes to AnkiWeb.")


def cmd_ping(_args):
    print(f"AnkiConnect reachable — version {invoke('version')}")


def _ensure_model(name, fields, front, back, is_cloze):
    if name in invoke("modelNames"):
        # Add any fields introduced since the model was created (e.g. FrontAudio).
        have = invoke("modelFieldNames", modelName=name)
        for i, f in enumerate(fields):
            if f not in have:
                invoke("modelFieldAdd", modelName=name, fieldName=f, index=i)
                print(f"  added field {f} to {name}")
        # Keep styling/templates current on re-run.
        invoke("updateModelStyling", model={"name": name, "css": CARD_CSS})
        tmpl = {"Card 1": {"Front": front, "Back": back}}
        invoke("updateModelTemplates", model={"name": name, "templates": tmpl})
        print(f"  updated existing model: {name}")
        return
    invoke(
        "createModel",
        modelName=name,
        inOrderFields=fields,
        css=CARD_CSS,
        isCloze=is_cloze,
        cardTemplates=[{"Name": "Card 1", "Front": front, "Back": back}],
    )
    print(f"  created model: {name}")


def cmd_setup(args):
    _pre_sync(args)
    deck = args.deck or DEFAULT_DECK
    invoke("createDeck", deck=deck)
    invoke("createDeck", deck=f"{deck}::{MAIN_SUBDECK}")
    invoke("createDeck", deck=f"{deck}::{PRON_SPELL_SUBDECK}")
    print(f"  deck ready: {deck}  (+ ::{MAIN_SUBDECK}, ::{PRON_SPELL_SUBDECK})")
    _ensure_model(BASIC_MODEL,
                  ["Front", "Back", "Example", "Note", "Source", "Type", "FrontAudio"],
                  BASIC_FRONT, BASIC_BACK, is_cloze=False)
    _ensure_model(CLOZE_MODEL,
                  ["Text", "Extra", "Example", "Note", "Source"],
                  CLOZE_FRONT, CLOZE_BACK, is_cloze=True)
    _ensure_model(SPELLING_MODEL,
                  ["Word", "Clue", "Tips", "Source"],
                  SPELLING_FRONT, SPELLING_BACK, is_cloze=False)
    print("Setup complete.")
    _post_sync(args)


def _deck_for(family, base):
    """Route cards into subdecks so each is studied at its own pace: pronunciation
    & spelling into one subdeck, everything else into `<base>::Main`. The base deck
    itself stays an empty container."""
    if family in ("pronunciation", "spelling"):
        return f"{base}::{PRON_SPELL_SUBDECK}"
    return f"{base}::{MAIN_SUBDECK}"


def _build_note(card, deck):
    family = (card.get("family") or "recall").lower()
    tags = card.get("tags") or []
    common = {"deckName": _deck_for(family, deck), "tags": tags,
              "options": {"allowDuplicate": False,
                          "duplicateScope": "deck"}}
    if family == "spelling":
        fields = {
            "Word": card.get("word", ""),
            "Clue": card.get("clue", ""),
            "Tips": card.get("tips", ""),
            "Source": card.get("source", ""),
        }
        return {**common, "modelName": SPELLING_MODEL, "fields": fields}
    if family == "context" or "text" in card:
        fields = {
            "Text": card.get("text", ""),
            "Extra": card.get("extra", ""),
            "Example": card.get("example", ""),
            "Note": card.get("note", ""),
            "Source": card.get("source", ""),
        }
        return {**common, "modelName": CLOZE_MODEL, "fields": fields}
    fields = {
        "Front": card.get("front", ""),
        "Back": card.get("back", ""),
        "Example": card.get("example", ""),
        "Note": card.get("note", ""),
        "Source": card.get("source", ""),
        "Type": family.capitalize(),
    }
    return {**common, "modelName": BASIC_MODEL, "fields": fields}


# ---------------------------------------------------------------------------
# Audio / media. A card may request TTS audio via a "tts" key, which is either
# a string or a list of {text, field, voice?, prepend?}. Each entry is spoken by
# macOS `say`, encoded to .m4a (AAC, Anki-playable), stored in the collection,
# and embedded as [sound:file] in the target field. Also supports "audio":
# [{path|url, field, prepend?}] to attach an existing file.
# ---------------------------------------------------------------------------
def _slug(text):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:30] or "audio"


def _synth_and_store(text, voice, prefix="acc"):
    """Speak `text` with macOS `say`, encode to m4a, store in Anki media.

    Returns the stored filename, or None if TTS tooling is unavailable.
    Filename is deterministic (hash of voice+text) so re-runs overwrite rather
    than duplicate.
    """
    if not (shutil.which("say") and shutil.which("afconvert")):
        print("  (skipping audio — macOS `say`/`afconvert` not found)")
        return None
    digest = hashlib.md5(f"{voice or 'default'}:{text}".encode()).hexdigest()[:10]
    filename = f"{prefix}-{_slug(text)}-{digest}.m4a"
    say_cmd = ["say"] + (["-v", voice] if voice else []) + ["-o", None, text]
    with tempfile.TemporaryDirectory() as d:
        aiff, m4a = os.path.join(d, "a.aiff"), os.path.join(d, "a.m4a")
        say_cmd[say_cmd.index(None)] = aiff
        subprocess.run(say_cmd, check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000",
                        aiff, m4a], check=True)
        with open(m4a, "rb") as fh:
            payload = base64.b64encode(fh.read()).decode()
    invoke("storeMediaFile", filename=filename, data=payload)
    return filename


def _embed(note, field, tag, prepend):
    cur = note["fields"].get(field, "")
    note["fields"][field] = (tag + (" " + cur if cur else "")) if prepend \
        else ((cur + " " if cur else "") + tag)


def _strip_html(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip(" .·—-")


_HL_RE = r'<span class="hl2?">(.*?)</span>'
_CLOZE_RE = r"\{\{c\d+::(.*?)(?:::.*?)?\}\}"

# Map a partial/inflected/joined term to a clean single query for a search link.
_YG_OVERRIDES = {
    "flag": "red flag", "scoop": "inside scoop", "sleeve": "up your sleeve",
    "ugly": "the good, the bad, and the ugly", "break": "break down",
    "rat us out": "rat out", "ratted on": "rat on", "have a rat": "smell a rat",
    "take something under advisement": "under advisement",
}


def _extract_term(fields, is_cloze, first_only):
    """Target term from a {FieldName: html} mapping. `first_only` picks the
    primary term (for a search query); otherwise joins co-highlighted parts
    (better for speech, e.g. "break down")."""
    if is_cloze:
        cl = re.findall(_CLOZE_RE, fields.get("Text", "") or "")
        return _strip_html(cl[0] if first_only else ", ".join(cl)) if cl else None
    for name in ("Back", "Example", "Front"):
        spans = re.findall(_HL_RE, fields.get(name, "") or "")
        if spans:
            return _strip_html(spans[0] if first_only else " ".join(spans))
    return re.split(r"[(—]", _strip_html(fields.get("Front", "") or ""))[0].strip() or None


def _term(fields, is_cloze, *, youglish):
    """Speech term (join) vs Youglish query (first term + canonical override)."""
    t = _extract_term(fields, is_cloze, first_only=youglish)
    return _YG_OVERRIDES.get(t, t) if (youglish and t) else t


def _card_term(card, *, youglish=True):  # push-time helper: card JSON uses lowercase keys
    fields = {"Front": card.get("front", ""), "Back": card.get("back", ""),
              "Example": card.get("example", ""), "Text": card.get("text", "")}
    return _term(fields, "text" in card, youglish=youglish)


def _youglish_link(term=None, accent="us", url=None):
    if not url:  # default: a search link; or pass an explicit clip URL (getbyid/…)
        url = f"https://youglish.com/pronounce/{urllib.parse.quote(term)}/english/{accent}"
    return f'<a class="yg" href="{url}">🔎 Youglish</a>'


# ---------------------------------------------------------------------------
# Read-aloud: every text field gets its own spoken audio, embedded in that
# field (so it plays alongside it). The Basic Front's audio goes into a
# separate FrontAudio field, because Front is Anki's duplicate key — putting a
# [sound:] tag in it would break dedup on re-push. A Cloze Text's audio (with
# the blank filled in) goes into Extra, on the back, so it can't give the
# answer away. Pronunciation and spelling cards are skipped: audio on their
# front would reveal what the card is testing.
# ---------------------------------------------------------------------------
READ_ALOUD_FIELDS = {                    # model -> [(source field, target field)]
    BASIC_MODEL: [("Front", "FrontAudio"), ("Back", "Back"),
                  ("Example", "Example"), ("Note", "Note")],
    CLOZE_MODEL: [("Text", "Extra"), ("Extra", "Extra"),
                  ("Example", "Example"), ("Note", "Note")],
}
READ_ALOUD_SKIP_TYPES = {"Pronunciation", "Spelling"}

# The TTS voice is English, so drop Chinese/CJK text and emoji/symbols (which
# `say` would read out by name) before speaking.
_CJK_RE = re.compile(r"[　-〿㐀-鿿豈-﫿＀-￯]+")
_SYMBOL_RE = re.compile(r"[←-⇿⌀-⏿①-➿⬀-⯿"
                        r"\U0001F000-\U0001FAFF️‍]")


def _speakable(s):
    """Plain English text to speak for a field's HTML, or None if nothing left."""
    s = re.sub(r"\[sound:[^\]]*\]", " ", s or "")
    s = re.sub(r'<a class="yg".*?</a>', " ", s)
    s = re.sub(_CLOZE_RE, r"\1", s)                      # fill in cloze answers
    s = re.sub(r"(?i)<br\s*/?>|</(li|div|p)>", ". ", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = s.replace("❌", ". Wrong: ").replace("✅", " correct ").replace("≈", " about ")
    s = re.sub(r"(\d)\s*[–—-]\s*(\d)", r"\1 to \2", s)       # 10,000–99,999
    s = _SYMBOL_RE.sub(" ", _CJK_RE.sub(" ", s))
    s = re.sub(r"\(\s*[-—,.;:=/]*\s*\)", " ", s)         # parens emptied by stripping
    s = s.replace("·", ". ").replace("•", ". ").replace(" / ", " or ").replace(" = ", ": ")
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([.,;:!?])(\s*[.,;:])+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip(" .,;:—-=")
    return s if re.search(r"[A-Za-z]", s) else None


def _norm_spoken(text):  # "a circuit" ~ "circuit" when comparing to term audio
    return re.sub(r"^(a|an|the|to)-", "", _slug(text))


def _read_aloud_plan(model, fields):
    """[(source, target, text)] still to be read aloud for a note (idempotent)."""
    if fields.get("Type", "") in READ_ALOUD_SKIP_TYPES:
        return []
    plan = []
    for src, dst in READ_ALOUD_FIELDS.get(model, []):
        cur = fields.get(dst, "") or ""
        if f"[sound:acc-ra-{src.lower()}-" in cur:
            continue                                     # already done
        if src == "Front" and "[sound:" in (fields.get("Front") or ""):
            continue                                     # listening card: has front audio
        text = _speakable(fields.get(src, ""))
        if not text:
            continue
        # Skip when the field's existing term audio already says the same thing.
        spoken = re.findall(r"\[sound:acc-(?!ra-)(.+?)-[0-9a-f]{10}\.m4a\]", cur)
        if any(_norm_spoken(sp) == _norm_spoken(text) for sp in spoken):
            continue
        plan.append((src, dst, text))
    return plan


def _apply_read_aloud(fields, plan, voice):
    """Synthesize the plan; return {field: new value} for the changed fields."""
    out = {}
    for src, dst, text in plan:
        fn = _synth_and_store(text, voice, prefix=f"acc-ra-{src.lower()}")
        if fn:
            cur = out.get(dst, fields.get(dst, "") or "")
            out[dst] = (cur + " " if cur else "") + f"[sound:{fn}]"
    return out


# Wrap each bare [sound:file] in a labelled pill (see .sl CSS / AUDIO_JS). The
# label comes from the filename: acc-ra-<field>-… is that field's read-aloud
# clip; any other acc-… clip is the term itself.
AUDIO_LABELS = {"front": "question", "back": "answer", "text": "sentence",
                "extra": "explanation", "example": "example", "note": "note",
                "clue": "word"}
_BARE_SOUND_RE = re.compile(r'(<span class="sl"[^>]*>)?\[sound:([^\]]+)\]')


def _audio_label(fn):
    m = re.match(r"acc-ra-([a-z]+)-", fn)
    if m:
        return AUDIO_LABELS.get(m.group(1), m.group(1))
    return "term" if fn.startswith("acc-") else "audio"


def _label_sounds(value):
    """Field HTML with every bare [sound:] wrapped in a pill (idempotent)."""
    def wrap(m):
        if m.group(1):
            return m.group(0)
        fn = m.group(2)
        return (f'<span class="sl" data-l="{_audio_label(fn)}" '
                f'data-src="{html.escape(fn, quote=True)}">[sound:{fn}]</span>')
    return _BARE_SOUND_RE.sub(wrap, value or "")


def _apply_media(card, note, voice, enable, read_aloud=True):
    model = note["modelName"]
    is_cloze = model == CLOZE_MODEL
    default_field = ("Clue" if model == SPELLING_MODEL
                     else "Extra" if is_cloze else "Back")

    family = (card.get("family") or "").lower()
    # Pronunciation cards default to including both audio and a Youglish link.
    if family == "pronunciation":
        card = {**card}
        card.setdefault("tts", True)
        card.setdefault("youglish", True)
    # Spelling cards play the word on the front (Clue) so you can spell it — no
    # Youglish (that's for the matching pronunciation card).
    elif family == "spelling":
        card = {**card}
        card.setdefault("tts", card.get("word") or True)

    # Youglish link (real-speaker pronunciation fallback). "youglish": true ->
    # auto-derive the term; a string -> use it; a dict -> {term?, accent?, field?}.
    yg = card.get("youglish")
    if yg:
        spec = yg if isinstance(yg, dict) else {}
        term = spec.get("term") or (yg if isinstance(yg, str) else _card_term(card))
        if spec.get("url") or term:
            _embed(note, spec.get("field", default_field),
                   _youglish_link(term, spec.get("accent", "us"), spec.get("url")),
                   prepend=False)

    # Audio. "tts": true -> auto-derive the spoken term; a string/dict/list ->
    # speak that text. (Youglish uses first-term; speech joins co-highlighted parts.)
    tts = card.get("tts")
    if tts and enable:
        if tts is True:
            term = _card_term(card, youglish=False)
            specs = [{"text": term}] if term else []
        else:
            specs = [tts] if isinstance(tts, (str, dict)) else tts
        for spec in specs:
            if isinstance(spec, str):
                spec = {"text": spec}
            fn = _synth_and_store(spec["text"], spec.get("voice", voice))
            if fn:
                _embed(note, spec.get("field", default_field),
                       f"[sound:{fn}]", spec.get("prepend", False))

    for spec in card.get("audio", []):  # existing files by path or url
        params = {"filename": spec.get("filename")
                  or f"acc-{_slug(spec.get('path') or spec['url'])}"}
        if spec.get("path"):
            params["path"] = spec["path"]
        else:
            params["url"] = spec["url"]
        fn = invoke("storeMediaFile", **params)
        _embed(note, spec.get("field", default_field),
               f"[sound:{fn}]", spec.get("prepend", False))

    # Read every field aloud (after term audio, so duplicates are detected).
    if enable and read_aloud and card.get("read_aloud", True):
        note["fields"].update(_apply_read_aloud(
            note["fields"], _read_aloud_plan(model, note["fields"]), voice))

    for k, v in note["fields"].items():
        if "[sound:" in v:
            note["fields"][k] = _label_sounds(v)


def cmd_push(args):
    _pre_sync(args)
    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    deck = args.deck or data.get("deck") or DEFAULT_DECK
    voice = args.voice or DEFAULT_VOICE
    enable_media = not args.no_media
    cards = data["notes"]
    notes = [_build_note(c, deck) for c in cards]
    for d in sorted({n["deckName"] for n in notes}):  # ensure target decks/subdecks exist
        invoke("createDeck", deck=d)

    # canAddNotesWithErrorDetail flags duplicates / invalid notes up front.
    # Dedup keys off the first field (unaffected by audio), so check BEFORE
    # generating media — no wasted TTS or orphan media for skipped notes.
    check = invoke("canAddNotesWithErrorDetail", notes=notes)
    addable, skipped = [], []
    for card, note, chk in zip(cards, notes, check):
        (addable if chk["canAdd"] else skipped).append((card, note, chk))

    for card, note, _ in addable:
        _apply_media(card, note, voice, enable_media,
                     read_aloud=not args.no_read_aloud)

    added_ids = invoke("addNotes", notes=[n for _, n, _ in addable]) if addable else []
    added = sum(1 for i in added_ids if i)

    decks = sorted({n["deckName"] for n in notes})
    print(f"Deck(s): {', '.join(decks)}")
    print(f"Added: {added}/{len(notes)} notes")
    for _, note, chk in skipped:
        label = note["fields"].get("Front") or note["fields"].get("Text", "")
        print(f"  skipped: {chk.get('error','?')} — {label[:60]}")

    _post_sync(args)


# Which existing notes `enrich` touches: vocab/idiom families with a single
# clear term. Concept/grammar/pronunciation-rule/map cards are left alone.
ENRICH_INCLUDE = {"idiom", "vocabulary", "phrasal-verb", "collocation", "adjective", "noun"}
ENRICH_EXCLUDE = {"concept", "vocabulary-map", "grammar", "pronunciation", "linking", "multimedia"}


def cmd_enrich(args):
    """Add pronunciation audio and/or Youglish links to *existing* vocab/idiom
    notes in a deck. Applies by default; pass --dry-run to preview only."""
    _pre_sync(args)              # sync before reading so the plan isn't stale
    deck = args.deck or DEFAULT_DECK
    both = not args.audio and not args.youglish
    do_audio, do_yg = args.audio or both, args.youglish or both
    voice = args.voice or DEFAULT_VOICE

    info = invoke("notesInfo", notes=invoke("findNotes", query=f'deck:"{deck}"'))
    plan, skipped = [], 0
    for n in info:
        tags = set(n["tags"])
        fields = {k: v["value"] for k, v in n["fields"].items()}
        is_cloze = n["modelName"] == CLOZE_MODEL
        if (fields.get("Type", "") == "Concept" or (tags & ENRICH_EXCLUDE)
                or not (tags & ENRICH_INCLUDE)):
            skipped += 1
            continue
        has_audio = any("[sound:" in v for v in fields.values())
        has_yg = any('class="yg"' in v for v in fields.values())
        a_term = _term(fields, is_cloze, youglish=False) if (do_audio and not has_audio) else None
        y_term = _term(fields, is_cloze, youglish=True) if (do_yg and not has_yg) else None
        if not (a_term or y_term):
            skipped += 1
            continue
        field = "Extra" if is_cloze else "Back"
        plan.append((n["noteId"], field, fields.get(field, ""), a_term, y_term))

    print(f'Deck "{deck}": {len(info)} notes · enrich {len(plan)} · skip {skipped}')
    for _, field, _, a, y in plan:
        bits = ([f"🔊 {a}"] if a else []) + ([f"🔎 {y}"] if y else [])
        print(f"  [{field:5}] " + "  ".join(bits))
    if not plan:
        print("Nothing to do — eligible cards already enriched.")
        return
    if args.dry_run:
        print("\n(dry run — omit --dry-run to write)")
        return

    print("\nApplying...")
    for nid, field, cur, a_term, y_term in plan:
        val = cur
        if a_term:
            fn = _synth_and_store(a_term, voice)
            if fn:
                val = (val + " " if val else "") + f"[sound:{fn}]"
        if y_term:
            val = (val + " " if val else "") + _youglish_link(y_term)
        invoke("updateNoteFields", note={"id": nid, "fields": {field: val}})
    print(f"Updated {len(plan)} notes.")
    _post_sync(args)


def cmd_read_aloud(args):
    """Retrofit per-field read-aloud audio onto *existing* notes in a deck.
    Idempotent; applies by default, --dry-run to preview."""
    _pre_sync(args)
    deck = args.deck or DEFAULT_DECK
    voice = args.voice or DEFAULT_VOICE
    query = f'deck:"{deck}"' + (f" ({args.query})" if args.query else "")
    info = invoke("notesInfo", notes=invoke("findNotes", query=query))
    plan = []
    for n in info:
        fields = {k: v["value"] for k, v in n["fields"].items()}
        p = _read_aloud_plan(n["modelName"], fields)
        if p:
            plan.append((n["noteId"], fields, p))
    clips = sum(len(p) for _, _, p in plan)
    print(f'{query}: {len(info)} notes · {len(plan)} to update · {clips} clips')
    for _, _, p in plan[:20] if args.dry_run else []:
        for src, dst, text in p:
            print(f"  [{src:7}→{dst:10}] {text[:90]}")
    if not plan or args.dry_run:
        print("Nothing to do." if not plan else "\n(dry run — omit --dry-run to write)")
        return
    for i, (nid, fields, p) in enumerate(plan, 1):
        changed = {k: _label_sounds(v)
                   for k, v in _apply_read_aloud(fields, p, voice).items()}
        if changed:
            invoke("updateNoteFields", note={"id": nid, "fields": changed})
        if i % 25 == 0:
            print(f"  {i}/{len(plan)} notes done", flush=True)
    print(f"Updated {len(plan)} notes ({clips} clips).")
    _post_sync(args)


def cmd_label_audio(args):
    """Wrap every bare [sound:] in existing notes in a labelled pill, so the
    template shows a label and builds an HTML5 player for it. Idempotent."""
    _pre_sync(args)
    deck = args.deck or DEFAULT_DECK
    query = f'deck:"{deck}"' + (f" ({args.query})" if args.query else "")
    info = invoke("notesInfo", notes=invoke("findNotes", query=query))
    plan = []
    for n in info:
        changed = {}
        for k, v in n["fields"].items():
            new = _label_sounds(v["value"])
            if new != v["value"]:
                changed[k] = new
        if changed:
            plan.append((n["noteId"], changed))
    print(f"{query}: {len(info)} notes · {len(plan)} to label")
    if not plan or args.dry_run:
        print("Nothing to do." if not plan else "(dry run — omit --dry-run to write)")
        return
    for nid, changed in plan:
        invoke("updateNoteFields", note={"id": nid, "fields": changed})
    print(f"Labelled {len(plan)} notes.")
    _post_sync(args)


def cmd_sync(_args):
    invoke("sync")
    print("Synced to AnkiWeb.")


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="ankicli", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--deck", help="override deck name")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping").set_defaults(func=cmd_ping)
    setup_p = sub.add_parser("setup")
    setup_p.add_argument("--no-pre-sync", action="store_true",
                         help="skip the pre-sync pull from AnkiWeb")
    setup_p.add_argument("--no-sync", action="store_true",
                         help="skip the post-sync push to AnkiWeb")
    setup_p.set_defaults(func=cmd_setup)
    sp = sub.add_parser("push")
    sp.add_argument("file")
    sp.add_argument("--no-sync", action="store_true",
                    help="skip the post-sync push to AnkiWeb (on by default)")
    sp.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    sp.add_argument("--voice", help="macOS TTS voice name (default: the system voice)")
    sp.add_argument("--no-media", action="store_true", help="skip TTS/audio generation")
    sp.add_argument("--no-read-aloud", action="store_true",
                    help="don't add per-field read-aloud audio (on by default)")
    sp.set_defaults(func=cmd_push)
    rp = sub.add_parser("read-aloud", help="add per-field audio to existing notes")
    rp.add_argument("--query", help="extra Anki search to narrow the notes, e.g. 'added:1'")
    rp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="preview only; don't write (applies by default)")
    rp.add_argument("--no-sync", action="store_true",
                    help="skip the post-sync push to AnkiWeb (on by default)")
    rp.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    rp.add_argument("--voice", help="macOS TTS voice name (default: the system voice)")
    rp.set_defaults(func=cmd_read_aloud)
    lp = sub.add_parser("label-audio", help="label existing audio buttons + add players")
    lp.add_argument("--query", help="extra Anki search to narrow the notes")
    lp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="preview only; don't write (applies by default)")
    lp.add_argument("--no-sync", action="store_true",
                    help="skip the post-sync push to AnkiWeb (on by default)")
    lp.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    lp.set_defaults(func=cmd_label_audio)
    ep = sub.add_parser("enrich", help="add audio/Youglish to existing vocab cards")
    ep.add_argument("--audio", action="store_true", help="add TTS audio")
    ep.add_argument("--youglish", action="store_true", help="add Youglish links")
    ep.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="preview only; don't write (applies by default)")
    ep.add_argument("--no-sync", action="store_true",
                    help="skip the post-sync push to AnkiWeb (on by default)")
    ep.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    ep.add_argument("--voice", help="macOS TTS voice name (default: the system voice)")
    ep.set_defaults(func=cmd_enrich)
    sub.add_parser("sync").set_defaults(func=cmd_sync)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
