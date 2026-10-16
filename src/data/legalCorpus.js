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
    statusLabel: "Good Law (Affirmed)",
    statusDescription: "Consistently affirmed. Conclusively settled that Section 27 leaves no room for any test of 'reasonableness' regarding post-service non-compete covenants.",
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
    id: "sc-1981-super-superintendence",
    title: "Super Superintendence Company of India v. Krishan Murgai",
    citation: "(1981) 2 SCC 246",
    court: "Supreme Court of India",
    benchSize: 3,
    benchType: "Full Bench",
    judges: ["V.D. Tulzapurkar, J.", "R.S. Pathak, J.", "A.P. Sen, J."],
    decisionYear: 1981,
    statutes: ["Indian Contract Act, 1872 - Section 27"],
    status: "GREEN",
    statusLabel: "Good Law (Binding 3-Judge Precedent)",
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
    title: "Justice K.S. Puttaswamy (Retd.) v. Union of India",
    citation: "(2017) 10 SCC 1",
    court: "Supreme Court of India",
    benchSize: 9,
    benchType: "Constitution Bench (9 Judges)",
    judges: ["J.S. Khehar, CJI", "J. Chelameswar, J.", "S.A. Bobde, J.", "D.Y. Chandrachud, J.", "R.K. Agrawal, J.", "Rohinton Fali Nariman, J.", "A.M. Sapre, J.", "Sanjay Kishan Kaul, J.", "S. Abdul Nazeer, J."],
    decisionYear: 2017,
    statutes: ["Constitution of India - Article 21, Part III"],
    status: "GREEN",
    statusLabel: "Good Law (Foundational 9-Judge Precedent)",
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
    statusLabel: "Good Law (Constitution Bench)",
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
    statusLabel: "Good Law (Liquidated Damages Authority)",
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
  }
];

