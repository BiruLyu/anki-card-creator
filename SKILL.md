---
name: anki-cards
description: Create high-quality Anki flashcards from any material (transcripts, docs, passages, word lists, or user input) using memory-science principles, and push them into Anki via AnkiConnect with nicely styled HTML. Use when the user wants to make, generate, or import Anki cards, turn material into flashcards, or study vocabulary/a topic with spaced repetition.
---

# Anki Card Creator

Turn source material into high-quality Anki flashcards grounded in memory
science, then push them into Anki (styled HTML) via AnkiConnect. You (Claude)
read the material and author the cards as JSON; a bundled CLI does the
mechanical add + sync.

## When to use
The user asks to create/generate/make Anki cards, turn a word list / passage /
transcript / doc into flashcards, or study a topic with spaced repetition.

---

## Core principles (memory science)

1. **Retrieval beats recognition.** Recall cards (concept → produce the term)
   force active retrieval; recognition cards (term → meaning) only train passive
   comprehension. Always generate a mix — never recognition-only.
2. **Direction by level.** Beginner/intermediate: include recognition alongside
   recall. Advanced: weight toward recall + open-ended production.
3. **Context beats isolation.** Card words inside a collocation/sentence, not
   bare. Fill-in-the-blank (cloze) beats plain translation for real use.
4. **Multiple memory routes.** Add a vivid example, a mnemonic/etymology, or a
   pronunciation hint where useful. Rich cards are recalled through more paths.
5. **Semantic networks.** Group 4+ related items into a vocabulary-map card;
   add synonym/antonym and word-family cards for high-frequency items.
6. **Generation effect.** Prefer examples drawn from the user's own material;
   flag fields the user should personalize.
7. **Spaced-repetition discipline.** Card only high-value items — do **not**
   card every word in a passage. Warn against mass-importing; it causes overwhelm.

## The card families

| Family | Front | Back | Note type |
|--------|-------|------|-----------|
| **Recall** | concept / meaning | the term (+ example) | Basic |
| **Recognition** | the term | meaning (+ example) | Basic |
| **Context** | sentence with a `{{c1::blank}}` | (auto) + notes | **Cloze** |
| **Concept** | a rule / "X vs Y" question | rule + 2 examples | Basic |
| **Multimedia** | audio/image cue | written form + hint | Basic |
| **Vocabulary map** | "name as many … as you can" | the cluster | Basic |
| **Pronunciation** | the word/phrase (highlighted) | IPA + syllable breakdown + tips + hook | Basic |
| **Spelling** | 🔊 audio + meaning clue → *type the word* | correct spelling (letter-diff) + tips | **Spelling** (type-answer) |

**Minimum set per target item:** 1 Recall + 1 Context. Add 1 Recognition for
beginner/intermediate. Add Concept for grammar/confusables, Vocabulary-map for a
cluster of 4+, Pronunciation for a word whose *sound* is the point.

### Pronunciation-breakdown cards (`family: "pronunciation"`)

For mastering how a specific word/phrase sounds. **Front** = the target,
highlighted with `<span class="hl">…</span>` so audio + Youglish auto-derive it.
**Back** = a structured breakdown wrapped in `<div class="pron">…</div>`:

```
<div class="pron">
  <div>📢 <b>IPA:</b> <span class="ipa">/ˈθɜːr.ə.li/</span> (US)</div>
  <div>🧩 <b>Syllable by Syllable:</b>
    <ul><li><b>thor</b> — soft "th" (tongue between teeth, like <i>think</i>) + vowel like "her"</li>
        <li><b>ough</b> → a quick unstressed "uh"</li>
        <li><b>ly</b> — like "lee"</li></ul></div>
  <div>💡 <b>Pronunciation Tips:</b>
    <ul><li>Mandarin speakers: θ has no equivalent — tongue between teeth, don't use "s"/"f"</li>
        <li>Stress the <b>first</b> syllable; 3 syllables, not 4</li></ul></div>
  <div>✍️ <b>Spelling Tips:</b>
    <ul><li>Silent letters / doubled letters / unusual patterns worth flagging</li></ul></div>
  <div>🔁 <b>Memory Hook:</b> "THOR-oughly" — Thor does it thoroughly 🔨</div>
</div>
```

