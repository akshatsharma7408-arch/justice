# BSA 2023 corpus verification record (30 October 2026)

## Sources
- Body text: Gazette of India Extraordinary, Act 47 of 2023 (eGazette CG-DL-E-25122023-250882), read from the PRS mirror
  https://prsindia.org/files/bills_acts/bills_parliament/2023/The%20Bharatiya%20Sakshya%20Bill,%202023.pdf (hosts the enacted gazette PDF).
- Headings: India Code arrangement of sections (consolidated, as on 6 Oct 2025)
  https://upload.indiacode.nic.in/view-casepdf?id=AC_CEN_5_23_00049_2023-47_1719292804654&type=act
- Second text layer for cross-check: https://thelawcodes.com/wp-content/uploads/2024/07/Bharatiya-Sakshya-Adhiniyam-2023-BS.pdf (same gazette, different file).
- Commencement: S.O. 849(E), 23.02.2024 (from the India Code footnote to s.1).

## Method
extract_bsa.py keeps words >= 9.4pt (drops 8pt marginal notes and page furniture) and splits sections by sequential number.
build_bsa.py applies 6 reviewed glitch patches (ss.21, 52, 146 sub-section numbering; 3 stray "( )" markers in ss.39, 52, 74), takes headings from the India Code ToC and trims the Schedule from s.170.

## Result
- 170/170 sections present, contiguous. 167/170 matched the second text layer on 40-character shingle containment before patching; the other 3 were the numbering glitches now patched.
- Sections 1-25 also checked against the India Code consolidated text (only s.1 differs: commencement footnote). Sections 26-170 were NOT compared against India Code (fetch truncated).

## Limits
- As-enacted text (25.12.2023). Amendments, if any, are not incorporated. Both PDF copies are the same gazette, so this is a text-layer check, not an independent edition.
- The Schedule (certificate form under s.63(4)) is not in the database.
- Per-section caveats on ss.1, 63, 170.
