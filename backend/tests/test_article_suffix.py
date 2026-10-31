from app.routers.search import normalize_article_suffix as n


def test_spaced_suffix_joined():
    assert n("what is article 339 AA") == "what is article 339AA"
    assert n("Article 21 A") == "Article 21A"
    assert n("art. 239 AA") == "art. 239AA"
    assert n("article 339 aa") == "article 339AA"


def test_plain_words_untouched():
    for q in ["article 21 in india", "article 14 or 15", "article 339", "what is article 21 of the constitution",
              "article 19 A freedom? yes".replace("A freedom", "and freedom"), "article 32 is a right"]:
        assert n(q) == q
