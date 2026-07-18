#!/usr/bin/env python3
"""ankicli — push methodology-driven flashcards into Anki via AnkiConnect.

Division of labor:
  * Claude reads source material (transcripts, docs, user input) and writes a
    cards JSON file following the anki-cards.md methodology.
  * This CLI mechanically creates the deck + styled note types, adds the notes,
    and (optionally) syncs to AnkiWeb.

No third-party dependencies — stdlib only. Requires Anki running with the
AnkiConnect add-on (code 2055492159) listening on http://127.0.0.1:8765.

Usage:
    python3 ankicli.py setup                 # create deck + note types (idempotent)
    python3 ankicli.py push cards.json       # add notes from a cards file
    python3 ankicli.py push cards.json --sync # add, then sync to AnkiWeb
    python3 ankicli.py enrich --apply --sync # add audio+Youglish to existing vocab cards
    python3 ankicli.py sync                  # sync only
    python3 ankicli.py ping                  # check AnkiConnect is reachable

`enrich` retrofits pronunciation onto notes already in a deck: it selects
vocab/idiom cards (skipping concept/grammar/rule/map cards), extracts each
card's term, and appends TTS audio and/or a Youglish link — skipping any note
that already has them. Dry-run unless --apply; --audio / --youglish do just one
(default: both).

setup/push/enrich first run a **pre-sync** (AnkiConnect `sync`) so they operate
on the latest collection from AnkiWeb rather than a stale local copy — this
avoids sync conflicts. Pass --no-pre-sync to skip it (offline / no AnkiWeb).

Cards JSON schema (see cards/example.json):
    {
      "deck": "AnkiCardCreator",              # optional; --deck flag overrides
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
Default accent is US. The link is offline/free and is added even under
`--no-media`.
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
"""

