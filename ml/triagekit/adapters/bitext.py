"""Adapter for the Bitext customer-support intent dataset (27 intents -> binary escalation, as in human-loop)."""
import csv
from pathlib import Path

from ..schemas import Row

csv.field_size_limit(10**9)
ESCALATE_INTENTS = {"contact_human_agent", "contact_customer_service", "complaint", "payment_issue", "get_refund",
                    "check_cancellation_fee", "registration_problems"}
INTENTS = ["cancel_order", "change_order", "change_shipping_address", "check_cancellation_fee", "check_invoice",
           "check_payment_methods", "check_refund_policy", "complaint", "contact_customer_service", "contact_human_agent",
           "create_account", "delete_account", "delivery_options", "delivery_period", "edit_account", "get_invoice",
           "get_refund", "newsletter_subscription", "payment_issue", "place_order", "recover_password", "registration_problems",
           "review", "set_up_shipping_address", "switch_account", "track_order", "track_refund"]


def load_bitext(path: str | Path, dedupe: bool = True) -> list[Row]:
    """Columns: flags, instruction, category, intent, response. Category = intent; exact duplicate instructions are dropped."""
    rows, seen = [], set()
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = {"instruction", "intent"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Bitext file lacks columns {sorted(missing)}")
        for i, r in enumerate(reader, start=1):
            text = (r["instruction"] or "").strip()
            intent = (r["intent"] or "").strip()
            if not text or not intent:
                continue
            if dedupe:
                if text in seen:
                    continue
                seen.add(text)
            rows.append(Row(id=f"bitext-{i:06d}", text=text, label=1 if intent in ESCALATE_INTENTS else 0, category=intent,
                            split="unassigned", source="bitext:rule_mapped", group_id=None))
    return rows
