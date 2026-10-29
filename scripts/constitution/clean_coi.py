# Clean raw article windows -> verified corpus JSON (v4 final)
import re, json
raw = open('/tmp/coi.txt', encoding='utf-8').read().split('\n')
dev = re.compile(r'[\u0900-\u097F]')
clean = [ln.rstrip() for ln in raw if not dev.search(ln)]
text = '\n'.join(clean)
p = text.find('WE, THE PEOPLE OF INDIA')
end = text.find('\x0c1[FIRST SCHEDULE')
text = text[p:end]
noise = r'(?:[\s\uF02A\*]|\d{1,2}\*{0,3}(?!\d))'
cont = r'(?:\n(?!\s*[\uF02A\uFF0A\s]*(?:\d+\s*\[)?\d{1,3}[A-Z]{0,3}\.\s)[^\n]{0,150}){0,3}?'
hdr = re.compile(r'(?:^|(?<=[\.\]\)\s\"\[]))[\s\f\uF02A\uFF0A]*(?:\d+\s*\[)?(\d{1,3}[A-Z]{0,3})\.\s+(?:\d+\s*\[)?\[?' + noise + r'{0,6}([A-Z][A-Za-z][^\n]{0,150}?' + cont + r')\u2014', re.M)
def norm_num(n):
    m = re.match(r'(\d+)([A-Z]*)', n)
    d, s = m.group(1), m.group(2)
    while len(d) > 1 and int(d) > 395:
        d = d[1:]
    return d + s
seen, matches = set(), []
for m in hdr.finditer(text):
    num = norm_num(m.group(1))
    if num in seen: continue
    seen.add(num)
    matches.append((num, m))
windows = {}
for i, (num, m) in enumerate(matches):
    e = matches[i+1][1].start() if i+1 < len(matches) else len(text)
    windows[num] = (m, text[m.start():e])
i268 = text.find('4268A. [Service tax')
if i268 > 0 and '268A' not in windows:
    nxt = min([m.start() for _, m in matches if m.start() > i268], default=len(text))
    fake = hdr.search(text, i268+1)
    windows['268A'] = (fake, text[i268+1:nxt])
FOOTSTART = re.compile(r'(Ins\.|Subs\.|Omitted|Added|Amended|w\.e\.f|Constitution \(|Act, \d{4}|G\.S\.R|ibid|vide|Cl\.|s\. \d|Sch\.|Art[s]?\.)', re.I)
FOOTCONT = re.compile(r'(Amendment\) Act|Act, \d{4}|w\.e\.f|\bibid\b|^s\. \d|^\d{4} SC|AIR \d|Vs?\.|struck down|Sch\.|G\.S\.R)', re.I)
FOOTLINE = re.compile(r'(w\.e\.f|\bibid\b|Subs\. by|Ins\. by|struck down|was as under|reported AIR|vide its order|before amendment|Omitted by the Constitution|Added by the Constitution)')
def is_furniture(s):
    if re.fullmatch(r'\d{1,3}', s): return True
    if s == 'THE CONSTITUTION OF INDIA': return True
    if re.fullmatch(r'PART [IVXLC]+[A-Z]?\.?', s): return True
    if re.fullmatch(r'\[?PART [IVXLC]+[A-Z]?\.?\]?', s): return True
    if re.fullmatch(r'[A-Z][A-Z \u2014,.\'\(\)-]{6,}', s) and not s.startswith('('): return True
    if re.fullmatch(r'\[[A-Z][A-Za-z ]{3,}\]', s): return True
    if re.fullmatch(r'\(?Part [IVXLC]+[\.\u2014-].*', s): return True
    if re.fullmatch(r'CHAPTER [IVXLC]+[\.\u2014-]?\s*\[?.*', s): return True
    if re.fullmatch(r'\d{1,2}\*{0,3}', s): return True
    return False
def clean_body(num, m, win):
    title = re.sub(r'\s+', ' ', m.group(2)).strip()
    title = re.sub(r'\s\d{1,2}\*{0,3}\s', ' ', title)
    title = re.sub(r'[\[\]\.]+$', '', title).strip()
    title = re.sub(r'^[\[\s]+', '', title).strip()
    body = win[m.end()-m.start():]
    out = []
    omitted_article = re.match(r'\s*\[?\(?\**(Omitted|Repealed)', body)
    for seg in body.split('\x0c'):
        lines = [ln.strip() for ln in seg.split('\n')]
        keep = []
        footnote_tail = False
        for ln in lines:
            if not ln or is_furniture(ln): continue
            if re.match(r'^\d{1,2}\.\s', ln) and FOOTSTART.search(ln): break
            if re.match(r'^(\*+|\d{1,2}\*+)\s', ln) and FOOTSTART.search(ln): break
            if re.match(r'^\d{1,2}\.\s', ln) and re.search(r'(The words|The expression|for cls?\.)', ln): break
            if not keep and FOOTCONT.search(ln) and not omitted_article: continue  # leading footnote continuation from prev page
            if FOOTLINE.search(ln) and not omitted_article: continue
            if re.fullmatch(r'\(w\.e\.f[^)]*\)\.?', ln): continue
            keep.append(ln)
        out.extend(keep)
    # trailing heading trim: last line of a genuine body ends with terminal punctuation
    while out and not re.search(r'[.;:)\]"—]$', out[-1]) and not out[-1].startswith('('):
        out.pop()
    body = ' '.join(out)
    body = re.sub(r'(^|\s)\d{1,2}(?=\[)', r'\1', body)
    body = re.sub(r'\s\d{1,2}\*{1,3}(?=[\s,.;])', ' ', body)
    body = re.sub(r'[\uF02A\uFF0A]', '*', body)
    body = re.sub(r'\*{2,}', '*', body)
    body = re.sub(r'\s+', ' ', body).strip()
    body = re.sub(r'\s+([,.;:])', r'\1', body)
    if body.endswith(']') and body.count(']') > body.count('['):
        body = body[:-1].rstrip()
    status = 'in_force'
    if re.match(r'^\[?Repealed', body): status = 'repealed'
    elif re.match(r'^\[?Omitted\b', body) or 'Omitted by the Constitution' in body[:120]: status = 'omitted'
    return title, body, status
corpus = {}
for num, (m, win) in windows.items():
    t, b, st = clean_body(num, m, win)
    corpus[num] = {'title': t, 'body': b, 'status': st}
corpus['232'] = {'title': 'Establishment of a common High Court for two or more States',
  'body': 'Omitted - articles 230, 231 and 232 substituted by articles 230 and 231 by the Constitution (Seventh Amendment) Act, 1956, s. 16 (w.e.f. 1-11-1956).', 'status': 'omitted'}
json.dump(corpus, open('/home/sandbox/work/coi_corpus.json','w'), ensure_ascii=False, indent=1)
susp = []
for k, v in corpus.items():
    b = v['body']
    if len(b) < 60 and v['status'] == 'in_force': susp.append((k, 'short', len(b)))
    elif b and not re.search(r'[.;:)\]"—]$', b) and v['status']=='in_force': susp.append((k, 'no-terminal', b[-50:]))
    if FOOTLINE.search(b) and v['status'] == 'in_force': susp.append((k, 'footleak', b[:80]))
print("articles:", len(corpus), "| suspicious:", len(susp))
for s in susp[:40]: print(' ', s)
