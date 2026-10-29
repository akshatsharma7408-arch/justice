# BNS / BNSS corpus verification record (29 October 2026, v2)

## Sources (exact URLs)
- BNS gazette PDF (Act 45 of 2023, eGazette CG-DL-E-25122023-250883):
  https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nyaya%20Sanhita,%202023.pdf (byte mirror of the official gazette)
- BNSS gazette PDF (Act 46 of 2023, eGazette CG-DL-E-25122023-250884):
  https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nagarik%20Suraksha%20Sanhita,%202023.pdf
- Indian Kanoon full-act pages (secondary transcript; headings + independent reading-order cross-check):
  BNS https://indiankanoon.org/doc/149679501/ ; BNSS https://indiankanoon.org/doc/91117739/
- Commencement: BNS S.O. 850(E), 23.02.2024: https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf
  BNSS S.O. 848(E), 23.02.2024: https://www.mha.gov.in/sites/default/files/BharatiyaNagarikSurakshaSanhita_24022024.pdf

## Commencement status (grounded)
- Both Acts in force 1 July 2024 per the above S.O.s. BNS exception: s.106(2) (official, from S.O. 850(E) itself).
  BNSS exception: First Schedule entries relating to BNS s.106(2).
- Current status of s.106(2): no later commencement notification located; press reporting
  (Hindustan Times, 25-26 Oct 2026) describes it as still not in force. Official exception = verified;
  continued non-commencement = reported, not re-verified against a fresh eGazette scan (egazette.gov.in unreachable from the build environment).
- BNSS s.1(2) territorial carve-outs (Chapters IX, XI, XII not applying to Nagaland / tribal areas
  unless the State Government notifies) preserved verbatim in the s.1 body.

## Body provenance and per-section verification classes
Body source hierarchy: (1) gazette-derived text (furniture and marginal notes stripped by exact
vocabulary match; every removed line-run provably matches a known heading/chapter string);
(2) Indian Kanoon transcript where the gazette PDF text layer is column-scrambled or my extraction
was incomplete (24 sections), each then verified to contain all words of the corresponding gazette
segment (remaining differences = marginal-note words and section-number tokens only).

- BNS (358): 169 gazette-derived and word-identical to the kanoon transcript; 185 gazette-derived
  where kanoon disagrees - every such disagreement quantified by word-multiset diff and classified:
  direction is kanoon omissions (dropped chapeaus/parenthetical act citations, e.g. s.2) or <=10-word
  formatting noise; 4 kanoon-body patches (ss.26, 147, 237, 342), each verified as a superset of the
  gazette segment's words.
- BNSS (531): 276 gazette-derived word-identical; 236 gazette-derived with classified kanoon
  disagreement (same classes); 9 kanoon-body patches (ss.4, 132, 158, 191, 205, 228, 285, 428, 531);
  10 scramble-zone sections (ss.150-152, 169-171, 230, 261, 409, 453) from kanoon, verified against
  the whole gazette stream.
- 11 sections manually diffed end-to-end before corpus assembly (BNS 2,3,4,14,26,49,341,358;
  BNSS 5,151,230); zero substantive divergence found, all layout artifacts.

## Known limitations (explicit)
- Text is the AS-ENACTED gazette text (25.12.2023). Later amendments, if any, are NOT incorporated.
- Gazette-derived bodies follow the PDF text layer's reading order; for illustration-heavy sections
  the layer may linearize illustration blocks out of printed order (content complete, order within
  illustration lists may reflect the text layer, not the printed page).
- Kanoon is a secondary transcript; the gazette PDF remains the authoritative source.
- No independent second-edition cross-check. Re-run this verification after any amendment cycle.
- Per-section provenance (which source and class) is recorded in scripts/criminal_reforms/provenance.json.
