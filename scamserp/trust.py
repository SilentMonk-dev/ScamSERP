from datetime import datetime, timezone
import re

from rapidfuzz.distance import Levenshtein

from .db import now
from .extract import host, domain

RULE_VERSION = "rules-1.1.0"
LABELS = ["Verified Official", "No Issue Found", "Unverified", "Suspicious", "Likely Fraud"]
REPUTABLE = {"wikipedia.org", "bbc.com", "reuters.com", "thehindu.com", "indianexpress.com"}
FREE = {"blogspot.com", "wordpress.com", "weebly.com", "github.io", "sites.google.com"}
CONFUSABLE = str.maketrans("аесорхуіјѕΑΒΕΙΚΜΝΟΡΤΧ", "aecopxyijsABEIKMNOPTX")


def active(record):
    if record["status"] != "verified" or not record["expires_at"]:
        return False
    try:
        expiry = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        clock = datetime.fromisoformat(now())
        verified = record.get("verified_at")
        verified = datetime.fromisoformat(verified.replace("Z", "+00:00")) if verified else None
        return expiry.tzinfo is not None and clock < expiry and (verified is None or (verified.tzinfo is not None and verified <= clock))
    except (AttributeError, TypeError, ValueError):
        return False


def score(observation, entity, registry, reused=False):
    signals = []
    def add(code, family, points, reason, hi):
        signals.append({"code": code, "family": family, "points": points, "reason": reason, "reason_hi": hi})
    d = observation.get("domain")
    ps = observation.get("phones", [])
    verified = [r for r in registry if active(r)]
    domains = {r["value"] for r in verified if r["kind"] == "domain"}
    official_phones = {r["value"] for r in verified if r["kind"] == "phone"}
    domain_ok = bool(d and d in domains)
    phones_ok = all(p in official_phones for p in ps)
    if domain_ok and phones_ok:
        return {"risk": 0, "verdict": "Verified Official", "signals": [], "rule_version": RULE_VERSION}
    if not entity:
        return {"risk": 0, "verdict": "Unverified", "signals": [], "rule_version": RULE_VERSION}
    candidates = {r["value"] for r in registry if r["kind"] == "domain" and r["status"] != "rejected"}
    candidate_domain = d in candidates
    intermediary = d in {r["value"] for r in verified if r["kind"] == "intermediary"}
    if d and domains and not domain_ok and not candidate_domain and not intermediary:
        add("domain_unlisted", "Identity", 25, "Domain is not in the current official registry for this entity.", "इस संस्था के आधिकारिक रिकॉर्ड में यह वेबसाइट नहीं है।")
        tokens = [re.sub(r"\W", "", t.lower()) for t in [entity["id"], *entity["aliases"]] if len(re.sub(r"\W", "", t)) > 2]
        try:
            decoded = d.encode("ascii").decode("idna") if d.isascii() else d
        except UnicodeError:
            decoded = d
        skeleton = decoded.translate(CONFUSABLE).lower()
        label = skeleton.split(".")[0]
        branded = any(t in re.sub(r"\W", "", skeleton) for t in tokens)
        lookalike = branded or any(0 < Levenshtein.distance(label, x.split(".")[0]) <= 2 for x in domains) or decoded != skeleton
        if lookalike:
            add("lookalike", "Identity", 30, "Domain resembles the claimed brand; resemblance does not establish ownership.", "वेबसाइट का नाम ब्रांड जैसा दिखता है, पर स्वामित्व साबित नहीं है।")
        if branded:
            add("brand_domain", "Identity", 15, "Brand token appears in a domain outside the official registry.", "गैर-आधिकारिक वेबसाइट के नाम में ब्रांड का नाम है।")
    # Absence of a complete phone registry is a gap, never an accusation.
    unmatched = bool(ps and official_phones and not phones_ok)
    if unmatched:
        add("phone_mismatch", "Contact", 35, "A displayed number is not listed in the verified phone registry.", "दिखाया गया नंबर सत्यापित फोन रिकॉर्ड में नहीं है।")
        if reused:
            add("phone_reused", "Contact", 20, "This number appears on at least two unrelated domains for the same entity.", "यह नंबर इसी संस्था से जुड़े दो अलग वेबसाइटों पर दिखा है।")
    facts = observation.get("facts", {})
    if facts.get("registered_at"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(facts["registered_at"].replace("Z", "+00:00"))).days
            if 0 <= age < 90:
                add("young_domain", "Infrastructure", 20, "Domain registration is less than 90 days old.", "वेबसाइट का पंजीकरण 90 दिन से कम पुराना है।")
        except (ValueError, TypeError):
            pass
    hostname = host(observation.get("url") or d or "") or ""
    if not intermediary and any(hostname == x or hostname.endswith("." + x) for x in FREE):
        add("free_host", "Infrastructure", 15, "A free-hosted page is presenting support information.", "मुफ्त होस्टिंग वाला पेज सहायता की जानकारी दिखा रहा है।")
    if observation.get("kind") == "ad":
        if facts.get("advertiser_verified") is False or facts.get("advertiser_linked") is False:
            add("ad_unlinked", "Ad behavior", 20, "Explicit advertiser evidence does not confirm an official relationship.", "विज्ञापनदाता के प्रमाण में आधिकारिक संबंध की पुष्टि नहीं है।")
        if facts.get("advertiser_new") is True:
            add("ad_new", "Ad behavior", 15, "Available advertiser evidence indicates a new account.", "उपलब्ध प्रमाण के अनुसार विज्ञापनदाता का खाता नया है।")
    if observation.get("kind") == "local" and (facts.get("listing_mismatch") is True or unmatched or (domains and d and not domain_ok and not candidate_domain and not intermediary)):
        # A domain/phone mismatch does not become an independent signal merely
        # because it appeared in Maps. Only separate listing evidence is Local.
        family = "Local" if facts.get("listing_mismatch") is True else ("Contact" if unmatched else "Identity")
        add("listing_mismatch", family, 25, "Listing contact information conflicts with the entity registry.", "लिस्टिंग की संपर्क जानकारी आधिकारिक रिकॉर्ड से मेल नहीं खाती।")
    if d and (d.endswith(".gov.in") or d.endswith(".nic.in")):
        add("government", "Mitigator", -40, "Government domain reduces risk; it does not verify every displayed contact.", "सरकारी वेबसाइट से जोखिम घटता है, पर हर नंबर सत्यापित नहीं होता।")
    if d in REPUTABLE or intermediary:
        add("intermediary", "Mitigator", -20, "A reputable or authorized intermediary reduces identity risk.", "विश्वसनीय या अधिकृत मध्यस्थ से पहचान का जोखिम घटता है।")
    risk = max(0, min(100, sum(s["points"] for s in signals)))
    families = {s["family"] for s in signals if s["points"] > 0}
    if risk >= 75 and len(families) >= 2:
        verdict = "Likely Fraud"
    elif risk >= 50:
        verdict = "Suspicious"
    elif risk >= 20 or candidate_domain or (ps and not phones_ok):
        verdict = "Unverified"
    else:
        verdict = "No Issue Found"
    return {"risk": risk, "verdict": verdict, "signals": signals, "rule_version": RULE_VERSION}