BASIC_FRONT = (
    "{{#Type}}<div class=\"tag\">{{Type}}</div>{{/Type}}\n"
    "<div class=\"q\">{{Front}}</div>"
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


def cmd_ping(_args):
    print(f"AnkiConnect reachable — version {invoke('version')}")


def _ensure_model(name, fields, front, back, is_cloze):
    if name in invoke("modelNames"):
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
    print(f"  deck ready: {deck}")
    _ensure_model(BASIC_MODEL,
                  ["Front", "Back", "Example", "Note", "Source", "Type"],
                  BASIC_FRONT, BASIC_BACK, is_cloze=False)
    _ensure_model(CLOZE_MODEL,
                  ["Text", "Extra", "Example", "Note", "Source"],
                  CLOZE_FRONT, CLOZE_BACK, is_cloze=True)
    print("Setup complete.")


def _build_note(card, deck):
    family = (card.get("family") or "recall").lower()
    tags = card.get("tags") or []
    common = {"deckName": deck, "tags": tags,
              "options": {"allowDuplicate": False,
                          "duplicateScope": "deck"}}
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


def _synth_and_store(text, voice):
    """Speak `text` with macOS `say`, encode to m4a, store in Anki media.

    Returns the stored filename, or None if TTS tooling is unavailable.
    Filename is deterministic (hash of voice+text) so re-runs overwrite rather
    than duplicate.
    """
    if not (shutil.which("say") and shutil.which("afconvert")):
        print("  (skipping audio — macOS `say`/`afconvert` not found)")
        return None
    digest = hashlib.md5(f"{voice or 'default'}:{text}".encode()).hexdigest()[:10]
    filename = f"acc-{_slug(text)}-{digest}.m4a"
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


def _card_term(card):  # push-time helper: card JSON uses lowercase keys
    fields = {"Front": card.get("front", ""), "Back": card.get("back", ""),
              "Example": card.get("example", ""), "Text": card.get("text", "")}
    return _term(fields, "text" in card, youglish=True)


def _youglish_link(term, accent="us"):
    url = f"https://youglish.com/pronounce/{urllib.parse.quote(term)}/english/{accent}"
    return f'<a class="yg" href="{url}">🔎 Youglish</a>'


def _apply_media(card, note, voice, enable):
    is_cloze = note["modelName"] == CLOZE_MODEL
    default_field = "Extra" if is_cloze else "Back"

    # Youglish link (real-speaker pronunciation fallback). "youglish": true ->
    # auto-derive the term; a string -> use it; a dict -> {term?, accent?, field?}.
    yg = card.get("youglish")
    if yg:
        spec = yg if isinstance(yg, dict) else {}
        term = spec.get("term") or (yg if isinstance(yg, str) else _card_term(card))
        if term:
            _embed(note, spec.get("field", default_field),
                   _youglish_link(term, spec.get("accent", "us")), prepend=False)

    tts = card.get("tts")
    if tts and enable:
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


def cmd_push(args):
    _pre_sync(args)
    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    deck = args.deck or data.get("deck") or DEFAULT_DECK
    voice = args.voice or DEFAULT_VOICE
    enable_media = not args.no_media
    cards = data["notes"]
    notes = [_build_note(c, deck) for c in cards]

    # canAddNotesWithErrorDetail flags duplicates / invalid notes up front.
    # Dedup keys off the first field (unaffected by audio), so check BEFORE
    # generating media — no wasted TTS or orphan media for skipped notes.
    check = invoke("canAddNotesWithErrorDetail", notes=notes)
    addable, skipped = [], []
    for card, note, chk in zip(cards, notes, check):
        (addable if chk["canAdd"] else skipped).append((card, note, chk))

    for card, note, _ in addable:
        _apply_media(card, note, voice, enable_media)

    added_ids = invoke("addNotes", notes=[n for _, n, _ in addable]) if addable else []
    added = sum(1 for i in added_ids if i)

    print(f"Deck: {deck}")
    print(f"Added: {added}/{len(notes)} notes")
    for _, note, chk in skipped:
        label = note["fields"].get("Front") or note["fields"].get("Text", "")
        print(f"  skipped: {chk.get('error','?')} — {label[:60]}")

    if args.sync:
        invoke("sync")
        print("Synced to AnkiWeb.")


# Which existing notes `enrich` touches: vocab/idiom families with a single
# clear term. Concept/grammar/pronunciation-rule/map cards are left alone.
ENRICH_INCLUDE = {"idiom", "vocabulary", "phrasal-verb", "collocation", "adjective", "noun"}
ENRICH_EXCLUDE = {"concept", "vocabulary-map", "grammar", "pronunciation", "linking", "multimedia"}


def cmd_enrich(args):
    """Add pronunciation audio and/or Youglish links to *existing* vocab/idiom
    notes in a deck. Dry-run by default; pass --apply to write."""
    _pre_sync(args)              # sync before reading so the preview isn't stale
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
    if not args.apply:
        print("\n(dry run — pass --apply to write)")
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
    if args.sync:
        invoke("sync")
        print("Synced to AnkiWeb.")


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
    setup_p.set_defaults(func=cmd_setup)
    sp = sub.add_parser("push")
    sp.add_argument("file")
    sp.add_argument("--sync", action="store_true", help="sync after pushing")
    sp.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    sp.add_argument("--voice", help="macOS TTS voice name (default: the system voice)")
    sp.add_argument("--no-media", action="store_true", help="skip TTS/audio generation")
    sp.set_defaults(func=cmd_push)
    ep = sub.add_parser("enrich", help="add audio/Youglish to existing vocab cards")
    ep.add_argument("--audio", action="store_true", help="add TTS audio")
    ep.add_argument("--youglish", action="store_true", help="add Youglish links")
    ep.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ep.add_argument("--sync", action="store_true", help="sync after applying")
    ep.add_argument("--no-pre-sync", action="store_true",
                    help="skip the pre-sync pull from AnkiWeb")
    ep.add_argument("--voice", help="macOS TTS voice name (default: the system voice)")
    ep.set_defaults(func=cmd_enrich)
    sub.add_parser("sync").set_defaults(func=cmd_sync)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
