"""Pixel-based check: OCR (tesseract on 250dpi renders of the PDF pages) vs corpus. Lists corpus tokens that OCR does not
reproduce (replace/delete ops), by section, for manual inspection against the rendered page.
Usage: python3 ocr_check.py corpus.json ocr_dir out.json"""
import json, re, sys, glob, difflib
o = json.load(open(sys.argv[1]))
ocr = ' '.join(open(f).read() for f in sorted(glob.glob(sys.argv[2] + '/p-*.txt')))
toks = lambda s: re.findall(r"[A-Za-z0-9]+", s.lower())
ot = toks(ocr); ct = []; owner = []
for k in sorted(o, key=int):
    t = [str(k)] + toks(o[k]['body']); ct += t; owner += [int(k)] * len(t)
sm = difflib.SequenceMatcher(None, ct, ot, autojunk=False)
rows = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag in ('replace', 'delete'):
        rows.append([owner[i1], ' '.join(ct[max(0, i1 - 3):i1]), ' '.join(ct[i1:i2]), ' '.join(ot[j1:j2])[:60]])
print('corpus tokens', len(ct), 'ocr tokens', len(ot), 'corpus-side differing ops', len(rows))
json.dump(rows, open(sys.argv[3], 'w'), indent=0)
for r in rows: print(r)
