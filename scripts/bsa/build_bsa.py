import json,re
raw=json.load(open('/tmp/bsa_raw.json'))
raw['170']=raw['170'].split('THE SCHEDULE')[0].strip()
# patches for superscript/italic glitches (verified against second gazette text layer)
raw['21']=raw['21'].replace('under (1) (2) sub-sections and of section 132','under sub-sections (1) and (2) of section 132')
raw['52']=raw['52'].replace('(2) (1) In the cases referred to in sub-section and also','(2) In the cases referred to in sub-section (1) and also')
raw['146']=raw['146'].replace('( )Leading','(2) Leading')
for k in raw:
    raw[k]=re.sub(r'\b([a-z]{1,3}) \( \)(?=\S)',lambda m:'(%s) '%m.group(1),raw[k])
# ToC headings
toc=open('/tmp/gh/bsa_ic.txt').read()
toc=toc[toc.index('SECTIONS 1.'):toc.index('THE SCHEDULE')] if 'THE SCHEDULE' in toc else toc
toc=toc[:toc.index('THE SCHEDULE')] if 'THE SCHEDULE' in toc else toc
flat=re.sub(r'\s+',' ',toc)
heads={}
pos=[]
n=1; i=0
for n in range(1,171):
    m=re.search(r'(?<![\d])%d\. '%n,flat[i:])
    pos.append((n,i+m.start(),i+m.end())); i=i+m.end()
for j,(n,s,e) in enumerate(pos):
    end=pos[j+1][1] if j+1<len(pos) else len(flat)
    heads[str(n)]=flat[e:end].strip()
json.dump(heads,open('/tmp/bsa_heads_raw.json','w'),indent=0)
for k in ('1','2','3','4','26','27','57','63','169','170'): print(k,heads[k])
json.dump(raw,open('/tmp/bsa_clean.json','w'))
print([k for k,v in raw.items() if '( )' in v])
