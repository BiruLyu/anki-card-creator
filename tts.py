#!/usr/bin/env python3
"""tts.py — make a pronunciation .m4a and drop it into Anki's media folder.

Generates audio from text with the macOS system voice (or a named voice),
copies the file straight into your Anki `collection.media` folder, and prints
the `[sound:filename.m4a]` label to paste into any card field. The label is
also copied to your clipboard (pbcopy) for convenience.

No AnkiConnect needed — it writes the file directly. Anki picks up new media
on its next sync / "Tools > Check Media".

Usage:
    python3 tts.py "would you like some water"
    python3 tts.py "famished" --voice Daniel
    python3 tts.py "in season" --name in-season      # custom base filename
    echo "hello there" | python3 tts.py              # text from stdin

    say -v '?'                                        # list available voices

Requires macOS `say` + `afconvert` (both built in).
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile


def slug(text):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:40] or "audio"


def find_media_dir():
    """Locate the Anki collection.media folder (override with $ANKI_MEDIA)."""
    env = os.environ.get("ANKI_MEDIA")
    if env:
        return env
    base = os.path.expanduser("~/Library/Application Support/Anki2")
    if not os.path.isdir(base):
        sys.exit(f"Anki folder not found: {base}\nSet $ANKI_MEDIA to your collection.media path.")
    cands = [os.path.join(base, p, "collection.media") for p in os.listdir(base)
             if os.path.isdir(os.path.join(base, p, "collection.media"))]
    if not cands:
        sys.exit(f"No collection.media folder under {base}. Set $ANKI_MEDIA.")
    # Prefer a profile literally named "User 1", else the first found.
    for c in cands:
        if os.path.basename(os.path.dirname(c)) == "User 1":
            return c
    return cands[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?", help="text to speak (or pipe via stdin)")
    ap.add_argument("--voice", help="macOS voice name (default: system voice; `say -v '?'` lists them)")
    ap.add_argument("--name", help="custom base filename (default: slug of the text)")
    ap.add_argument("--media", help="Anki collection.media path (else auto-detected / $ANKI_MEDIA)")
    args = ap.parse_args()

    text = (args.text if args.text is not None else sys.stdin.read()).strip()
    if not text:
        sys.exit("No text given. Example: python3 tts.py \"bow out\"")

    if not (shutil.which("say") and shutil.which("afconvert")):
        sys.exit("Needs macOS `say` and `afconvert` (both built in on macOS).")

    media_dir = args.media or find_media_dir()
    digest = hashlib.md5(f"{args.voice or 'default'}:{text}".encode()).hexdigest()[:10]
    base = slug(args.name) if args.name else slug(text)
    filename = f"acc-{base}-{digest}.m4a"
    dest = os.path.join(media_dir, filename)

    with tempfile.TemporaryDirectory() as d:
        aiff, m4a = os.path.join(d, "a.aiff"), os.path.join(d, "a.m4a")
        say_cmd = ["say"] + (["-v", args.voice] if args.voice else []) + ["-o", aiff, text]
        subprocess.run(say_cmd, check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", aiff, m4a],
                       check=True)
        shutil.copyfile(m4a, dest)

    label = f"[sound:{filename}]"
    # Copy the label to the clipboard (best-effort).
    try:
        subprocess.run(["pbcopy"], input=label.encode(), check=True)
        clip = "  (copied to clipboard)"
    except Exception:
        clip = ""

    print(f"✓ saved: {dest}")
    print(f"  voice: {args.voice or 'system default'}")
    print(f"\nPaste this into a card field:{clip}\n\n  {label}\n")


if __name__ == "__main__":
    main()
