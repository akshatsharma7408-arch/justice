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
cont = r'(?:\n(?!\s*[\uF02A\uFF0A\s]*(?:\d+\s*\[)?\d{1,3}[A-Z]{0,3}\.\s)[^\n]{0,150}?){0,3}?'
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
# 268A handled as a special case below (header has a glued footnote digit)
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
    body = re.sub(r'^\d{1,2}\*+\s*', '', body)
    body = re.sub(r'^\d{1,2}\[', '[', body)
    body = re.sub(r'\s?\*\sSee Appendix[^.]*\.?', '', body)
    body = re.sub(r'(?<=\s)\d{1,2}\.\s(?=\()', '', body)
    i = body.find('* See ')
    if i > 0 and len(body) - i < 250:
        body = body[:i].rstrip(' ;:')
    body = re.sub(r'\s+', ' ', body).strip()
    status = 'in_force'
    if re.match(r'^\[?Repealed', body): status = 'repealed'
    elif re.match(r'^\[?Omitted\b', body) or 'Omitted by the Constitution' in body[:120]: status = 'omitted'
    return title, body, status
corpus = {}
for num, (m, win) in windows.items():
    t, b, st = clean_body(num, m, win)
    corpus[num] = {'title': t, 'body': b, 'status': st}
i268 = text.find('268A. [Service tax')
j269 = min([m.start() for _, m in matches if m.start() > i268], default=len(text))
seg268 = text[i268:j269]
m268 = re.match(r'268A\.\s+\[(.+?)\]\.\u2014(.*)', seg268, re.S)
t268 = re.sub(r'\s+', ' ', m268.group(1)).strip().rstrip('.')
b268 = re.sub(r'\s+', ' ', m268.group(2)).strip()
b268 = re.split(r'\s+\d{1,2}\.\sThe words', b268)[0].strip()
corpus['268A'] = {'title': t268, 'body': b268, 'status': 'omitted' if b268.startswith('Omitted') else 'in_force'}
corpus['232'] = {'title': 'Establishment of a common High Court for two or more States',
  'body': 'Omitted - articles 230, 231 and 232 substituted by articles 230 and 231 by the Constitution (Seventh Amendment) Act, 1956, s. 16 (w.e.f. 1-11-1956).', 'status': 'omitted'}

# Post-pass: article-specific asterisk-footnote surgery (each inspected against the PDF text)
# Art 370: asterisk note (2019 C.O. 273 operative-status declaration + 1952 C.O. 44 Explanation
# modification) is footnote apparatus, not clause text; body resumes at "(ii)". Keep it verbatim
# as the explanation so the current operative status is preserved and attributed.
b370 = corpus['370']['body']
i = b370.find('* In exercise of the powers conferred')
j = b370.find('*Now \u201cGovernor\u201d.')
assert i > 0 and j > i, "370 footnote boundaries not found"
note370 = b370[i:j + len('*Now \u201cGovernor\u201d.')]
corpus['370']['body'] = (b370[:i] + b370[j + len('*Now \u201cGovernor\u201d.'):]).replace('  ', ' ').strip()
corpus['370']['body'] = corpus['370']['body'].replace('; and (ii)', '; and (ii)')
corpus['370']['explanation'] = "Asterisk note in the official edition (verbatim): " + note370
# Arts 371F / 372: pure pointer footnotes, dropped
b = corpus['371F']['body']
b = b.replace(' * See the Constitution (Removal of Difficulties) Order No. XI (C.O. 99).', '')
corpus['371F']['body'] = re.sub(r'\s+', ' ', b).strip()
b = corpus['372']['body']
i = b.find(' * See the Adaptation of Laws Order')
assert i > 0, "372 footnote not found"
# Explanations I-IV follow the asterisk footnote in the source; re-attach from the raw stream
iex = text.find('\x0cExplanation I.')
iend = text.find('372A.', iex)
assert iex > 0 and iend > iex, "372 explanations not found"
expl_lines = [ln.strip() for ln in text[iex:iend].split('\n') if ln.strip() and not re.fullmatch(r'\d{1,3}', ln.strip())]
expl = re.sub(r'\s+', ' ', ' '.join(expl_lines)).replace('\x0c', '').strip()
corpus['372']['body'] = re.sub(r'\s+', ' ', (b[:i] + ' ' + expl)).strip()

json.dump(corpus, open('/home/sandbox/work/coi_corpus.json','w'), ensure_ascii=False, indent=1)
susp = []
for k, v in corpus.items():
    b = v['body']
    if len(b) < 60 and v['status'] == 'in_force': susp.append((k, 'short', len(b)))
    elif b and not re.search(r'[.;:)\]"—]$', b) and v['status']=='in_force': susp.append((k, 'no-terminal', b[-50:]))
    if FOOTLINE.search(b) and v['status'] == 'in_force': susp.append((k, 'footleak', b[:80]))
print("articles:", len(corpus), "| suspicious:", len(susp))
for s in susp[:40]: print(' ', s)
