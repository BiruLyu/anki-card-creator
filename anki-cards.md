# Anki Card Creator

Create high-quality Anki flashcards grounded in memory science. Use this skill when the user wants to make Anki cards for vocabulary, language learning, or any subject.

## Trigger

Use this skill when the user:
- Asks to create, generate, or make Anki cards
- Wants to turn a word list, passage, or topic into flashcards
- Asks how to design flashcards for language learning or study

## Core Principles (from memory science)

### 1. Retrieval beats recognition
- **Recognition cards** (L2 front → L1 back) train passive reading/listening comprehension only
- **Recall cards** (L1 front → L2 back, or category prompts) force active retrieval and are far more effective for production
- Always generate a mix; never generate recognition cards exclusively

### 2. Card direction matters by level
- Beginner/intermediate: include L2→L1 recognition cards alongside L1→L2 recall cards
- Advanced: weight heavily toward L1→L2 and open-ended production cards

### 3. Context beats isolation
- Include the word in a collocation or phrase, not just in isolation (e.g., "make a decision", not just "decision")
- Sentence-completion cards (fill-in-the-blank) beat simple translation cards for real-world use
- Collocations anchor words to real usage patterns

### 4. Multiple memory routes
- Add a memorable example sentence (ideally personal or vivid)
- Add pronunciation hints for new scripts or tricky phonetics
- Add a mnemonic, image cue, or etymological note when useful
- Rich cards are retrieved through more pathways than bare translation cards

### 5. Semantic networks over isolated facts
- Group related vocabulary into vocabulary-map cards when appropriate
- Include synonym/antonym cards for high-frequency words
- Word-family cards (noun/verb/adjective forms) reduce total card count

### 6. Generation effect
- Encourage the user to write their own example sentences
- Flag which fields are best filled by the user personally (personal memory beats generic examples)

### 7. Spaced repetition discipline
- Prioritize: only card words the user is actively studying or has recently encountered
- Warn against mass-importing word lists — overwhelm undermines the system
- Recommend reviewing daily for new cards and letting Anki schedule the rest

## The Card Families

Generate cards from multiple families rather than defaulting to word+translation only:

| Family | Front example | Back example | Best for |
|--------|--------------|--------------|----------|
| **Recognition** | ghiaccio | ice (🧊) + sentence | Passive reading/listening |
| **Recall** | ice (concept) | ghiaccio — say it aloud | Active production |
| **Context** | "It's going to _____ tonight." (freeze) | gelare / congelare | Collocations, chunks |
| **Concept** | "When do you use 'da' vs 'di' in Italian?" | Rule + 2 examples | Grammar, patterns |
| **Multimedia** | [Audio clip front] | Written form + pronunciation note | Listening, phonetics |
| **Pronunciation** | the word/phrase (highlighted) | IPA + syllable breakdown + tips + memory hook (+ auto audio & Youglish) | Mastering how a word sounds |
| **Spelling** | 🔊 audio + meaning clue → *type it* | correct spelling (letter-diff) + tips | Testing spelling *production* |

### Pronunciation-breakdown cards

For learning the pronunciation of a specific word or phrase. Front = the target
(highlight it with `<span class="hl">…</span>` so audio/Youglish auto-derive it);
Back = a structured breakdown, wrapped in `<div class="pron">…</div>`:

- 📢 **IPA:** `<span class="ipa">/…/</span>` (mark US vs UK if they differ)
- 🧩 **Syllable by Syllable:** one `<li>` per syllable — describe each sound with a
  common English word or simple analogy ("rhymes with…", "like the *a* in *cat*").
- 💡 **Pronunciation Tips:** sounds tricky for **Mandarin speakers** specifically
  (θ/ð, r vs l, final consonants, v/w); accent differences; silent letters;
  unusual stress; liaison (esp. French); common mispronunciations.
- ✍️ **Spelling Tips** (when spelling is tricky): how to remember the written form —
  silent/doubled letters, foreign patterns (`gi`→"j", `sci`→"sh"), commonly
  transposed letters, or breaking the word into familiar chunks.
- 🔁 **Memory Hook** (optional): a short rhyme, association, or mnemonic for the sound.

With `family: "pronunciation"`, the tool auto-adds TTS audio **and** a Youglish
link (no need to set `tts`/`youglish`). Pass `"youglish": {"url": "…getbyid…"}` to
use a specific clip instead of the auto search link. Style: `.ipa` renders the
transcription in monospace; `.pron` spaces the sections.

### Spelling-check cards

