"""Extract Consumer Protection Act 2019 (Act 35 of 2019) from the Gazette of India Extraordinary PDF
(No. 54, 9 Aug 2019). Body words >= 9.5pt; marginal notes are 7.5-8.5pt words, grouped by vertical gap and
attached to the nearest section start on the same page.
Usage: python3 extract_cpa.py SRC.pdf OUT.json"""
import pdfplumber, re, json, sys
from collections import defaultdict
SRC = sys.argv[1]; OUT = sys.argv[2]
pdf = pdfplumber.open(SRC)
body, margin = [], []
for pi, pg in enumerate(pdf.pages):
    for w in pg.extract_words(extra_attrs=['size']):
        if w['top'] < 62 or w['top'] > 790: continue
        (body if w['size'] >= 9.5 else margin).append((pi, w))
rows = {}
for pi, w in body: rows.setdefault((pi, round(w['top'] / 3)), []).append(w)
L = []
for k in sorted(rows):
    ws = sorted(rows[k], key=lambda w: w['x0'])
    L.append((k[0], ws[0]['top'], ' '.join(w['text'] for w in ws)))
start = next(i for i, (p, t, s) in enumerate(L) if re.match(r'^1\.\s*\(1\)\s*This Act may be called', s))
L = L[start:]
secs, tops, cur, nxt = {}, {}, None, 1
for p, t, s in L:
    if re.fullmatch(r'\d{1,2}|S\s?\.\s?\d+\]?.*GAZETTE.*|.*THE GAZETTE OF INDIA EXTRAORDINARY.*', s.strip()): continue
    m = re.match(r'^(\d{1,3})\.\s*(.*)$', s)
    if m and int(m.group(1)) == nxt:
        cur = nxt; secs[cur] = [m.group(2)]; tops[cur] = (p, t); nxt += 1; continue
    if cur: secs[cur].append(s)
mrows = {}
for pi, w in margin:
    if w['size'] > 8.5 or w['size'] < 7.5: continue
    mrows.setdefault((pi, round(w['top'] / 3)), []).append(w)
notes = []
for k in sorted(mrows):
    ws = sorted(mrows[k], key=lambda w: w['x0'])
    notes.append((k[0], ws[0]['top'], ' '.join(w['text'] for w in ws)))
pages = defaultdict(list)
for p, t, s_ in notes: pages[p].append((t, s_))
groups = []
for p, ls in pages.items():
    ls.sort(); g = [ls[0]]
    for x in ls[1:]:
        if x[0] - g[-1][0] > 11.5:
            groups.append((p, g[0][0], ' '.join(y[1] for y in g))); g = [x]
        else: g.append(x)
    groups.append((p, g[0][0], ' '.join(y[1] for y in g)))
assign = defaultdict(list)
for p, t, txt in groups:
    cands = [(abs(tt - t), n) for n, (pp, tt) in tops.items() if pp == p]
    if not cands: continue
    d, n = min(cands)
    if d <= 40: assign[n].append((p, t, txt))
heads = {}
for n in secs:
    txt = ' '.join(x[2] for x in sorted(assign.get(n, [])))
    heads[n] = re.sub(r'\s+', ' ', re.sub(r'\b\d{1,3} of \d{4}\.', ' ', txt)).strip()
out = {str(k): {'heading': heads.get(k, ''), 'body': re.sub(r'\s+', ' ', ' '.join(v)).strip(), 'page': tops[k][0] + 1} for k, v in secs.items()}
print(len(out), 'sections;', sum(1 for v in out.values() if not v['heading']), 'without heading')
json.dump(out, open(OUT, 'w'), indent=0, ensure_ascii=False)
