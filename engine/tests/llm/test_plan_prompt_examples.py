from __future__ import annotations

from engine.core.llm.plan_prompt import build_planner_prompt
import engine.api.routes.plan as plan_mod


def test_planner_prompt_includes_login_flow_example():
    prompt = build_planner_prompt("dummy")
    assert "fill the login form and go to the dashboard" in prompt
    assert "assertUrl" in prompt and "Email" in prompt and "Password" in prompt


def test_preview_prompt_includes_login_flow_example():
    p = plan_mod._build_prompt("dummy", context={})
    assert "fill the login form and go to the dashboard" in p
    assert "assertUrl" in p and "Email" in p and "Password" in p