export const CONTRACT_PRESETS = [
  {
    id: "preset-tech-consultant",
    title: "Senior Tech Consultant Agreement (Predatory Non-Compete)",
    category: "Employment & Consultancy",
    clauses: [
      {
        id: "cl-1",
        number: "1.0",
        title: "Term & Scope of Engagement",
        text: "The Consultant is engaged as Principal AI Systems Architect for a fixed tenure of twenty-four (24) months, commencing from the Effective Date, subject to early termination as stipulated under Clause 8.",
        riskLevel: "LOW",
        statutoryIssue: null,
        layman: "You are hired as a principal architect for 2 years unless let go earlier under Section 8.",
        redline: null
      },
      {
        id: "cl-4",
        number: "4.2",
        title: "Intellectual Property Assignment & Prior Moral Rights",
        text: "The Consultant hereby irrevocably assigns to the Company all worldwide rights, title, and interest in and to all Works, Inventions, models, and code developed, including moral rights, whether created during or outside business hours, using Company resources or personal equipment.",
        riskLevel: "MODERATE",
        statutoryIssue: "Section 57, Copyright Act, 1957 (Moral rights cannot be completely assigned or waived under Indian law)",
        layman: "The company claims ownership of everything you code—even projects you build at home on your own laptop on weekends. Under Indian copyright law, your moral rights as an author cannot be completely stripped.",
        redline: "The Consultant hereby assigns to the Company all proprietary rights in Works and Inventions created strictly in the direct scope of Company engagement and utilizing Company resources, excluding prior personal works and non-competing independent projects."
      },
      {
        id: "cl-9-3",
        number: "9.3",
        title: "Post-Termination Non-Compete Restriction",
        text: "The Consultant agrees that for a period of twenty-four (24) months following termination of this Agreement for any reason whatsoever, the Consultant shall not, directly or indirectly, engage in, advise, establish, or consult for any business operating in direct or indirect competition with the Company anywhere within the territory of India.",
        riskLevel: "CRITICAL",
        statutoryIssue: "Section 27, Indian Contract Act, 1872 (Restraint of trade - Void ab initio under Indian Law)",
        layman: "The company is trying to ban you from working for any competitor anywhere in India for 2 whole years after you leave. UNDER INDIAN LAW, THIS IS 100% UNENFORCEABLE AND VOID AB INITIO. Indian courts do not allow companies to restrict your right to earn a livelihood once employment ends.",
        precedents: ["Percept D'Mark v. Zaheer Khan (2006) 4 SCC 227", "Super Superintendence v. Krishan Murgai (1981) 2 SCC 246"],
        redline: "The Consultant agrees that for a period of twelve (12) months following termination, the Consultant shall not knowingly solicit, canvas, or induce away any existing client of the Company with whom the Consultant personally had material dealings during the last 6 months of engagement, nor disclose any confidential proprietary trade secrets."
      },
      {
        id: "cl-11",
        number: "11.1",
        title: "Governing Law & Exclusive Judicial Forum",
        text: "This Agreement shall be governed by the laws of India. Any dispute arising out of or in connection with this Agreement shall be subject to the exclusive jurisdiction of the Courts in Bangalore, and Consultant waives any right to invoke statutory appellate or consumer remedies in any other forum.",
        riskLevel: "MODERATE",
        statutoryIssue: "Section 28, Indian Contract Act, 1872 (Agreements in restraint of legal proceedings void to the extent of curtailing statutory jurisdiction)",
        layman: "All disputes must go to Bangalore courts, and they want you to give up other statutory rights. While parties can pick one competent court, clauses that strip statutory legal remedies are void.",
        redline: "This Agreement shall be governed by and construed in accordance with the laws of India. Courts of Bangalore shall have competent jurisdiction, subject to mandatory statutory consumer and labor remedies."
      }
    ]
  },
  {
    id: "preset-saas-msa",
    title: "Enterprise SaaS Master Services Agreement (Unilateral Liability)",
    category: "Software & Technology",
    clauses: [
      {
        id: "cl-msa-1",
        number: "3.1",
        title: "Service Availability & Maintenance Windows",
        text: "The Provider guarantees 99.9% uptime per calendar month, excluding scheduled maintenance windows notified at least 48 hours in advance.",
        riskLevel: "LOW",
        statutoryIssue: null,
        layman: "Standard 99.9% uptime commitment with a requirement to notify you 2 days before scheduled maintenance.",
        redline: null
      },
      {
        id: "cl-msa-5",
        number: "8.2",
        title: "Liquidated Damages as Penalty in Terrorem",
        text: "In the event of any material breach or service interruption exceeding 4 continuous hours, Provider shall immediately forfeit and pay to Customer liquidated damages equivalent to 100% of the entire annual contract value, irrespective of whether actual monetary injury occurred.",
        riskLevel: "CRITICAL",
        statutoryIssue: "Section 74, Indian Contract Act, 1872 (Penal liquidated damages vs genuine pre-estimate of loss - Kailash Nath v. DDA)",
        layman: "If the server goes down for 4 hours, the client wants 100% of the whole year's fees as penalty without proving they lost any money. Under Indian law (Kailash Nath case), courts will not enforce punitive penalties; damages must reflect genuine pre-estimated losses.",
        precedents: ["Kailash Nath Associates v. DDA (2015) 4 SCC 136"],
        redline: "In the event of service interruption exceeding 4 continuous hours attributable solely to Provider, Customer shall be entitled to pro-rated Service Credits capped at 15% of the monthly billing, as a mutually agreed genuine pre-estimate of liquidated damages."
      },
      {
        id: "cl-msa-7",
        number: "12.4",
        title: "Unilateral Indemnity & Limitation of Liability Exemption",
        text: "Customer's liability under this Agreement shall in all cases be capped at INR 10,000, whereas Provider's indemnity obligations for any claim, including third-party software claims, shall be unlimited, unconditional, and survive perpetual termination.",
        riskLevel: "CRITICAL",
        statutoryIssue: "Unconscionable contractual covenant & imbalance under Indian Contract jurisprudence",
        layman: "Massively one-sided: If the customer breaches, their maximum penalty is ₹10,000. But if you have an issue, your liability is unlimited forever. This creates huge commercial exposure.",
        redline: "Each party's aggregate liability under this Agreement, whether in contract, tort, or indemnity, shall be capped at the total fees paid or payable by Customer to Provider in the preceding twelve (12) months, excluding breaches of confidentiality or gross negligence."
      }
    ]
  }
];
