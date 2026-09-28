from fairtriage.normalise import PROTECTED, normalise, reconcile
from fairtriage.schemas import (Actionability, Confidence, DecisiveFact, Extraction,
                                Habitability, HazardDomain)


def test_lexicon_fixes_spelling():
    assert normalise("powa plug no wata")[0] == "power plug no water"


def test_protected_words_never_change():
    for w in PROTECTED:
        assert normalise(w)[0] == w


def test_reconcile_takes_the_cautious_reading():
    def ex(d):
        return Extraction(actionability=Actionability.REPAIR, hazard_domain=d,
                          is_active=True, endangers_person=d == HazardDomain.GAS,
                          essential_service_lost=False, habitability=Habitability.IMPAIRED,
                          evidence_phrase="x", confidence=Confidence.HIGH,
                          missing_decisive_fact=DecisiveFact.NONE)
    merged, diffs = reconcile(ex(HazardDomain.ELECTRICAL), ex(HazardDomain.GAS))
    assert diffs and merged.endangers_person, "a disagreement must never downgrade danger"
