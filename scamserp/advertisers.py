"""Evidence joins; domain-search candidates never prove ownership of an observed ad."""
import json

from .trust import active


def joined_facts(observation, advertisers, reviews):
    facts = json.loads(observation["facts_json"])
    if observation["kind"] != "ad":
        return facts
    review = reviews.get(observation["id"])
    current_review = bool(review and active(review))
    aid = review["advertiser_id"] if current_review else observation["advertiser_id"]
    record = advertisers.get(aid)
    evidence = json.loads(record["data_json"]) if record else None
    if evidence:
        facts["advertiser_evidence"] = {**evidence, "advertiser_id": aid, "checked_at": record["checked_at"], "attribution": "human-reviewed" if current_review else "search-result advertiser ID"}
        # Only explicit status is adverse. Normal documented payloads lack it.
        if evidence.get("verification_status") == "unverified":
            facts["advertiser_verified"] = False
    if current_review:
        facts["advertiser_relationship_review"] = review
        if review["relationship"] in {"linked", "unlinked"}:
            facts["advertiser_linked"] = review["relationship"] == "linked"
    return facts
