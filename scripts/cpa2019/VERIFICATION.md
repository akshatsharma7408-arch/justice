# Consumer Protection Act, 2019 (Act 35 of 2019) - corpus verification

Status: text as enacted (assent 9 Aug 2019). NOT promoted to production (deploy-live) at the time of writing.

## Source identity
Gazette of India Extraordinary, Part II Sec 1, No. 54, 9 Aug 2019, 40 pages, title "2606GI.p65", Acrobat Distiller 7.0, created 9 Aug 2019 23:04 IST.
SHA-256 0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756 - identical bytes from:
- https://cdnbbsr.s3waas.gov.in/s3194cf6c2de8e00c05fcf16c498adc7bf/uploads/2022/01/2022010496.pdf (government-hosted, linked from haryanafood.gov.in)
- Wikimedia Commons "Consumer_Protection_Act,_2019.pdf"
Same title/first text as https://consumeraffairs.nic.in/sites/default/files/CP%20Act%202019.pdf (fetch returns only the first ~10 KB, s.1-19 region) and egazette.gov.in/WriteReadData/2019/210422.pdf (s.1-33 compared earlier; s.34 onward truncated by the fetch tool).
Not obtained: a copy from egazette.gov.in or India Code downloaded in full.

## Method
- extract_cpa.py (pdfplumber): body text = words >= 9.5pt; headings = 7.5-8.5pt marginal notes grouped and attached to the nearest section start on the page; cross-references ("5 of 1908.") removed from headings.
- build_cpa.py: strips trailing chapter heading residue and the gazette signature; adds s.1 (commencement) and s.107 (repeal/savings) caveats.
- crosscheck.py (PyMuPDF, a different PDF library): token-level difflib comparison of the built corpus body text against the PDF body-size lines, plus a heading-in-marginal-text check.

## Result (per section, no percentages)
- 107 contiguous sections, all with headings and terminal punctuation.
- Token diff corpus (20,139 tokens) vs PyMuPDF (20,492): 47 differences, all non-statutory page furniture: 39 running page headers ("THE GAZETTE OF INDIA EXTRAORDINARY", page numbers), 7 chapter headings (II, III, IV, V, VI, VII, VIII; I excluded) and the gazette signature line after s.107. Zero differing words inside any section body.
- Heading check: 0 of 107 headings fail (every heading's words occur in order in the marginal text of its page).

## Limits
- Both extractions read the same PDF text layer; an error in the text layer itself would not show. No rendered-image comparison was done.
- Amendments, rules, notifications and schedules after enactment are not incorporated. Commencement is by notification under s.1(3); notified dates are not recorded here.
- Not a consolidated or current text. Served with the "as enacted - amendments not checked" badge and notice.
- Case attachment: a case is kept only if its text names the 2019 Act; this guard is not proof of a holding.
