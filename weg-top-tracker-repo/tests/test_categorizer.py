import json

import pandas as pd
import pytest

from wegtop.categorizer import (
    COMPLEXITY_SCORES,
    COST_SCORES,
    OWNER_SCORES,
    _is_reasoning_model,
    build_user_prompt,
    categorize_excel,
    categorize_top,
    compute_score,
)


# -- helpers -----------------------------------------------------------------


def _make_top(
    top_number="1",
    top_title="Genehmigung der Jahresabrechnung",
    description="Die Eigentümer genehmigen die Jahresabrechnung 2024.",
):
    return {
        "meeting_date": "2024-06-15",
        "top_number": top_number,
        "top_title": top_title,
        "description": description,
    }


class _FakeChoice:
    def __init__(self, content: str):
        self.message = type("Msg", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class DummyOpenAIClient:
    """Hand-rolled fake that mimics the OpenAI client interface."""

    def __init__(self, response_json: dict):
        self._response = json.dumps(response_json)
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):  # noqa: ARG002
        return _FakeResponse(self._response)


class CapturingClient:
    """Fake that records the kwargs passed to create() for assertion."""

    def __init__(self, response_json: dict):
        self._response = json.dumps(response_json)
        self.captured_kwargs: dict = {}
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        return _FakeResponse(self._response)


