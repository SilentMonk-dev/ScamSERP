"""Source-checked records and explicitly pending candidates, never fabricated audits."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import now
from .extract import normalize_phone

# Four entities were checked against primary sources on 2026-10-09. The rest
# are candidate registry entries requiring an operator's independent review.
ENTITIES = [
    ("sbi", "State Bank of India", "banking", "sbi.bank.in", ["SBI", "एसबीआई"], "https://sbi.bank.in/en/web/customer-care/contact-us", ["1800 1234", "1800 2100", "1800 11 2211", "1800 425 3800"]),
    ("hdfc", "HDFC Bank", "banking", "hdfc.bank.in", ["HDFC"], "https://www.hdfc.bank.in/", []),
    ("icici", "ICICI Bank", "banking", "icici.bank.in", ["ICICI"], "https://www.icici.bank.in/", []),
    ("pnb", "Punjab National Bank", "banking", "pnb.bank.in", ["PNB"], "https://pnb.bank.in/", []),
    ("axis", "Axis Bank", "banking", "axis.bank.in", ["Axis"], "https://www.axis.bank.in/", []),
    ("bob", "Bank of Baroda", "banking", "bankofbaroda.bank.in", ["BOB", "Bank of Baroda"], "https://bankofbaroda.bank.in/", []),
    ("canara", "Canara Bank", "banking", "canarabank.bank.in", ["Canara"], "https://canarabank.bank.in/", []),
    ("union", "Union Bank of India", "banking", "unionbankofindia.bank.in", ["Union Bank"], "https://unionbankofindia.bank.in/", []),
    ("kotak", "Kotak Mahindra Bank", "banking", "kotak.bank.in", ["Kotak"], "https://kotak.bank.in/", []),
    ("indianbank", "Indian Bank", "banking", "indianbank.bank.in", ["Indian Bank"], "https://indianbank.bank.in/", []),
    ("phonepe", "PhonePe", "payments", "phonepe.com", ["PhonePe"], "https://www.phonepe.com/", []),
    ("googlepay", "Google Pay India", "payments", "pay.google.com", ["Google Pay", "GPay"], "https://pay.google.com/intl/en_in/about/", []),
    ("paytm", "Paytm", "payments", "paytm.com", ["Paytm"], "https://paytm.com/", []),
    ("bhim", "BHIM", "payments", "bhimupi.org.in", ["BHIM"], "https://www.bhimupi.org.in/", []),
    ("fastag", "NHAI FASTag", "payments", "ihmcl.co.in", ["FASTag", "IHMCL"], "https://ihmcl.co.in/", []),
    ("pmkisan", "PM Kisan", "government", "pmkisan.gov.in", ["PM Kisan", "पीएम किसान"], "https://pmkisan.gov.in/", []),
    ("passport", "Passport Seva", "government", "passportindia.gov.in", ["Passport", "पासपोर्ट"], "https://www.passportindia.gov.in/psp/CallCenter", ["1800 258 1800"]),
    ("uidai", "Aadhaar / UIDAI", "government", "uidai.gov.in", ["Aadhaar", "UIDAI", "आधार"], "https://uidai.gov.in/en", ["1947"]),
    ("epfo", "EPFO", "government", "epfindia.gov.in", ["EPFO"], "https://www.epfindia.gov.in/", []),
    ("incometax", "Income Tax", "government", "incometax.gov.in", ["Income Tax"], "https://www.incometax.gov.in/", []),
    ("digilocker", "DigiLocker", "government", "digilocker.gov.in", ["DigiLocker"], "https://www.digilocker.gov.in/", []),
    ("irctc", "IRCTC", "government", "irctc.co.in", ["IRCTC"], "https://www.irctc.co.in/", []),
    ("indane", "Indane", "utilities", "iocl.com", ["Indane", "Indian Oil"], "https://iocl.com/", []),
    ("bharatgas", "Bharatgas", "utilities", "bharatpetroleum.in", ["Bharatgas"], "https://www.bharatpetroleum.in/", []),
    ("hpgas", "HP Gas", "utilities", "hindustanpetroleum.com", ["HP Gas"], "https://www.hindustanpetroleum.com/", []),
    ("mseb", "MSEDCL", "utilities", "mahadiscom.in", ["MSEDCL", "Mahavitaran"], "https://www.mahadiscom.in/", []),
    ("tneb", "Tamil Nadu Electricity", "utilities", "tnebnet.org", ["TNEB", "TANGEDCO"], "https://www.tnebnet.org/", []),
    ("indiapost", "India Post", "logistics", "indiapost.gov.in", ["India Post"], "https://www.indiapost.gov.in/", []),
    ("bluedart", "Blue Dart", "logistics", "bluedart.com", ["Blue Dart"], "https://www.bluedart.com/", []),
    ("dtdc", "DTDC", "logistics", "dtdc.in", ["DTDC"], "https://www.dtdc.in/", []),
    ("delhivery", "Delhivery", "logistics", "delhivery.com", ["Delhivery"], "https://www.delhivery.com/", []),
    ("ekart", "Ekart", "logistics", "ekartlogistics.com", ["Ekart"], "https://www.ekartlogistics.com/", []),
    ("airtel", "Airtel", "telecom", "airtel.in", ["Airtel"], "https://www.airtel.in/", []),
    ("jio", "Jio", "telecom", "jio.com", ["Jio"], "https://www.jio.com/", []),
    ("vi", "Vodafone Idea", "telecom", "myvi.in", ["Vodafone", "Vodafone Idea"], "https://www.myvi.in/", []),
    ("amazon", "Amazon India", "ecommerce", "amazon.in", ["Amazon"], "https://www.amazon.in/", []),
    ("flipkart", "Flipkart", "ecommerce", "flipkart.com", ["Flipkart"], "https://www.flipkart.com/", []),
    ("meesho", "Meesho", "ecommerce", "meesho.com", ["Meesho"], "https://www.meesho.com/", []),
    ("myntra", "Myntra", "ecommerce", "myntra.com", ["Myntra"], "https://www.myntra.com/", []),
    ("ajio", "AJIO", "ecommerce", "ajio.com", ["AJIO"], "https://www.ajio.com/", []),
]
CHECKED = {"sbi", "pmkisan", "passport", "uidai"}
LANGUAGES = {"en": "English", "hi": "हिन्दी", "ta": "தமிழ்", "te": "తెలుగు", "bn": "বাংলা", "mr": "मराठी", "hinglish": "Hinglish"}
PHRASES = {
    "en": ["customer care number", "helpline", "complaint support", "office near me"],
    "hi": ["कस्टमर केयर नंबर", "हेल्पलाइन", "शिकायत सहायता", "नजदीकी कार्यालय"],
    "ta": ["வாடிக்கையாளர் சேவை எண்", "உதவி எண்", "புகார் உதவி", "அருகிலுள்ள அலுவலகம்"],
    "te": ["కస్టమర్ కేర్ నంబర్", "హెల్ప్‌లైన్", "ఫిర్యాదు సహాయం", "సమీప కార్యాలయం"],
    "bn": ["কাস্টমার কেয়ার নম্বর", "হেল্পলাইন", "অভিযোগ সহায়তা", "নিকটবর্তী অফিস"],
    "mr": ["ग्राहक सेवा क्रमांक", "हेल्पलाइन", "तक्रार मदत", "जवळचे कार्यालय"],
    "hinglish": ["customer care ka number", "helpline number kya hai", "shikayat kaise kare", "paas ka office"],
}
STATES = {
    "Maharashtra": "Mumbai, Maharashtra, India", "Uttar Pradesh": "Lucknow, Uttar Pradesh, India",
    "Tamil Nadu": "Chennai, Tamil Nadu, India", "Telangana": "Hyderabad, Telangana, India",
    "West Bengal": "Kolkata, West Bengal, India", "Delhi": "New Delhi, Delhi, India",
}


def _seed_base(db):
    if db.one("SELECT value FROM meta WHERE key='seed_version'"):
        return
    with db.connect() as c:
        for id, name, category, d, aliases, source, ps in ENTITIES:
            c.execute("INSERT INTO entity VALUES (?,?,?,?)", (id, name, category, json.dumps(aliases, ensure_ascii=False)))
            for kind, value, display in [("domain", d, d), *[("phone", normalize_phone(p), p) for p in ps]]:
                verified = id in CHECKED
                c.execute("INSERT INTO registry(entity_id,kind,value,display,source_url,verifier,verified_at,expires_at,status) VALUES (?,?,?,?,?,?,?,?,?)", (id, kind, value, display, source, "Primary-source check (automated assistant); human recheck required" if verified else "Awaiting human review", "2026-10-09T00:00:00+00:00" if verified else None, "2026-11-08T00:00:00+00:00" if verified else None, "verified" if verified else "pending"))
            for language, phrases in PHRASES.items():
                for i, phrase in enumerate(phrases):
                    # Manual templates are intentionally labelled; never claim these are real autocomplete suggestions.
                    qid = f"{id}-{language}-{i+1}"
                    c.execute("INSERT INTO query(id,entity_id,text,language,tier,local_intent) VALUES (?,?,?,?,?,?)", (qid, id, f"{aliases[0]} {phrase}", language, 1 if i == 0 else (2 if i < 3 else 3), int(i == 3)))
        c.execute("INSERT INTO meta VALUES ('seed_version','1')")


SPECIAL_PHRASES = {
    "en": ["refund support", "courier tracking", "appointment booking"],
    "hi": ["रिफंड सहायता", "कूरियर ट्रैकिंग", "अपॉइंटमेंट बुकिंग"],
    "ta": ["பணத்தைத் திரும்பப் பெற உதவி", "கூரியர் கண்காணிப்பு", "சந்திப்பு முன்பதிவு"],
    "te": ["రీఫండ్ సహాయం", "కొరియర్ ట్రాకింగ్", "అపాయింట్‌మెంట్ బుకింగ్"],
    "bn": ["রিফান্ড সহায়তা", "কুরিয়ার ট্র্যাকিং", "অ্যাপয়েন্টমেন্ট বুকিং"],
    "mr": ["परतावा मदत", "कुरिअर ट्रॅकिंग", "अपॉइंटमेंट बुकिंग"],
    "hinglish": ["refund kaise milega", "courier tracking kaise kare", "appointment kaise book kare"],
}


def seed_registry(db):
    _seed_base(db)
    if db.one("SELECT value FROM meta WHERE key='query_seed_version'"):
        return
    intents = ["customer_care", "helpline", "complaint", "local_office"]
    with db.connect() as c:
        for eid, name, category, d, aliases, source, ps in ENTITIES:
            for language in PHRASES:
                for i, intent in enumerate(intents, 1):
                    c.execute("UPDATE query SET intent_id=? WHERE id=?", (intent, f"{eid}-{language}-{i}"))
                extras = []
                if category in {"banking", "payments", "utilities", "logistics", "ecommerce", "telecom"}:
                    extras.append(("refund", 0))
                if category == "logistics":
                    extras.append(("tracking", 1))
                if eid == "passport":
                    extras.append(("appointment", 2))
                for intent, index in extras:
                    c.execute("INSERT OR IGNORE INTO query(id,entity_id,text,language,tier,local_intent,origin,intent_id) VALUES (?,?,?,?,2,0,'manual-v2',?)", (f"{eid}-{language}-{intent}", eid, f"{aliases[0]} {SPECIAL_PHRASES[language][index]}", language, intent))
        c.execute("INSERT INTO meta VALUES ('query_seed_version','2')")


def seed_demo(db, pipeline):
    if db.settings.mode != "demo" or db.one("SELECT value FROM meta WHERE key='demo_version'"):
        return
    clock = datetime.now(timezone.utc)
    core = ["sbi", "uidai", "passport", "pmkisan", "hdfc", "phonepe", "indiapost", "airtel", "amazon", "mseb"]
    for entity_index, eid in enumerate(core):
        entity = db.one("SELECT * FROM entity WHERE id=?", (eid,))
        records = db.rows("SELECT * FROM registry WHERE entity_id=?", (eid,))
        official = next(r["value"] for r in records if r["kind"] == "domain")
        phone = next((r["display"] for r in records if r["kind"] == "phone"), "")
        for li, language in enumerate(list(LANGUAGES)[:6]):
            qid = f"{eid}-{language}-1"
            for si, (state, location) in enumerate(STATES.items()):
                for day in (1, 8, 15):
                    # Deterministic synthetic variation, never empirical regional or language claims.
                    flagged = (li + si + entity_index + day) % 3 + 1
                    items = [{"position": 1, "title": f"{entity['name']} — official contact page", "link": f"https://{official}/", "snippet": f"Illustrative official result. {phone}"}, {"position": 2, "title": "General reference guide", "link": "https://en.wikipedia.org/wiki/Customer_service", "snippet": "Illustrative reference result. Always use the entity's own website."}]
                    for rank in range(3, 7):
                        if rank < 3 + flagged:
                            items.append({"position": rank, "title": f"{entity['name']} support (fictional fixture)", "link": f"https://{eid}-care-{rank}.example/", "snippet": "SYNTHETIC TEST ONLY. Fictional support number 1800 000 0000. Do not call."})
                        else:
                            items.append({"position": rank, "title": "Independent help article (fictional fixture)", "link": f"https://guide-{rank}.example/", "snippet": "SYNTHETIC TEST ONLY. General guidance without contact details."})
                    payload = {"search_metadata": {"id": f"demo-{eid}-{language}-{si}-{day}", "status": "Success"}, "organic_results": items, "ads": [{"title": f"{entity['name']} instant help (fictional ad)", "link": f"https://{eid}-priority.example/", "snippet": "SYNTHETIC TEST ONLY. 1800 000 0000.", "advertiser_id": f"DEMO-{eid}", "advertiser_verified": False}], "related_questions": [{"title": "Where can I find the official helpline?", "snippet": "Open the entity's own website."}]}
                    pipeline.ingest(payload, qid, "google", state, location, language, demo=True, fetched_at=(clock - timedelta(days=day)).isoformat(timespec="seconds"), rebuild=False)
                suggestions = {"search_metadata": {"id": f"demo-auto-{eid}-{language}-{si}", "status": "Success"}, "suggestions": [{"value": f"{entity['name']} {PHRASES[language][0]} 24x7 toll free"}]}
                pipeline.ingest(suggestions, qid, "google_autocomplete", state, location, language, demo=True, rebuild=False)
    pipeline.rebuild()
    # Only fictional fixtures are pre-reviewed; real collections always enter pending review.
    db.execute("UPDATE campaign SET review_state='approved',reviewer='Synthetic fixture author',reviewed_at=?", (now(),))
    db.execute("INSERT INTO meta VALUES ('demo_version','1')")
