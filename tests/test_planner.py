import pytest

from app.planner import ClaudePlanner, OpenAICompatiblePlanner, PlannerError, make_planner


def test_default_provider_is_openai_compatible(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(make_planner(), OpenAICompatiblePlanner)


def test_anthropic_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert isinstance(make_planner(), ClaudePlanner)


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(PlannerError, match="unknown LLM_PROVIDER"):
        make_planner()


@pytest.mark.parametrize(
    ("planner_class", "missing"),
    [(ClaudePlanner, "ANTHROPIC_API_KEY"), (OpenAICompatiblePlanner, "OPENAI_MODEL")],
)
def test_missing_configuration(monkeypatch, planner_class, missing):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(PlannerError, match=missing) as error:
        planner_class().plan("How many records?", [])
    assert error.value.status_code == 503
