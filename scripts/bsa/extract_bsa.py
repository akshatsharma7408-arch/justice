import pdfplumber, re, json
pdf=pdfplumber.open('/home/sandbox/w/src/bsa_prs.pdf')
L=[]
for pi,pg in enumerate(pdf.pages):
    ws=[w for w in pg.extract_words(extra_attrs=['size']) if w['size']>=9.4 and 60<w['top']<800]
    rows={}
    for w in ws: rows.setdefault(round(w['top']/3),[]).append(w)
    for k in sorted(rows):
        t=' '.join(w['text'] for w in sorted(rows[k],key=lambda w:w['x0']))
        L.append((pi,t))
# drop page 0 preamble up to 'follows:—'
start=next(i for i,(p,t) in enumerate(L) if p==0 and t.startswith('1.'))
L=L[start:]
L=[(p,t) for p,t in L if not re.fullmatch(r'\d{1,2}',t.strip())]
secs={}; cur=None; nxt=1
for p,t in L:
    m=re.match(r'^(\d{1,3})\.\s*(.*)$',t)
    if m and int(m.group(1))==nxt:
        cur=nxt; secs[cur]=[m.group(2)]; nxt+=1; continue
    if cur: secs[cur].append(t)
print(len(secs), nxt-1)
# schedule marker
last=secs[max(secs)]
for i,t in enumerate(last):
    if 'THE SCHEDULE' in t.upper(): print('schedule at',i,len(last))
out={str(k):re.sub(r'\s+',' ',' '.join(v)).strip() for k,v in secs.items()}
json.dump(out,open('/tmp/bsa_raw.json','w'),indent=0)
for k in ('1','57','63','170'): print(k,out[k][:400]); print()
