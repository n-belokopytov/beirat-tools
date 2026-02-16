from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .export.excel_exporter import ExcelExporter
from .models import CategorizedTOP

logger = logging.getLogger(__name__)

OWNER_SCORES: Dict[str, int] = {
    "Formalities": 1,
    "Property management": 2,
    "Individual Owners": 3,
    "Multiple Owners": 4,
    "A building": 5,
    "Whole community of owners": 6,
}

COST_SCORES: Dict[str, int] = {
    "Free": 1,
    "Paid by an individual owner": 2,
    "Paid by Property Management": 3,
    "Paid by community — less than 2000 euros": 4,
    "Paid by community — 2000 to 10000 euros": 5,
    "Paid by community — more than 10000 euros": 6,
}

COMPLEXITY_SCORES: Dict[str, int] = {
    "Easy — single party, no legal challenges": 1,
    "Mid — multiple parties involved, no legal challenges": 3,
    "Hard — potential legal challenges": 5,
}

SYSTEM_PROMPT = """\
You are an experienced German WEG (Wohnungseigentümergemeinschaft) Beirat member \
with 15+ years of experience, a legal expert in WEG-Recht, and a former \
Hausverwaltung professional. You deeply understand German property law, building \
management costs, contractor coordination, and the political dynamics of \
owner communities.

Given a TOP (Tagesordnungspunkt) from a Wohnungseigentümerversammlung protocol, \
classify it along three dimensions.

## Dimension A — Owner of further actions
Who is primarily responsible for executing this decision?
- "Formalities" — procedural items (Protokollgenehmigung, Entlastung, etc.)
- "Property management" — tasks the Hausverwaltung handles alone
- "Individual Owners" — affects/requires action from a single owner
- "Multiple Owners" — requires coordination among several specific owners
- "A building" — affects one building in a multi-building WEG
- "Whole community of owners" — requires action from the entire Eigentümergemeinschaft

## Dimension B — Cost allocation
Who pays, and approximately how much?
- "Free" — no cost (formalities, procedural votes)
- "Paid by an individual owner" — cost borne by one specific owner
- "Paid by Property Management" — covered by Verwaltung fees/budget
- "Paid by community — less than 2000 euros" — small shared expense
- "Paid by community — 2000 to 10000 euros" — moderate shared expense
- "Paid by community — more than 10000 euros" — major shared expense

When the text mentions specific euro amounts, use those. When no amount is stated, \
estimate based on your experience with typical German WEG costs for the type of \
work described.

## Dimension C — Complexity of execution
How difficult is this to implement?
- "Easy — single party, no legal challenges" — straightforward, one responsible party
- "Mid — multiple parties involved, no legal challenges" — coordination needed \
but legally clear
- "Hard — potential legal challenges" — may involve disputes, legal interpretation, \
Anfechtung risk

Respond ONLY with a JSON object (no markdown, no explanation outside the JSON):
{
  "owner": "<exact label from Dimension A>",
  "owner_reasoning": "<1 sentence in German explaining your choice>",
  "cost_allocation": "<exact label from Dimension B>",
  "cost_reasoning": "<1 sentence in German explaining your choice>",
  "complexity": "<exact label from Dimension C>",
  "complexity_reasoning": "<1 sentence in German explaining your choice>"
}"""

_USER_PROMPT_TEMPLATE = """\
TOP {top_number}: {top_title}

Beschlusstext:
{description}"""


def _clean(value: Any, default: str = "") -> str:
    """Coerce a value to str, replacing pandas NaN/None with *default*."""
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return str(value)


def build_user_prompt(top: Dict[str, Any]) -> str:
    return _USER_PROMPT_TEMPLATE.format(
        top_number=_clean(top.get("top_number"), "?"),
        top_title=_clean(top.get("top_title")),
        description=_clean(top.get("description")),
    )


def compute_score(owner: str, cost: str, complexity: str) -> int:
    owner_val = OWNER_SCORES[owner]
    cost_val = COST_SCORES[cost]
    complexity_val = COMPLEXITY_SCORES[complexity]
    return owner_val * cost_val * complexity_val


_REQUIRED_KEYS = ("owner", "cost_allocation", "complexity")


def _validate_labels(result: Dict[str, str]) -> None:
    for key in _REQUIRED_KEYS:
        if key not in result:
            raise ValueError(f"LLM response missing required key: {key!r}")
    if result["owner"] not in OWNER_SCORES:
        raise ValueError(f"Unknown owner label: {result['owner']!r}")
    if result["cost_allocation"] not in COST_SCORES:
        raise ValueError(f"Unknown cost label: {result['cost_allocation']!r}")
    if result["complexity"] not in COMPLEXITY_SCORES:
        raise ValueError(f"Unknown complexity label: {result['complexity']!r}")


_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


def categorize_top(client: Any, model: str, top: Dict[str, Any]) -> Dict[str, Any]:
    """Call the OpenAI API to classify a single TOP. Returns the parsed JSON dict."""
    user_msg = build_user_prompt(top)
    reasoning = _is_reasoning_model(model)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "developer" if reasoning else "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "response_format": {"type": "json_object"},
    }
    if not reasoning:
        kwargs["temperature"] = 0.0
    response = client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content
    result = json.loads(raw)
    _validate_labels(result)
    return result


def categorize_excel(
    client: Any,
    input_path: Path,
    output_path: Path,
    *,
    model: str = "gpt-5.2",
    fail_fast: bool = False,
) -> None:
    """Read approved TOPs from Excel, categorize each via LLM, and write results."""
    df = pd.read_excel(input_path, sheet_name="Approved_TOPs")
    tops = df.to_dict(orient="records")

    categorized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for i, top in enumerate(tops, 1):
        top_num = top.get("top_number", "?")
        logger.info("Categorizing TOP %s (%d/%d)…", top_num, i, len(tops))
        print(f"[{i}/{len(tops)}] Categorizing TOP {top_num}…")

        try:
            result = categorize_top(client, model, top)
        except Exception as exc:  # pylint: disable=broad-except
            errors.append({"top_number": top_num, "error": str(exc)})
            print(f"[ERROR] TOP {top_num}: {exc}", file=sys.stderr)
            if fail_fast:
                raise SystemExit(1) from exc
            continue

        score = compute_score(result["owner"], result["cost_allocation"], result["complexity"])

        row = CategorizedTOP(
            meeting_date=top.get("meeting_date"),
            top_number=top.get("top_number", ""),
            top_title=top.get("top_title"),
            description=top.get("description", ""),
            owner=result["owner"],
            owner_reasoning=result.get("owner_reasoning", ""),
            cost_allocation=result["cost_allocation"],
            cost_reasoning=result.get("cost_reasoning", ""),
            complexity=result["complexity"],
            complexity_reasoning=result.get("complexity_reasoning", ""),
            importance_score=score,
        )
        categorized.append(asdict(row))

    exporter = ExcelExporter()
    exporter.export_categorized(rows=categorized, out_path=output_path)

    if errors:
        print(f"[WARN] {len(errors)} TOP(s) failed categorization.", file=sys.stderr)
    print(f"Categorized {len(categorized)} TOPs → {output_path}")
