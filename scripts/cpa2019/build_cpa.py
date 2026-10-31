"""Build backend/app/ingest/cpa_corpus.json from the extract_cpa.py output.
Usage: python3 build_cpa.py raw.json backend/app/ingest/cpa_corpus.json"""
import json, re, sys
raw = json.load(open(sys.argv[1])); out = {}
for k in sorted(raw, key=int):
    body = raw[k]['body']
    body = re.sub(r'\s*[\u2014\-]{2,}\s*DR\.\s*G\.\s*NARAYANA RAJU.*$', '', body).strip()   # gazette signature (s.107)
    body = re.sub(r'\s*CHAPTER [IVXL]+(?: [A-Z])*\s*$', '', body).strip()                 # chapter heading leaked at section end
    out[k] = {'heading': raw[k]['heading'], 'body': body}
out['1']['caveat'] = ("Commencement: under s.1(3) the Act comes into force on dates notified by the Central Government, "
                      "and different dates may apply to different provisions. The notified dates are not recorded in this database.")
out['107']['caveat'] = ("Repeals the Consumer Protection Act, 1986 (68 of 1986) subject to the savings in sub-section (2); "
                        "the effect on pending matters is as stated in the section text.")
json.dump(out, open(sys.argv[2], 'w'), indent=1, ensure_ascii=False)
print(len(out), 'sections')