class FailingClient:
    """Fake that raises on create()."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):  # noqa: ARG002
        raise self._exc


# -- compute_score -----------------------------------------------------------


def test_compute_score_minimum():
    assert compute_score("Formalities", "Free", "Easy — single party, no legal challenges") == 1


def test_compute_score_maximum():
    score = compute_score(
        "Whole community of owners",
        "Paid by community — more than 10000 euros",
        "Hard — potential legal challenges",
    )
    assert score == 6 * 6 * 5
    assert score == 180


def test_compute_score_mid_range():
    score = compute_score(
        "Property management",
        "Paid by community — less than 2000 euros",
        "Mid — multiple parties involved, no legal challenges",
    )
    assert score == 2 * 4 * 3
    assert score == 24


def test_compute_score_rejects_unknown_label():
    with pytest.raises(KeyError):
        compute_score("Unknown", "Free", "Easy — single party, no legal challenges")


# -- build_user_prompt -------------------------------------------------------


def test_build_user_prompt_contains_fields():
    top = _make_top(top_number="5", top_title="Sanierung Dach", description="Dach wird saniert.")
    prompt = build_user_prompt(top)
    assert "TOP 5: Sanierung Dach" in prompt
    assert "Dach wird saniert." in prompt
    assert "Beschlusstext:" in prompt


def test_build_user_prompt_handles_missing_fields():
    prompt = build_user_prompt({})
    assert "TOP ?" in prompt


# -- categorize_top ----------------------------------------------------------

_VALID_RESPONSE = {
    "owner": "Formalities",
    "owner_reasoning": "Rein formaler Beschluss.",
    "cost_allocation": "Free",
    "cost_reasoning": "Keine Kosten verbunden.",
    "complexity": "Easy — single party, no legal challenges",
    "complexity_reasoning": "Einfacher Vorgang ohne Rechtsrisiken.",
}


def test_categorize_top_parses_valid_json():
    client = DummyOpenAIClient(_VALID_RESPONSE)
    result = categorize_top(client, "gpt-4o-mini", _make_top())
    assert result["owner"] == "Formalities"
    assert result["cost_allocation"] == "Free"
    assert result["complexity"] == "Easy — single party, no legal challenges"
    assert "Rein formaler Beschluss." in result["owner_reasoning"]


def test_categorize_top_rejects_invalid_owner():
    bad = {**_VALID_RESPONSE, "owner": "Aliens"}
    client = DummyOpenAIClient(bad)
    with pytest.raises(ValueError, match="Unknown owner label"):
        categorize_top(client, "gpt-4o-mini", _make_top())


def test_categorize_top_rejects_invalid_cost():
    bad = {**_VALID_RESPONSE, "cost_allocation": "Priceless"}
    client = DummyOpenAIClient(bad)
    with pytest.raises(ValueError, match="Unknown cost label"):
        categorize_top(client, "gpt-4o-mini", _make_top())


def test_categorize_top_rejects_invalid_complexity():
    bad = {**_VALID_RESPONSE, "complexity": "Impossible"}
    client = DummyOpenAIClient(bad)
    with pytest.raises(ValueError, match="Unknown complexity label"):
        categorize_top(client, "gpt-4o-mini", _make_top())


# -- categorize_excel end-to-end (mocked) -----------------------------------


def test_categorize_excel_end_to_end(tmp_path):
    input_path = tmp_path / "approved.xlsx"
    output_path = tmp_path / "categorized.xlsx"

    df = pd.DataFrame(
        [
            _make_top(top_number="1", top_title="Entlastung"),
            _make_top(top_number="2", top_title="Dachsanierung"),
        ]
    )
    df.to_excel(input_path, sheet_name="Approved_TOPs", index=False)

    responses = [
        {
            "owner": "Formalities",
            "owner_reasoning": "Formaler Beschluss.",
            "cost_allocation": "Free",
            "cost_reasoning": "Keine Kosten.",
            "complexity": "Easy — single party, no legal challenges",
            "complexity_reasoning": "Einfach.",
        },
        {
            "owner": "Whole community of owners",
            "owner_reasoning": "Betrifft alle.",
            "cost_allocation": "Paid by community — more than 10000 euros",
            "cost_reasoning": "Dachsanierung ist teuer.",
            "complexity": "Hard — potential legal challenges",
            "complexity_reasoning": "Vergaberecht beachten.",
        },
    ]

    class SequentialClient:
        def __init__(self, items):
            self._items = iter(items)
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):  # noqa: ARG002
            return _FakeResponse(json.dumps(next(self._items)))

    client = SequentialClient(responses)
    categorize_excel(client, input_path, output_path, model="gpt-4o-mini")

    assert output_path.exists()
    result = pd.read_excel(output_path, sheet_name="Categorized_TOPs")

    assert len(result) == 2
    assert "importance_score" in result.columns
    assert "owner" in result.columns
    assert "cost_allocation" in result.columns
    assert "complexity" in result.columns

    # Sorted descending by importance_score, so Dachsanierung (180) comes first
    assert result.iloc[0]["importance_score"] == 180
    assert result.iloc[0]["owner"] == "Whole community of owners"
    assert result.iloc[1]["importance_score"] == 1
    assert result.iloc[1]["owner"] == "Formalities"


# -- score lookup tables cover all labels -----------------------------------


def test_owner_scores_covers_all_six():
    assert len(OWNER_SCORES) == 6
    assert set(OWNER_SCORES.values()) == {1, 2, 3, 4, 5, 6}


def test_cost_scores_covers_all_six():
    assert len(COST_SCORES) == 6
    assert set(COST_SCORES.values()) == {1, 2, 3, 4, 5, 6}


def test_complexity_scores_covers_all_three():
    assert len(COMPLEXITY_SCORES) == 3
    assert set(COMPLEXITY_SCORES.values()) == {1, 3, 5}


# -- _is_reasoning_model & model dispatch -----------------------------------


def test_is_reasoning_model_detects_reasoning_prefixes():
    assert _is_reasoning_model("o3") is True
    assert _is_reasoning_model("o3-mini") is True
    assert _is_reasoning_model("o4-mini") is True
    assert _is_reasoning_model("gpt-5.2") is True
    assert _is_reasoning_model("gpt-5-mini") is True
    assert _is_reasoning_model("gpt-5-nano") is True


def test_is_reasoning_model_rejects_non_reasoning():
    assert _is_reasoning_model("gpt-4o-mini") is False
    assert _is_reasoning_model("gpt-4.1") is False
    assert _is_reasoning_model("gpt-4-turbo") is False


def test_categorize_top_uses_developer_role_for_reasoning_model():
    client = CapturingClient(_VALID_RESPONSE)
    categorize_top(client, "gpt-5.2", _make_top())
    messages = client.captured_kwargs["messages"]
    assert messages[0]["role"] == "developer"
    assert "temperature" not in client.captured_kwargs


def test_categorize_top_uses_system_role_for_non_reasoning_model():
    client = CapturingClient(_VALID_RESPONSE)
    categorize_top(client, "gpt-4o-mini", _make_top())
    messages = client.captured_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert client.captured_kwargs["temperature"] == 0.0


# -- NaN handling in build_user_prompt --------------------------------------


def test_build_user_prompt_handles_nan_title():
    top = _make_top()
    top["top_title"] = float("nan")
    prompt = build_user_prompt(top)
    assert "nan" not in prompt.lower()
    assert "TOP 1:" in prompt


def test_build_user_prompt_handles_none_title():
    top = _make_top()
    top["top_title"] = None
    prompt = build_user_prompt(top)
    assert "None" not in prompt
    assert "TOP 1:" in prompt


# -- _validate_labels: missing keys -----------------------------------------


def test_categorize_top_rejects_missing_owner_key():
    incomplete = {"cost_allocation": "Free", "complexity": "Hard — potential legal challenges"}
    client = DummyOpenAIClient(incomplete)
    with pytest.raises(ValueError, match="missing required key.*owner"):
        categorize_top(client, "gpt-4o-mini", _make_top())


def test_categorize_top_rejects_missing_cost_key():
    incomplete = {
        "owner": "Formalities",
        "complexity": "Easy — single party, no legal challenges",
    }
    client = DummyOpenAIClient(incomplete)
    with pytest.raises(ValueError, match="missing required key.*cost_allocation"):
        categorize_top(client, "gpt-4o-mini", _make_top())


# -- malformed LLM response ------------------------------------------------


def test_categorize_top_raises_on_invalid_json():
    class BadJsonClient:
        def __init__(self):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):  # noqa: ARG002
            return _FakeResponse("This is not JSON at all")

    with pytest.raises(json.JSONDecodeError):
        categorize_top(BadJsonClient(), "gpt-4o-mini", _make_top())


# -- categorize_excel: error recovery ---------------------------------------


def test_categorize_excel_skips_failed_tops(tmp_path):
    input_path = tmp_path / "approved.xlsx"
    output_path = tmp_path / "categorized.xlsx"

    df = pd.DataFrame(
        [
            _make_top(top_number="1", top_title="Good"),
            _make_top(top_number="2", top_title="Bad"),
            _make_top(top_number="3", top_title="Good again"),
        ]
    )
    df.to_excel(input_path, sheet_name="Approved_TOPs", index=False)

    call_count = 0

    class FailSecondClient:
        def __init__(self):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):  # noqa: ARG002
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM exploded")
            return _FakeResponse(json.dumps(_VALID_RESPONSE))

    client = FailSecondClient()
    categorize_excel(client, input_path, output_path, model="gpt-4o-mini")

    assert output_path.exists()
    result = pd.read_excel(output_path, sheet_name="Categorized_TOPs")
    assert len(result) == 2  # TOP 2 skipped, TOPs 1 and 3 survived


def test_categorize_excel_fail_fast_stops_on_first_error(tmp_path):
    input_path = tmp_path / "approved.xlsx"
    output_path = tmp_path / "categorized.xlsx"

    df = pd.DataFrame([_make_top(top_number="1")])
    df.to_excel(input_path, sheet_name="Approved_TOPs", index=False)

    client = FailingClient(RuntimeError("boom"))
    with pytest.raises(SystemExit):
        categorize_excel(client, input_path, output_path, model="gpt-4o-mini", fail_fast=True)


# -- categorize_excel: empty input ------------------------------------------


def test_categorize_excel_handles_empty_input(tmp_path):
    input_path = tmp_path / "empty.xlsx"
    output_path = tmp_path / "categorized.xlsx"

    pd.DataFrame(columns=["meeting_date", "top_number", "top_title", "description"]).to_excel(
        input_path, sheet_name="Approved_TOPs", index=False
    )

    client = DummyOpenAIClient(_VALID_RESPONSE)
    categorize_excel(client, input_path, output_path, model="gpt-4o-mini")

    assert output_path.exists()
    result = pd.read_excel(output_path, sheet_name="Categorized_TOPs")
    assert len(result) == 0
