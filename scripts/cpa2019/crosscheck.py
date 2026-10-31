"""Independent cross-check: PyMuPDF line text (different library from pdfplumber extraction) vs corpus JSON, token-level diff.
Usage: python3 crosscheck.py SRC.pdf corpus_raw.json out_rows.json"""
import fitz, json, re, difflib, sys
doc = fitz.open(sys.argv[1]); o = json.load(open(sys.argv[2]))
rows = {}
for pi, pg in enumerate(doc):
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["text"].strip()]
            if not sp or max(s["size"] for s in sp) < 9.5: continue
            y = l["bbox"][1]
            if y < 62 or y > 790: continue
            rows.setdefault((pi, round(y / 3)), []).append((l["bbox"][0], ''.join(s["text"] for s in sp if s["size"] >= 9.5 or True)))
txt = [' '.join(t for x, t in sorted(rows[k])) for k in sorted(rows)]
full = '\n'.join(txt)
m = re.search(r'1\.\s*\(1\)\s*This Act may be called', full); full = full[m.start():]
toks = lambda s: re.findall(r"[A-Za-z0-9]+", s.lower())
ft = toks(full); ct = []; owner = []
for k in sorted(o, key=int):
    t = [str(k)] + toks(o[k]['body']); ct += t; owner += [int(k)] * len(t)
sm = difflib.SequenceMatcher(None, ct, ft, autojunk=False)
out = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag != 'equal':
        out.append([owner[min(i1, len(owner) - 1)], tag, ' '.join(ct[i1:i2])[:90], ' '.join(ft[j1:j2])[:90]])
print('tokens corpus/pymupdf', len(ct), len(ft), 'ratio', round(sm.ratio(), 5), 'diff ops', len(out))
json.dump(out, open(sys.argv[3], 'w'), indent=0)
for r in out[:70]: print(r)

# Heading check: every heading token must occur in the small-font (marginal note) text of the section's PDF page
# (PyMuPDF), and the heading's tokens must appear there in the same order.
small = {}
for pi, pg in enumerate(doc):
    ls = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if 7.0 <= s["size"] <= 8.6 and s["text"].strip(): ls.append((round(l["bbox"][1], 1), l["bbox"][0], s["text"]))
    ls.sort(); small[pi + 1] = toks(' '.join(t for _, _, t in ls))
bad = []
for k, v in o.items():
    ht = toks(v['heading']); pool = small.get(v['page'], []) + small.get(v['page'] + 1, [])
    it = iter(pool)
    if not ht or not all(any(w == x for x in it) for w in ht): bad.append((k, v['heading']))
print('heading rows not found in-order in marginal text of the section page:', len(bad)); print(bad)
