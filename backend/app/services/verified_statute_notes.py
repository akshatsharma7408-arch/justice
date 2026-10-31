"""Verbatim statute text verified against an official source, for topics with no bare-act corpus.

Each entry quotes the provision exactly as reproduced in Supreme Court of India judgments
(api.sci.gov.in). Text is never paraphrased here. Amendments after the quoting judgment
are not checked, and that is stated in the label.
"""
import re
from typing import Optional, Dict

_S138 = ("138. Dishonour of cheque for insufficiency, etc., of funds in the account.\u2014Where any cheque drawn by a person on an account maintained by him with a banker for payment of any amount of money to another person from out of that account for the discharge, in whole or in part, of any debt or other liability, is returned by the bank unpaid, either because of the amount of money standing to the credit of that account is insufficient to honour the cheque or that it exceeds the amount arranged to be paid from that account by an agreement made with that bank, such person shall be deemed to have committed an offence and shall, without prejudice to any other provision of this Act, be punished with imprisonment for a term which may extend to two years, or with fine which may extend to twice the amount of the cheque, or with both:\n"
         "Provided that nothing contained in this section shall apply unless\u2014\n"
         "(a) the cheque has been presented to the bank within a period of six months from the date on which it is drawn or within the period of its validity, whichever is earlier;\n"
         "(b) the payee or the holder in due course of the cheque, as the case may be, makes a demand for the payment of the said amount of money by giving a notice in writing, to the drawer of the cheque, within thirty days of the receipt of information by him from the bank regarding the return of the cheque as unpaid; and\n"
         "(c) the drawer of such cheque fails to make the payment of the said amount of money to the payee or as the case may be, to the holder in due course of the cheque within fifteen days of the receipt of the said notice.\n"
         "Explanation.\u2014For the purposes of this section, \u201cdebt or other liability\u201d means a legally enforceable debt or other liability.")

_S142 = ("142. Cognizance of offences.\u2014Notwithstanding anything contained in the Code of Criminal Procedure, 1973 (2 of 1974)\u2014\n"
         "(a) no court shall take cognizance of any offence punishable under section 138 except upon a complaint, in writing, made by the payee or, as the case may be, the holder in due course of the cheque;\n"
         "(b) such complaint is made within one month of the date on which the cause of action arises under clause (c) of the proviso to section 138:\n"
         "Provided that the cognizance of a complaint may be taken by the Court after the prescribed period, if the complainant satisfies the Court that he had sufficient cause for not making a complaint within such period.\n"
         "(c) no court inferior to that of a Metropolitan Magistrate or a Judicial Magistrate of the first class shall try any offence punishable under section 138.")

NI_SOURCES = [
    "https://api.sci.gov.in/jonew/judis/41940.pdf",
    "https://api.sci.gov.in/jonew/judis/40692.pdf",
    "https://api.sci.gov.in/supremecourt/2023/52267/52267_2023_15_15_56255_Judgement_01-Oct-2024.pdf",
]

_CHEQUE = re.compile(r"\b(cheques?|checks?)\b.{0,40}\b(bounc\w*|dishonou?r\w*|return\w*|fail\w*)|\b(bounc\w*|dishonou?r\w*)\b.{0,30}\b(cheques?|checks?)\b|negotiable instruments? act|\bni act\b|\bsection 138\b.{0,40}\b(ni|negotiable|cheque)", re.I)


def verified_note_for(query: str) -> Optional[Dict[str, str]]:
    if not _CHEQUE.search(query or ""):
        return None
    answer = (
        "Verified statute text (Negotiable Instruments Act, 1881, sections 138 and 142). "
        "The exact words of the law are below; nothing has been paraphrased.\n\n"
        + _S138 + "\n\n" + _S142 + "\n\n"
        "Source: both sections are quoted in Supreme Court of India judgments on the court's own site. "
        "Edition: the text as quoted there (section 142 as amended in 2002). Later amendments, rules and "
        "state-specific changes are not checked here. This is not legal advice."
    )
    return {"answer": answer, "sources": NI_SOURCES}
