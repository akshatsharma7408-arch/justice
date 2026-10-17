# Verified data sources — Section 27 / Article 141 corpus

Every precedent in `backend/app/data/section27_precedents.json` was verified
on 2026-10-17 against a free public source. `ratioSummary` fields are
editorial paraphrases for retrieval ranking — the authoritative text is the
full judgment at the source link. Paywalled databases (Manupatra, SCC OnLine,
Westlaw) are never scraped.

## Supreme Court of India

| Case | Citation | Bench | Decided | Source |
| --- | --- | --- | --- | --- |
| Percept D'Mark (India) (P) Ltd. v. Zaheer Khan | (2006) 4 SCC 227; AIR 2006 SC 3426 | H.K. Sema, A.R. Lakshmanan JJ. | 2006-03-22 | https://indiankanoon.org/doc/571375/ |
| Superintendence Company of India (P) Ltd. v. Krishan Murgai | (1981) 2 SCC 246; AIR 1980 SC 1717 | Tulzapurkar, Untwalia, Sen JJ. | 1980-05-09 | https://indiankanoon.org/doc/1186410/ |
| Niranjan Shankar Golikari v. Century Spinning & Mfg. Co. Ltd. | AIR 1967 SC 1098; 1967 (2) SCR 378 | Shelat, Bachawat JJ. | 1967-01-17 | https://indiankanoon.org/doc/452434/ · https://api.sci.gov.in/jonew/judis/2486.pdf |
| Gujarat Bottling Co. Ltd. v. The Coca Cola Co. | (1995) 5 SCC 545; AIR 1995 SC 2372 | S.C. Agrawal, S. Saghir Ahmad JJ. | 1995-08-04 | https://indiankanoon.org/doc/104935066/ |
| Justice K.S. Puttaswamy (Retd.) v. Union of India | (2017) 10 SCC 1 | 9-judge Constitution Bench | 2017-08-24 | https://indiankanoon.org/doc/91938676/ |
| ADM Jabalpur v. Shivkant Shukla | (1976) 2 SCC 521 | 5-judge Constitution Bench | 1976-04-28 | https://indiankanoon.org/doc/1735815/ |

## Delhi High Court

| Case | Decided | Source |
| --- | --- | --- |
| Wipro Ltd. v. Beckman Coulter International S.A. | 2006-07-11 | https://indiankanoon.org/doc/647033/ |
| Ambiance India Pvt. Ltd. v. Naveen Jain | 2005-03-16 | https://indiankanoon.org/doc/1399186/ |
| Desiccant Rotors International Pvt. Ltd. v. Bappaditya Sarkar & Anr | 2009-07-14 | https://indiankanoon.org/doc/175180860/ |
| Stellar Information Technology Pvt. Ltd. v. Rakesh Kumar & Ors | 2016-08-29 | https://indiankanoon.org/doc/65671346/ |

## Corrections made during verification

- Percept D'Mark bench is H.K. Sema & A.R. Lakshmanan JJ. (earlier drafts of
  this repo named B.P. Singh & Altamas Kabir JJ. — incorrect).
- Krishan Murgai bench is Tulzapurkar, Untwalia & Sen JJ., decided 9 May 1980
  (reported in 1981 SCC) — earlier repo data said Pathak J. and 1981.
- Niranjan Golikari bench is Shelat & Bachawat JJ. — earlier repo data said
  Shelat & Vaidialingam JJ.
- The Delhi HC non-compete case previously listed as "Desiccant Rotors
  International v. B.P. Aggarwal (2011)" is actually Desiccant Rotors
  International Pvt. Ltd. v. Bappaditya Sarkar & Anr (14 July 2009).

## Statutes

Statutory texts (Indian Contract Act 1872, Specific Relief Act 1963,
Arbitration and Conciliation Act 1996) are transcribed in
`app/ingest/seed_bare_acts.py` and `app/ingest/indiacode_scraper.py`,
following the official texts published on India Code (indiacode.nic.in).
