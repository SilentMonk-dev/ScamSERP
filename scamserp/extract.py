import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit

import phonenumbers
import tldextract

# Bundled PSL: no network fetch on citizen lookups. bank.in is a current Indian suffix.
PSL = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True, extra_suffixes=["bank.in", "example"])


def ascii_digits(text):
    return "".join(str(unicodedata.digit(c)) if c.isdecimal() else c for c in text)


def normalize_phone(value):
    digits = re.sub(r"\D", "", ascii_digits(value))
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits in {"1930", "1947", "112", "1906", "1912", "198", "199"}:
        return "short:" + digits
    if re.fullmatch(r"1(?:800|860)\d{4,9}", digits):
        return "toll:" + digits
    if re.fullmatch(r"140\d{7}", digits):
        return "service:" + digits
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    try:
        parsed = phonenumbers.parse(digits, "IN")
        if phonenumbers.is_possible_number(parsed) and (re.fullmatch(r"[6-9]\d{9}", digits) or phonenumbers.is_valid_number(parsed)):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def phones(text):
    text = ascii_digits(text)
    candidates = re.findall(r"(?<!\w)(?:\+?91[\s().-]*)?(?:\d[\s().-]*){7,13}\d(?!\w)", text)
    candidates += re.findall(r"(?<!\d)(?:1930|1947|1906|1912|112|198|199)(?!\d)", text)
    return sorted({p for v in candidates if (p := normalize_phone(v))})


def host(value):
    value = value.strip()
    if not value or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return None
        hostname = (parsed.hostname or "").rstrip(".").lower()
        hostname = hostname.encode("idna").decode("ascii")
        ipaddress.ip_address(hostname)
        return None  # IP addresses are out of scope, and are never fetched.
    except ValueError:
        if 'hostname' not in locals():
            return None
    except UnicodeError:
        return None
    if "." not in hostname or not re.fullmatch(r"[a-z0-9.-]+", hostname) or any(not x or len(x) > 63 or x.startswith('-') or x.endswith('-') for x in hostname.split('.')):
        return None
    return hostname


def domain(value):
    hostname = host(value)
    if not hostname:
        return None
    parts = PSL(hostname)
    return parts.top_domain_under_public_suffix or hostname


def links(text):
    found = re.findall(r"(?:https?://|www\.)[^\s<>\"']+|(?<![@\w])(?:[\w-]+\.)+(?:com|in|org|net|co|io|example)(?:/[^\s<>\"']*)?", text, re.I)
    return sorted({d for item in found if (d := domain(item.rstrip(".,;:!?)।")))})


def flatten_text(value):
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for k, v in value.items() if k in {"title", "snippet", "description", "phone", "phone_number", "sitelinks", "inline", "expanded", "answer"})
    if isinstance(value, list):
        return " ".join(map(flatten_text, value))
    return str(value) if value is not None else ""


def observations(payload, engine):
    """Normalize documented shapes, without inventing absent advertiser fields."""
    results = []
    def add(items, kind):
        for i, item in enumerate(items or [], 1):
            if isinstance(item, str):
                item = {"title": item}
            if not isinstance(item, dict):
                continue
            url = item.get("website") or item.get("link") or item.get("url")
            text = flatten_text(item)
            try:
                position = max(1, int(item.get("position") or i))
            except (ValueError, TypeError):
                position = i
            facts = {k: item[k] for k in ("advertiser_verified", "advertiser_linked", "advertiser_new", "registered_at", "listing_mismatch") if k in item}
            gps = item.get("gps_coordinates")
            if isinstance(gps, dict):
                lat, lon = gps.get("latitude"), gps.get("longitude")
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and -90 <= lat <= 90 and -180 <= lon <= 180:
                    facts["gps_coordinates"] = {"latitude": lat, "longitude": lon}
            for key in ("address", "place_id", "rating", "reviews", "type"):
                if isinstance(item.get(key), (str, int, float)):
                    facts[key] = item[key]
            results.append({"kind": kind, "position": position, "title": str(item.get("title") or item.get("value") or item.get("question") or item.get("name") or "Untitled result")[:500], "snippet": str(item.get("snippet") or item.get("description") or item.get("answer") or "")[:4000], "url": url if isinstance(url, str) and host(url) else None, "domain": domain(url) if isinstance(url, str) else None, "phones": phones(text), "advertiser_id": item.get("advertiser_id"), "facts": facts})
    if engine == "google_autocomplete":
        add(payload.get("suggestions", []), "autocomplete")
    elif engine in {"google_local", "google_maps"}:
        add(payload.get("ads", []), "ad")
        local = payload.get("local_results", [])
        add(local.get("places", []) if isinstance(local, dict) else local, "local")
    else:
        add(payload.get("organic_results", []), "organic")
        add(payload.get("ads", []), "ad")
        add(payload.get("ads_bottom", []), "ad")
        local = payload.get("local_results", {})
        add(local.get("places", []) if isinstance(local, dict) else local, "local")
        add(payload.get("related_questions", []), "paa")
        add(payload.get("related_searches", []), "related")
        graph = payload.get("knowledge_graph")
        if graph:
            add([graph], "knowledge")
    return results
