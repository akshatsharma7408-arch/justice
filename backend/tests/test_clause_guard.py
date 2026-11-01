import pytest
from app.services.llm_service import clause_sentence_preserves as g

C4 = "(4) The Magistrate shall fix the first date of hearing, which shall not ordinarily be beyond three days from the date of receipt of the application by the court."
C5 = "(5) The Magistrate shall Endeavour to dispose of every application made under sub-section (1) within a period of sixty days from the date of its first hearing."
C2 = "(2) The relief sought may include an order for payment of compensation or damages without prejudice to the right of such person to institute a suit, against the respondent."

def test_good_sentences_pass():
    assert g(C4, "The Magistrate must set the first hearing date, which should not ordinarily be more than three days after the court receives the application.") is None
    assert g(C5, "The Magistrate shall try to decide each application within sixty days from its first hearing.") is None

def test_respondent_to_abuser_rejected():
    assert g(C2, "The person can ask for money from the abuser and can still file a separate suit.") == "swapped in 'abuser'"

def test_dropped_ordinarily_rejected():
    assert g(C4, "The Magistrate must set the first hearing date within three days of receiving the application.") == "qualifier 'ordinarily' dropped"

def test_dropped_endeavour_rejected_and_changed_period_rejected():
    assert g(C5, "The Magistrate shall decide each application within sixty days from its first hearing.") == "qualifier 'endeavour' dropped"
    assert g(C5, "The Magistrate shall try to decide each application within ninety days from its first hearing.") == "number or time period changed"

def test_modal_may_to_must_rejected():
    assert g(C2, "The relief must include money from the respondent.") is not None
