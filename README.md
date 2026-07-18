# Anki Card Creator

A small, dependency-free toolkit for turning vocabulary and language material into
**high-quality Anki flashcards** — grounded in memory science, styled with clean HTML,
and enriched with pronunciation audio and pronunciation links. Cards are authored as
JSON and pushed into Anki over [AnkiConnect](https://ankiweb.net/shared/info/2055492159).

The guiding idea: **never generate word→translation cards only** (the single biggest
flashcard failure mode). Mix *card families* — recall, recognition, context/cloze,
concept, vocabulary-map — and keep every item in real context. The full methodology is
in [`anki-cards.md`](anki-cards.md).

## Features

- **Three styled note types** (Basic, native Cloze, and a **Spelling** type that uses
  Anki's type-in-the-answer to grade spelling letter-by-letter), dark-mode aware.
- **Pronunciation audio** — auto-generated with the macOS system voice (`say` → `.m4a`),
  stored in Anki and embedded as `[sound:…]`.
- **Youglish links** — one click to hear real speakers say the term on YouTube; a
  fallback when synthetic TTS is off.
- **Pronunciation-breakdown cards** (`family: "pronunciation"`) — IPA, syllable-by-
  syllable breakdown, learner-specific tips, and a memory hook, with audio + Youglish
  auto-attached.
- **Spelling-check cards** (`family: "spelling"`) — hear the word + a meaning clue, type
  the spelling, and Anki grades it letter-by-letter.

Pronunciation and spelling cards **auto-route** to a `…::Pronunciation & Spelling`
subdeck so you can drill them separately from vocabulary.
- **`enrich`** — retrofit audio + Youglish onto vocab cards already in a deck (idempotent,
  dry-run by default).
- **Pre-sync** — pulls the latest from AnkiWeb before writing, so you never create sync
  conflicts.

## Requirements

- [Anki](https://apps.ankiweb.net/) running with the **AnkiConnect** add-on (code
  `2055492159`) on `http://127.0.0.1:8765`.
- Python 3 (standard library only — no `pip install`).
- Audio generation uses macOS `say` + `afconvert` (optional; skip with `--no-media`).

## Quick start

```bash
python3 ankicli.py ping                 # check AnkiConnect is reachable
python3 ankicli.py setup                # create the deck + 2 styled note types
python3 ankicli.py push cards/example.json --sync
```

Then a standalone helper for one-off audio:

```bash
python3 tts.py "piece of cake"          # makes an .m4a, drops it in Anki's media folder,
                                        # prints (and clipboard-copies) the [sound:…] label
```

## Commands

| Command | What it does |
|---|---|
| `ping` | Check AnkiConnect is reachable |
| `setup` | Create the deck + two styled note types (idempotent; re-run to restyle) |
| `push <file> [--sync]` | Add notes from a cards JSON file |
| `enrich [--audio] [--youglish] [--apply] [--sync]` | Retrofit pronunciation onto existing vocab cards (dry-run unless `--apply`) |
| `sync` | Sync to AnkiWeb |

`setup` / `push` / `enrich` pre-sync from AnkiWeb first; pass `--no-pre-sync` to skip.

## Cards JSON

See [`cards/example.json`](cards/example.json) for a worked example. Per note: a `family`,
then `front`/`back` (Basic) **or** `text` (Cloze), plus optional `example`, `note`,
`source`, `tags`, and pronunciation keys `tts` / `youglish`.

```json
{ "deck": "AnkiCardCreator",
  "notes": [
    { "family": "recall",
      "front": "Idiom: something very easy to do.",
      "back": "a <span class=\"hl\">piece of cake</span>",
      "example": "The exam was a piece of cake.",
      "tags": ["english", "idiom"], "tts": true, "youglish": true },
    { "family": "context",
      "text": "Don't worry, the setup is a {{c1::piece of cake}}.",
      "extra": "= very easy" }
  ] }
}
```

Field values are HTML: `<span class="hl">` (highlight the target term), `<span class="hl2">`
(secondary), `<code>` (grammar patterns), plus `<b>`/`<i>`/`<br>`.

## License

MIT — see [LICENSE](LICENSE).