To test whether you can *produce* a spelling (retrieval, not recognition). Uses
Anki's native **type-in-the-answer**: the front plays the word + a meaning clue
(word hidden), you type it, and Anki grades it letter-by-letter.

```json
{ "family": "spelling", "word": "Prosciutto",
  "clue": "an Italian dry-cured ham",
  "tips": "Silent c in sci (=sh) + double t." }
```

`word` is plain text (Anki compares against it) and is auto-spoken on the front.

**Deck routing:** pronunciation and spelling cards are automatically placed in a
`<deck>::Pronunciation & Spelling` subdeck (kept separate from vocabulary). Connected
-speech / linking-rule cards are a pronunciation *concept* (not the pronunciation
family), so route them there explicitly with a file-level `"deck"` when you want them
alongside — e.g. `"deck": "AnkiCardCreator::Pronunciation & Spelling"`.

**Default pairing:** whenever you make a pronunciation card for a **tricky-to-spell**
word, also emit a companion spelling card by default (a tricky word → two cards).
A word is tricky if it has silent letters, doubled letters, non-phonetic/foreign
patterns (`ph`, `sci`→"sh", `gi`→"j", `ou`→"oo"), apostrophes/hyphens/odd
capitalization, or a commonly transposed form (`chipotle`, `entrepreneur`). Skip it
for regular, phonetic words written the way they sound (`popsicle`, `croutons`).

## Workflow

When invoked, follow these steps:

### Step 1 — Gather input
Ask (or infer from context):
- What language or subject?
- What is the user's current level (beginner / intermediate / advanced)?
- What word(s), phrase(s), or topic to card?
- Any specific cards they need (grammar point, collocations, etc.)?

If the user supplies a word list or passage directly, proceed without asking.

### Step 2 — Generate cards

For each target item, produce cards in this format:

```
---
Card Type: [Recognition | Recall | Context | Concept | Multimedia]
Front: [prompt]
Back: [answer + collocation/sentence + pronunciation hint if needed]
Note: [optional mnemonic, etymology, or personal-example prompt]
Tags: [language::italian, level::beginner, type::recall, topic::weather]
---
```

**Minimum card set per vocabulary item:**
- 1 Recall card (L1 → L2)
- 1 Context card (fill-in-the-blank or collocation)
- 1 Recognition card (L2 → L1) if user is beginner/intermediate

**Add when appropriate:**
- Synonym/antonym card for high-frequency items
- Concept card for grammar-heavy items
- Vocabulary-map card for a semantic cluster of 4+ related words

### Step 3 — Present and offer to refine

Show all generated cards clearly. Then offer:
- "Would you like me to add audio/pronunciation notes?"
- "Should I generate a vocabulary-map card connecting these words?"
- "Which example sentences would you like to personalize?"

### Step 4 — Export format (optional)

If the user wants to import into Anki, format as tab-separated values:
```
Front[TAB]Back[TAB]Tags
```

Or as an Anki-compatible note list they can paste into a CSV import.

## What NOT to do

- Do not generate only word→translation cards — this is the single biggest failure mode
- Do not card every word in a passage — prompt the user to select high-priority items first
- Do not add so many fields to one card that reviewing becomes overwhelming
- Do not skip the Tags field — good tagging makes deck management possible

## Example output

**Input:** User is learning Italian, intermediate level, wants cards for: ghiaccio, fare una decisione, pioggia torrenziale

---
**Card 1**
Type: Recall
Front: ice (the substance, weather/drinks context)
Back: ghiaccio [GYAH-cho] — "C'è ghiaccio sul marciapiede." (There's ice on the sidewalk.)
Note: Think "glacier" → ghiaccio. Personal prompt: add a sentence about ice in your life.
Tags: italian, intermediate, recall, weather, noun

**Card 2**
Type: Context
Front: "Ho bisogno di _____ una decisione." (I need to make a decision.)
Back: fare
Note: "Fare una decisione" — always collocates with "fare", not "prendere" in this pattern.
Tags: italian, intermediate, context, collocation, verb

**Card 3**
Type: Recognition
Front: pioggia torrenziale
Back: torrential rain — "Ieri c'era una pioggia torrenziale." 🌧️
Tags: italian, intermediate, recognition, weather, noun

**Card 4**
Type: Vocabulary Map
Front: Italian weather vocabulary — name as many as you can
Back: [map] sole ↔ pioggia ↔ neve ↔ ghiaccio ↔ vento ↔ nebbia ↔ grandine
Tags: italian, intermediate, recall, weather, vocabulary-map
