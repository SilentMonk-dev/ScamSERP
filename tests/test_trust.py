from datetime import datetime, timedelta, timezone

import pytest

from scamserp.extract import domain, host, links, normalize_phone, observations, phones
from scamserp.trust import active, score


ENTITY = {"id": "sbi", "aliases": ["SBI", "State Bank of India"]}
REGISTRY = [{"kind": "domain", "value": "sbi.bank.in", "status": "verified", "expires_at": "2099-01-01T00:00:00+00:00"}, {"kind": "phone", "value": "toll:18001234", "status": "verified", "expires_at": "2099-01-01T00:00:00+00:00"}]


@pytest.mark.parametrize("value,expected", [("१८०० १२३४", "toll:18001234"), ("1800-258-1800", "toll:18002581800"), ("+91 (98765) 43210", "+919876543210"), ("১৯৪৭", "short:1947"), ("౧౮౦౦ ౧౨౩౪", "toll:18001234"), ("1401234567", "service:1401234567"), ("123", None)])
def test_phone_normalization(value, expected):
    assert normalize_phone(value) == expected


def test_phone_extraction_indian_digits_and_formats():
    assert set(phones("Call १८०० १२३४ or +91-98765-43210. Aadhaar 1947.")) == {"toll:18001234", "+919876543210", "short:1947"}


@pytest.mark.parametrize("value,expected", [("https://home.sbi.bank.in/contact", "sbi.bank.in"), ("https://sbi.bank.in.attacker.example", "attacker.example"), ("https://one.blogspot.com/", "one.blogspot.com"), ("https://evil@uidai.gov.in", None), ("javascript:alert(1)", None), ("http://127.0.0.1/private", None), ("https://[::1]/", None), ("https://foo..in/", None)])
def test_domain_normalization(value, expected):
    assert domain(value) == expected


def test_registry_override():
    result = score({"domain": "sbi.bank.in", "phones": ["toll:18001234"], "kind": "ad", "facts": {"advertiser_verified": False}}, ENTITY, REGISTRY, reused=True)
    assert result["verdict"] == "Verified Official" and result["risk"] == 0


def test_expired_registry_never_verifies():
    expired = [{**r, "expires_at": "2000-01-01T00:00:00+00:00"} for r in REGISTRY]
    assert score({"domain": "sbi.bank.in", "phones": [], "facts": {}}, ENTITY, expired)["verdict"] == "Unverified"


def test_two_family_guard():
    result = score({"domain": "sbi-care-support.example", "phones": [], "facts": {}}, ENTITY, REGISTRY)
    assert result["risk"] == 70
    assert result["verdict"] == "Suspicious"
    result = score({"domain": "sbi-care-support.example", "phones": ["toll:18000000000"], "facts": {}}, ENTITY, REGISTRY)
    assert result["risk"] == 100 and result["verdict"] == "Likely Fraud"


def test_missing_ad_status_is_unknown():
    result = score({"domain": "generic.example", "phones": [], "kind": "ad", "facts": {}}, ENTITY, REGISTRY)
    assert not any(s["family"] == "Ad behavior" for s in result["signals"])


def test_unknown_entity_never_fraud():
    assert score({"domain": "sbi-support.example", "phones": ["toll:18000000000"], "facts": {}}, None, REGISTRY)["verdict"] == "Unverified"


def test_unknown_phone_registry_never_mismatch():
    result = score({"domain": "pmkisan.gov.in", "phones": ["toll:18000000000"], "facts": {}}, {"id": "pmkisan", "aliases": []}, [{**REGISTRY[0], "value": "pmkisan.gov.in"}])
    assert result["verdict"] == "Unverified"
    assert not any(s["code"] == "phone_mismatch" for s in result["signals"])


def test_contact_on_official_domain_prevents_override():
    result = score({"domain": "sbi.bank.in", "phones": ["toll:18000000000"], "facts": {}}, ENTITY, REGISTRY)
    assert result["verdict"] == "Unverified"


def test_gov_mitigator_does_not_make_unexplained_contact_safe():
    result = score({"domain": "other.gov.in", "phones": ["toll:18000000000"], "facts": {}}, ENTITY, REGISTRY)
    assert result["risk"] == 20 and result["verdict"] == "Unverified"


def test_sitelink_extraction_and_all_engines():
    data = {"organic_results": [{"title": "help", "link": "https://sbi.bank.in/", "sitelinks": {"inline": [{"title": "1800 1234"}]}}], "ads": [{"title": "Ad", "link": "https://ad.example"}], "ads_bottom": [{"title": "Bottom"}], "local_results": {"places": [{"title": "Branch", "phone": "1947"}]}, "knowledge_graph": {"title": "Panel", "phone": "1930"}, "related_questions": [{"title": "Question?"}], "related_searches": [{"title": "Search"}]}
    extracted = observations(data, "google")
    assert {x["kind"] for x in extracted} == {"organic", "ad", "local", "knowledge", "paa", "related"}
    assert extracted[0]["phones"] == ["toll:18001234"]
    assert observations({"suggestions": [{"value": "help now"}]}, "google_autocomplete")[0]["title"] == "help now"
    assert observations({"local_results": [{"title": "Bank", "website": "https://sbi.bank.in", "phone": "1800 1234"}]}, "google_local")[0]["phones"] == ["toll:18001234"]


def test_sms_links():
    assert links("Help at https://sbi-care.example/path. Or uidai.gov.in!") == ["sbi-care.example", "uidai.gov.in"]
