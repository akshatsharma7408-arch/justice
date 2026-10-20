/**
 * AILIP Indian Legal Corpus & Precedent Database
 * Sourced from open-source Indian legal datasets: Vaquill Open India Law & KanoonGPT
 */

export const LANDMARK_PRECEDENTS = [
  {
    id: "sc-2006-percept",
    title: "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr.",
    citation: "(2006) 4 SCC 227",
    court: "Supreme Court of India",
    benchSize: 2,
    benchType: "Division Bench",
    judges: ["S.B. Sinha, J.", "P.K. Balasubramanyan, J."],
    decisionYear: 2006,
    statutes: ["Indian Contract Act, 1872 - Section 27"],
    status: "GREEN",
    statusLabel: "Binding Precedent (Division Bench)",
    statusDescription: "Conclusively settled that Section 27 leaves no room for any test of 'reasonableness' regarding post-service non-compete covenants.",
    ratioSummary: "Under Section 27 of the Indian Contract Act, 1872, any covenant in restraint of trade that extends beyond the term of the agreement is void ab initio. The doctrine applies without exception to post-contractual covenants.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Wipro Ltd. v. Beckman Coulter International (2006)", treatment: "AFFIRMED", year: 2006 },
      { court: "Delhi High Court", case: "Stellantis India v. Ex-Executive (2021)", treatment: "RELIED_ON", year: 2021 },
      { court: "Bombay High Court", case: "TechnoTrend Corp v. Rahul Sharma (2023)", treatment: "RELIED_ON", year: 2023 }
    ],
    citationCount: 412,
    overruledCases: []
  },
  {
    id: "sc-1981-superintendence",
    title: "Superintendence Company of India (P) Ltd. v. Krishan Murgai",
    citation: "(1981) 2 SCC 246",
    court: "Supreme Court of India",
    benchSize: 3,
    benchType: "Full Bench",
    judges: ["V.D. Tulzapurkar, J.", "R.S. Pathak, J.", "A.P. Sen, J."],
    decisionYear: 1981,
    statutes: ["Indian Contract Act, 1872 - Section 27"],
    status: "GREEN",
    statusLabel: "Binding Precedent (3-Judge Bench)",
    statusDescription: "Binding 3-Judge precedent. Confirmed that Indian law does not follow English Common Law rule of reasonable restraints post-service.",
    ratioSummary: "A post-service restrictive covenant operating after termination of employment is void in toto under Section 27 of the Contract Act. The doctrine of restraint of trade admits of no exceptions other than sale of goodwill.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Percept D'Mark v. Zaheer Khan (2006)", treatment: "AFFIRMED", year: 2006 },
      { court: "Delhi High Court", case: "Affle India Ltd. v. Saurabh Singh (2018)", treatment: "AFFIRMED", year: 2018 }
    ],
    citationCount: 689,
    overruledCases: []
  },
  {
    id: "sc-1967-niranjan-golikari",
    title: "Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd.",
    citation: "(1967) 2 SCR 378",
    court: "Supreme Court of India",
    benchSize: 2,
    benchType: "Division Bench",
    judges: ["J.M. Shelat, J.", "C.A. Vaidialingam, J."],
    decisionYear: 1967,
    statutes: ["Indian Contract Act, 1872 - Section 27"],
    status: "YELLOW",
    statusLabel: "Distinguished / Cautionary",
    statusDescription: "Frequently misunderstood. Valid ONLY for non-compete clauses operating DURING the subsistence of active employment. Post-employment application is distinguished and rejected.",
    ratioSummary: "Negative covenants operating during the period of the employment contract when the employee is bound to serve his employer exclusively are not in restraint of trade under Section 27. However, does NOT apply to post-termination restraints.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Krishan Murgai (1981)", treatment: "DISTINGUISHED", note: "Limited to subsistence of service", year: 1981 },
      { court: "Supreme Court of India", case: "Percept D'Mark (2006)", treatment: "DISTINGUISHED", note: "Not applicable post-service", year: 2006 }
    ],
    citationCount: 1105,
    overruledCases: []
  },
  {
    id: "sc-2017-puttaswamy",
    title: "K.S. Puttaswamy v. Union of India (right to privacy)",
    altTitles: ["Justice K.S. Puttaswamy (Retd.) v. Union of India"],
    citation: "(2017) 10 SCC 1",
    court: "Supreme Court of India",
    benchSize: 9,
    benchType: "Constitution Bench",
    leadJudge: "J.S. Khehar, C.J.I.",
    judges: ["J.S. Khehar, CJI", "J. Chelameswar, J.", "S.A. Bobde, J.", "D.Y. Chandrachud, J.", "R.K. Agrawal, J.", "Rohinton Fali Nariman, J.", "A.M. Sapre, J.", "Sanjay Kishan Kaul, J.", "S. Abdul Nazeer, J."],
    decisionYear: 2017,
    year: 2017,
    statutes: ["Constitution of India - Article 21, Part III"],
    status: "GREEN",
    statusLabel: "Foundational Precedent (9-Judge Bench)",
    statusDescription: "Monumental unanimous 9-judge ruling. Holds the Right to Privacy as a fundamental right intrinsic to Article 21. Explicitly overruled ADM Jabalpur (1976) and M.P. Sharma (1954).",
    ratioSummary: "Privacy is a constitutionally protected fundamental right emerging primarily from the guarantee of life and personal liberty under Article 21. Any encroachment must satisfy the threefold test of legality, legitimate state aim, and proportionality.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Navtej Singh Johar v. UOI (2018)", treatment: "RELIED_ON", year: 2018 },
      { court: "Supreme Court of India", case: "Joseph Shine v. UOI (2018)", treatment: "RELIED_ON", year: 2018 },
      { court: "Supreme Court of India", case: "Aadhaar Card Act Challenge (2019)", treatment: "APPLIED", year: 2019 }
    ],
    citationCount: 3820,
    overruledCases: ["ADM Jabalpur v. Shivkant Shukla (1976)", "M.P. Sharma v. Satish Chandra (1954)"]
  },
  {
    id: "sc-1976-adm-jabalpur",
    title: "ADM Jabalpur v. Shivkant Shukla (Habeas Corpus Case)",
    citation: "(1976) 2 SCC 521",
    court: "Supreme Court of India",
    benchSize: 5,
    benchType: "Constitution Bench",
    judges: ["A.N. Ray, CJI", "H.R. Khanna, J. (Dissenting)", "M.H. Beg, J.", "Y.V. Chandrachud, J.", "P.N. Bhagwati, J."],
    decisionYear: 1976,
    statutes: ["Constitution of India - Article 21, Article 359"],
    status: "RED",
    statusLabel: "Overruled / Bad Law",
    statusDescription: "EXPRESSLY OVERRULED by the 9-Judge Constitution Bench in K.S. Puttaswamy (2017). Cannot be cited under Article 141 for liberty suspension.",
    ratioSummary: "Majority held that in view of Presidential Order under Article 359(1), no person had locus standi to move any writ petition under Article 226 for habeas corpus. HR Khanna's dissent was later canonized and majority holding overruled.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "K.S. Puttaswamy v. UOI (2017)", treatment: "OVERRULED", note: "Overruled in toto by 9-judge bench", year: 2017 }
    ],
    citationCount: 1420,
    overruledCases: []
  },
  {
    id: "sc-2018-navtej-johar",
    title: "Navtej Singh Johar & Ors. v. Union of India",
    citation: "(2018) 10 SCC 1",
    court: "Supreme Court of India",
    benchSize: 5,
    benchType: "Constitution Bench",
    judges: ["Dipak Misra, CJI", "A.M. Khanwilkar, J.", "R.F. Nariman, J.", "D.Y. Chandrachud, J.", "Indu Malhotra, J."],
    decisionYear: 2018,
    statutes: ["Indian Penal Code, 1860 - Section 377", "Constitution of India - Articles 14, 15, 19, 21"],
    status: "GREEN",
    statusLabel: "Binding Precedent (5-Judge Bench)",
    statusDescription: "Decriminalized consensual sexual acts between adults under Section 377. Overruled the earlier 2-judge bench decision in Suresh Kumar Koushal (2014).",
    ratioSummary: "Section 377 IPC, so far as it penalizes any consensual sexual activity between two adults, is unconstitutional and violative of Articles 14, 15, 19 and 21 of the Constitution.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Supriyo @ Supriya Chakraborty v. UOI (2023)", treatment: "RELIED_ON", year: 2023 }
    ],
    citationCount: 954,
    overruledCases: ["Suresh Kumar Koushal v. Naz Foundation (2014) 1 SCC 1"]
  },
  {
    id: "sc-2014-suresh-koushal",
    title: "Suresh Kumar Koushal & Anr. v. Naz Foundation & Ors.",
    citation: "(2014) 1 SCC 1",
    court: "Supreme Court of India",
    benchSize: 2,
    benchType: "Division Bench",
    judges: ["G.S. Singhvi, J.", "S.J. Mukhopadhaya, J."],
    decisionYear: 2014,
    statutes: ["Indian Penal Code, 1860 - Section 377"],
    status: "RED",
    statusLabel: "Overruled / Bad Law",
    statusDescription: "EXPRESSLY OVERRULED by the 5-Judge Constitution Bench in Navtej Singh Johar (2018). Any reliance on this judgment is fatal in court.",
    ratioSummary: "Reversed Delhi High Court's Naz Foundation judgment and upheld the constitutionality of Section 377 IPC.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Navtej Singh Johar v. UOI (2018)", treatment: "OVERRULED", note: "Overruled by 5-Judge Constitution Bench", year: 2018 }
    ],
    citationCount: 480,
    overruledCases: []
  },
  {
    id: "sc-2015-kailash-nath",
    title: "Kailash Nath Associates v. Delhi Development Authority",
    citation: "(2015) 4 SCC 136",
    court: "Supreme Court of India",
    benchSize: 2,
    benchType: "Division Bench",
    judges: ["Ranjan Gogoi, J.", "Rohinton Fali Nariman, J."],
    decisionYear: 2015,
    statutes: ["Indian Contract Act, 1872 - Section 74"],
    status: "GREEN",
    statusLabel: "Binding Precedent (Division Bench)",
    statusDescription: "Authoritative precedent on forfeiture of earnest money and liquidated damages under Section 74 ICA.",
    ratioSummary: "Compensation under Section 74 is awarded for damage or loss proved to have been suffered. Where it is possible to prove actual damage, such proof is not dispensed with. Forfeiture of earnest money without proving damage is punitive and unlawful.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Mahanagar Telephone Nigam v. Tata Comm (2019)", treatment: "AFFIRMED", year: 2019 },
      { court: "Delhi High Court", case: "Unitech Limited v. DDA (2022)", treatment: "RELIED_ON", year: 2022 }
    ],
    citationCount: 820,
    overruledCases: []
  },
  {
    id: "sc-2022-vijay-madanlal",
    title: "Vijay Madanlal Choudhary & Ors. v. Union of India",
    citation: "(2022) SCC OnLine SC 929",
    court: "Supreme Court of India",
    benchSize: 3,
    benchType: "Full Bench",
    judges: ["A.M. Khanwilkar, J.", "Dinesh Maheshwari, J.", "C.T. Ravikumar, J."],
    decisionYear: 2022,
    statutes: ["Prevention of Money Laundering Act, 2002 - Section 45, 50"],
    status: "YELLOW",
    statusLabel: "Cautionary / Review Pending",
    statusDescription: "Upheld PMLA twin conditions and ED powers, but core aspects are currently subject to reconsideration before a Special Bench.",
    ratioSummary: "Upheld the validity of Section 45 twin conditions for bail under PMLA. Held that supply of ECIR is not mandatory as it is an internal administrative document.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Pankaj Bansal v. UOI (2023)", treatment: "DISTINGUISHED", note: "Grounds of arrest must be furnished in writing", year: 2023 },
      { court: "Supreme Court of India", case: "Review Petition in PMLA (2024)", treatment: "PENDING_REVIEW", note: "Referred to larger bench on twin conditions", year: 2024 }
    ],
    citationCount: 1530,
    overruledCases: []
  },
  {
    id: "sc-1979-dhanapal-chettiar",
    title: "V. Dhanapal Chettiar v. Yesodai Ammal",
    citation: "(1979) 4 SCC 214",
    court: "Supreme Court of India",
    benchSize: 7,
    benchType: "Constitution Bench",
    judges: ["Y.V. Chandrachud, CJI", "P.N. Bhagwati, J.", "V.R. Krishna Iyer, J.", "V.D. Tulzapurkar, J.", "D.A. Desai, J.", "R.S. Pathak, J.", "E.S. Venkataramiah, J."],
    decisionYear: 1979,
    statutes: ["Transfer of Property Act, 1882 - Section 106", "State Rent Control Acts"],
    status: "GREEN",
    statusLabel: "Foundational Precedent (7-Judge Bench)",
    statusDescription: "7-Judge Constitution Bench ruling settling relationship between Section 106 TPA notice and statutory grounds under State Rent Control Acts.",
    ratioSummary: "Notice to quit under Section 106 Transfer of Property Act is not a condition precedent for maintaining eviction petition under State Rent Control Acts; landlord must establish statutory grounds for eviction.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "Atma Ram Properties v. Federal Motors (2005)", treatment: "RELIED_ON", year: 2005 }
    ],
    citationCount: 1650,
    overruledCases: []
  },
  {
    id: "sc-2005-atma-ram",
    title: "Atma Ram Properties (P) Ltd. v. Federal Motors (P) Ltd.",
    citation: "(2005) 1 SCC 705",
    court: "Supreme Court of India",
    benchSize: 2,
    benchType: "Division Bench",
    judges: ["R.C. Lahoti, CJI", "G.P. Mathur, J."],
    decisionYear: 2005,
    statutes: ["Delhi Rent Control Act, 1958", "Code of Civil Procedure, 1908 - Order 41 Rule 5"],
    status: "GREEN",
    statusLabel: "Binding Precedent (Division Bench)",
    statusDescription: "Settled that upon passing of eviction decree, tenant cannot remain rent-free and appellate court may condition stay of eviction on payment of mesne profits.",
    ratioSummary: "Tenant against whom eviction decree is passed is liable to pay reasonable mesne profits or market rent as condition for stay of execution pending appeal.",
    treatmentHistory: [
      { court: "Supreme Court of India", case: "State of Maharashtra v. Super Max (2009)", treatment: "AFFIRMED", year: 2009 }
    ],
    citationCount: 920,
    overruledCases: []
  }
];

export const CONTRACT_PRESETS = [];
