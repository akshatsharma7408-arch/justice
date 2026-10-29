# Constitution of India corpus (build artifacts)

Source: official Legislative Department diglot PDF,
"The Constitution of India [As on 1st May, 2026]" (incorporating amendments
up to the 106th Amendment Act, 2023).
URL: https://www.legislative.gov.in/static/uploads/2025/07/c9fe9c9b6840524844316f74bb1c556c.pdf

- parse_coi.py / clean_coi.py: extraction + cleaning pipeline (pdftotext -> per-article JSON).
- coi_corpus.json: 499 articles (467 in force, 32 omitted/repealed with omission notes).
  Articles 238 and 35A are absent from this edition (Part VII omitted by the 7th
  Amendment; 35A not carried in this edition).
- Extraction verified by clause-level containment checks against the PDF text
  stream and structural audits (no footnote/page furniture in in-force bodies).
  This is the "As on 1st May, 2026" edition only; later amendments are not covered.