Content guidance:
- **📢 IPA** — mark US vs UK when they differ.
- **🧩 Syllables** — one `<li>` each; describe each sound with a common English word or
  simple analogy ("rhymes with…", "like the *a* in *cat*").
- **💡 Tips** — call out sounds tricky for **Mandarin speakers specifically** (θ/ð, r vs
  l, v/w, final consonants), accent differences, silent letters, unusual stress, liaison
  (esp. French), and common mispronunciations.
- **✍️ Spelling Tips** *(include when spelling is tricky)* — how to remember the written
  form: silent/doubled letters (`Prosciutto` — silent *c*, double *t*), foreign patterns
  (`gi`→"j", `sci`→"sh"), letter order often transposed (`chipotle` not "chipolte"),
  syllable→letter mnemonics, or breaking the word into familiar chunks.
- **🔁 Memory Hook** *(optional)* — a rhyme/association/mnemonic for the sound.

`family: "pronunciation"` **auto-adds TTS audio and a Youglish link** — you don't set
`tts`/`youglish` yourself (override by setting either explicitly). To point at a
**specific Youglish clip** instead of the auto search, pass
`"youglish": {"url": "https://youglish.com/getbyid/…"}`. `.ipa` styles the
transcription; `.pron` spaces the sections.

> **Default pairing — pronunciation + spelling.** Whenever you make a pronunciation
> card for a word whose **spelling is tricky**, also emit a companion **spelling**
> card (same word) by default. A word counts as tricky-to-spell if it has any of:
> silent letters (*Prosciutto*, *L'Occitane*), doubled letters (*burrata*, *Reggiano*),
> non-phonetic/foreign patterns (*ph*, *sci*→"sh", *gi*→"j", *ou*→"oo", *ch*),
> apostrophes / hyphens / unusual capitalization, or a commonly transposed/misspelled
> form (*chipotle*, *entrepreneur*). **Skip** the spelling card for regular, phonetic
> words that are written the way they sound (*popsicle*, *croutons*). The user can
> always ask for "pronunciation only" or "spelling too" to override.

### Spelling-check cards (`family: "spelling"`)

Tests whether the learner can *produce* a spelling (not just recognize it). Uses
Anki's native **type-in-the-answer** — the front plays the word + shows a meaning
clue (word hidden), the learner types it, and Anki grades it letter-by-letter.

```json
{ "family": "spelling",
  "word": "Prosciutto",                              // the answer you type (plain text, no HTML)
  "clue": "an Italian dry-cured ham, sliced thin",   // shown on the front (word hidden)
  "tips": "Silent <b>c</b> in <b>sci</b> (=\"sh\") + a double <b>t</b>.",  // shown on the back
  "tags": ["english", "spelling"] }
```

Audio of the word is **auto-added to the front** (from `word`) so you hear it, then
spell it — no Youglish (that belongs on the pronunciation card). `word` must be
**plain text** (Anki compares your typed answer to it). By default this is the
**companion** to a pronunciation card for any tricky-to-spell word (see the pairing
rule above) — so a tricky word yields *two* cards: pronunciation + spelling. Skip it
for regular, phonetic words.

> **Deck routing.** Cards auto-route into subdecks so each is studied at its own
> pace, leaving the base deck an empty container: `pronunciation` and `spelling`
> cards go to `<deck>::Pronunciation & Spelling`, and **every other family** goes to
> `<deck>::Main` (give `::Main` its own new-cards/day limit in Anki's deck options).
> Connected-speech / linking-rule cards are a pronunciation *concept* (not the
> pronunciation family), so to file them with the pronunciation set add a file-level
> `"deck": "AnkiCardCreator::Pronunciation & Spelling"` (or push `--deck …`).

---

## Workflow

### 1. Gather / infer
Subject or language; user level; which items to card. If given a passage or
list, proceed without asking. **Select high-value items** (idioms, collocations,
confusables, grammar patterns) — do not card every word; if the input is large,
propose a shortlist first.

### 2. Author cards as JSON
Write a cards file (default location: `cards/<name>.json` in the working
project, or the scratchpad if there's no natural home). Schema:

```json
{
  "deck": "AnkiCardCreator",
  "notes": [
    { "family": "recall",
      "front": "meaning / concept prompt",
      "back": "the <span class=\"hl\">term</span>",
      "example": "a sentence, ideally from the source",
      "note": "mnemonic / register / collocation",
      "source": "where it came from",
      "tags": ["subject", "topic::x"] },

    { "family": "context",
      "text": "A sentence with the target {{c1::blanked out}}.",
      "extra": "brief gloss shown on the back",
      "example": "optional extra example",
      "note": "optional", "source": "optional",
      "tags": ["subject", "collocation"] }
  ]
}
```

Mapping: `family: "context"` (or any note with a `text` field) → **Cloze** note
type; every other family → **Basic**. `deck` is optional (default
`AnkiCardCreator`; override per-file or with `--deck`).

**The front must be answerable on its own.** A cloze card's front is the
`text` field with the blank hidden — nothing else. Before writing one, cover
the target in your head and check: does the *rest of the sentence* actually
imply that word/phrase (grammar, logic, a collocation you'd complete, a
callback earlier in the sentence)? That's true for grammar-pattern and fixed-
collocation cards (subject-verb agreement, prepositions, "on someone's
___") — the sentence *is* the evidence.

It is **not** true for a sentence lifted verbatim from a book/transcript to
teach an arbitrary content word (a literary adjective, a one-off noun, slang)
— any number of words could grammatically fill that blank, so the card is
unsolvable without peeking at `extra`, which trains "flip immediately" instead
of retrieval. For these:
- Add a few words of paraphrase/definition **inside `text` itself** (still
  front-visible, outside the `{{c1::…}}` span) — e.g. `The bricks were old
  and {{c1::crumbly}} — they broke apart at the slightest touch.` — so the
  sentence now semantically implies the answer; or
- Use Anki's built-in cloze **hint**: `{{c1::crumbly::brittle, breaks apart
  easily}}` renders as a `[brittle, breaks apart easily]` placeholder on the
  front instead of `[...]`. Put a short (few-word) paraphrase there, in
  `text`, not in `extra` — `extra` is back-only and doesn't help the attempt.
- Never write a hint that contains the answer itself (or an unhyphenated
  inflection of it) — that just changes what gets copied from where.
- If neither is natural (the word is truly arbitrary trivia, e.g. a proper
  noun or a random fact), reconsider the family — a **recall** card
  (definition front → term back) tests the same knowledge honestly instead of
  faking a cloze.

`reference/example-cards.json` (next to this skill) is a full worked example —
22 cards across recall/recognition/context/concept/vocabulary-map families.

### 3. Style with HTML
Field values are rendered as HTML (dark-mode aware). Use:
- `<code>…</code>` — inline monospace; ideal for grammar patterns/prepositions
  (e.g. `rat on` vs `rat out`) or literal code.
- `<span class="hl">…</span>` — yellow highlight (use for the **target term**).
- `<span class="hl2">…</span>` — green highlight (secondary).
- `<pre><code>…</code></pre>` — code block. Also `<b>`, `<i>`, `<br>`.
Keep the target expression highlighted; put register/collocation info in `note`.

**Audio / pronunciation.** Add a `tts` key to any note to auto-generate spoken
audio (macOS `say` → `.m4a`, stored in Anki, embedded as `[sound:…]`):
```json
{ "family": "recall", "front": "…", "back": "…",
  "tts": "bow out" }                                  // audio on Back (Cloze: Extra)

{ "family": "multimedia", "front": "🔊 What do you hear?", "back": "bow out — to withdraw",
  "tts": [ { "text": "bow out", "field": "Front" },   // listening card: audio on the FRONT
           { "text": "I bowed out at the last minute.", "field": "Example" } ] }
```
Per-entry options: `field` (default Back / Cloze Extra), `voice`, `prepend`.
Use for **listening cards** (audio on Front, answer on Back) and
**pronunciation-check cards** (audio on Back so the learner self-checks). To
attach an existing audio file instead of TTS: `"audio": [{"path": "/abs/x.mp3",
"field": "Back"}]` (or `"url"`). Audio uses the macOS **system default voice**
unless overridden with `push --voice <name>` (`say -v '?'` lists names).
`push --no-media` skips audio. (Note: Siri voices are gated from the `say` CLI —
set the desired voice as the system voice in Spoken Content instead.)

**Youglish link.** Add `"youglish": true` to a note for a clickable link to
real-speaker pronunciations on YouTube — a good fallback when the TTS voice is
wrong. `true` auto-derives the term; a string uses an explicit query; a dict
`{"term":…, "accent":"uk", "field":"Back"}` overrides. Default accent US. Best
paired with `tts` on vocab/idiom cards (skip it on grammar/concept cards).

### 4. Push via the bundled CLI
The CLI is dependency-free (stdlib) and lives at
`~/.claude/skills/anki-cards/scripts/ankicli.py`. **Anki must be running with
the AnkiConnect add-on** (add-on code `2055492159`) on `http://127.0.0.1:8765`.

> **Canonical source:** this skill's `SKILL.md`, `reference/`, and `scripts/*.py`
> are symlinks into a local clone of the public repo
> [github.com/BiruLyu/anki-card-creator](https://github.com/BiruLyu/anki-card-creator)
> (wherever you cloned it; default `~/Tasks/anki-card-creator/`). Edit the tooling
> *and this doc* there (commit + push); the skill reflects changes automatically.
> Don't edit the symlinked files expecting a private copy.

```bash
CLI=~/.claude/skills/anki-cards/scripts/ankicli.py
python3 "$CLI" ping                       # verify AnkiConnect is reachable
python3 "$CLI" setup                      # create deck + 2 styled note types (idempotent; run once)
python3 "$CLI" push cards/<name>.json      # add notes (auto pre- + post-sync to AnkiWeb)
python3 "$CLI" push cards/<name>.json --no-sync   # add without the post-sync push
python3 "$CLI" enrich                      # retrofit audio+Youglish onto existing vocab cards (applies + syncs)
python3 "$CLI" enrich --dry-run            # preview only, don't write
python3 "$CLI" sync                       # sync only
```

`setup` also refreshes CSS/templates on the existing note types, so to restyle:
edit `CARD_CSS`/templates in the script and re-run `setup`. Sync requires the
user to be logged into AnkiWeb in the Anki desktop app.

**Auto-sync both ends (automatic).** `setup`, `push`, and `enrich` first pull the
latest from AnkiWeb (an AnkiConnect `sync`) so they act on the current collection,
not a stale local copy, and then push changes back up afterwards — keeping
desktop/phone/AnkiWeb in step and preventing conflicts. Skip either half with
`--no-pre-sync` / `--no-sync` (offline, or AnkiWeb not set up).

**`enrich`** retrofits pronunciation onto notes already in a deck — for cards
made before you added `tts`/`youglish`, or imported elsewhere. It selects
vocab/idiom cards (skips concept/grammar/rule/map cards), extracts each card's
term from its `.hl` highlight or cloze, and appends TTS audio and/or a Youglish
link, skipping any note that already has them (idempotent). It **applies by
default** (and post-syncs); pass `--dry-run` to preview without writing, and
`--audio` / `--youglish` to limit it to one (default: both).

### 5. Verify / report
Report how many notes were added vs skipped. **Duplicate handling:** the CLI
sets `allowDuplicate:false` scoped to the deck — Anki skips a note when its
**first field** (`Front` for Basic, `Text` for Cloze), with HTML stripped,
matches an existing note of the same type in that deck. Re-pushing an identical
file is a safe no-op. Caveat: dedup is on card content only — there is **no
memory of which source files were already processed**, so re-generating with
reworded fronts can create near-duplicates. If needed, spot-check with
AnkiConnect `findNotes`/`cardsInfo`.

## What NOT to do
- Don't generate only term→meaning cards (the single biggest failure mode).
- Don't card every word — shortlist high-priority items first.
- Don't overload one card with so many fields that review is a slog.
- Don't skip `tags` — they make deck management possible.
- Don't assume AnkiConnect is up — `ping` first and tell the user to open Anki
  (with the add-on) if it isn't.
- Don't blank an arbitrary content word out of a verbatim source sentence and
  call it done — if the remaining sentence can't imply the answer, add a
  paraphrase/cloze hint in `text` (see above) or switch to a recall card.

## Note types (created by `setup`)
- **`AnkiCardCreator Basic`** — fields `Front, Back, Example, Note, Source, Type`.
- **`AnkiCardCreator Cloze`** — fields `Text, Extra, Example, Note, Source`
  (native `{{c1::…}}` cloze).
Both share one dark-mode-aware stylesheet defined in the CLI's `CARD_CSS`.
