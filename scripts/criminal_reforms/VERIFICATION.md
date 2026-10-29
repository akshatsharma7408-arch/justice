# BNS / BNSS corpus verification record (29 October 2026)

## Sources
- BNS: official Gazette PDF, Act 45 of 2023, eGazette CG-DL-E-25122023-250883,
  byte mirror at https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nyaya%20Sanhita,%202023.pdf
- BNSS: official Gazette PDF, Act 46 of 2023, eGazette CG-DL-E-25122023-250884,
  byte mirror at https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nagarik%20Suraksha%20Sanhita,%202023.pdf
- Structured section text (headings + natural reading order): Indian Kanoon full-act
  pages (secondary transcript of the same gazette text).
- Commencement: BNS S.O. 850(E) 23.02.2024 (https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf)
  - in force 1 July 2024 EXCEPT s.106(2). s.106(2) still uncommenced as of 29 Oct 2026
    (Hindustan Times, 25-26 Oct 2026 report).
  BNSS S.O. 848(E) 23.02.2024 (https://www.mha.gov.in/sites/default/files/BharatiyaNagarikSurakshaSanhita_24022024.pdf)
  - in force 1 July 2024 except First Schedule entries relating to BNS s.106(2).
  BNSS s.1(2) territorial carve-outs (Nagaland / tribal areas, Chapters IX, XI, XII) preserved verbatim in the s.1 body.

## Method
Seeded bodies/headings were parsed from the Indian Kanoon transcript (358/358 BNS,
531/531 BNSS, monotonically complete), then cross-checked against the official
gazette PDF text (alnum-normalized):

- BNS: 231 sections strict verbatim order-verified; 32 word-multiset identical
  (gazette illustration-block layout reorder only); 95 with small word-level
  differences (<=30 words, dominated by marginal-note junction artifacts;
  12-word shingle coverage vs gazette 82-99%).
- BNSS: 270 strict; 78 word-identical; 183 small-diff (same artifact classes;
  shingle coverage 86-99%).
- 11 sections manually diffed end-to-end (BNS 2, 3, 4, 14, 26, 49, 341, 358;
  BNSS 5, 151, 230): every divergence traced to gazette PDF layout artifacts
  (marginal-heading interleaves, illustration-column reorder, two-column
  scrambling). No substantive textual divergence found.

## Limitations
- Text is the AS-ENACTED gazette text (25.12.2023). Later amendments, if any,
  are not incorporated. No second-edition cross-check performed.
- "Word-identical" and "small-diff" classes are not strict verbatim order
  verification; they establish content identity against the gazette up to
  layout ordering and formatting artifacts.
- Kanoon is a secondary transcript; the gazette PDF remains the authoritative
  source. Any future amendment cycle must re-run this verification.
