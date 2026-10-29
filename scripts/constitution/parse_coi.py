# JUSTICE Constitution parser v4
# Source: official Legislative Department diglot PDF "The Constitution of India [As on 1st May, 2026]"
# URL: https://www.legislative.gov.in/static/uploads/2025/07/c9fe9c9b6840524844316f74bb1c556c.pdf
import re, json
raw = open('/tmp/coi.txt', encoding='utf-8').read().split('\n')
dev = re.compile(r'[\u0900-\u097F]')
clean = [ln.rstrip() for ln in raw if not dev.search(ln)]
text = '\n'.join(clean)
p = text.find('WE, THE PEOPLE OF INDIA')
end = text.find('\x0c1[FIRST SCHEDULE')
text = text[p:end]
text = re.sub(r'\b([Aa])rticles?\s+(\d{1,3}[A-Z]{0,3})\.', lambda m: m.group(1)+'rticle '+m.group(2)+'\u00a7', text)
noise = r'(?:[\s\uF02A\*]|\d{1,2}\*{0,3}(?!\d))'
cont = r'(?:\n(?!\s*[\uF02A\uFF0A\s]*(?:\d+\s*\[)?\d{1,3}[A-Z]{0,3}\.\s)[^\n]{0,150}){0,3}'
hdr = re.compile(r'(?:^|(?<=[\.\]\)\s\"\[]))[\s\f\uF02A\uFF0A]*(?:\d+\s*\[)?(\d{1,3}[A-Z]{0,3})\.\s+(?:\d+\s*\[)?\[?' + noise + r'{0,6}([A-Z][A-Za-z][^\n]{0,150}?' + cont + r'?)\u2014', re.M)
matches = list(hdr.finditer(text))
def norm_num(n):
    m = re.match(r'(\d+)([A-Z]*)', n)
    d, s = m.group(1), m.group(2)
    while len(d) > 1 and int(d) > 395:
        d = d[1:]
    return d + s
arts = {}
for i, m in enumerate(matches):
    num = norm_num(m.group(1))
    e = matches[i+1].start() if i+1 < len(matches) else len(text)
    if num not in arts:
        arts[num] = text[m.start():e].strip()
missing = [str(n) for n in range(1, 396) if str(n) not in arts]
suff = sorted([k for k in arts if not k.isdigit()])
print("unique:", len(arts))
print("missing numeric:", missing)
print("suffixed:", suff)
json.dump(arts, open('/tmp/coi_articles_raw.json','w'), ensure_ascii=False, indent=1)
