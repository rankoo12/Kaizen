from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class QACase:
    case_id: str
    text: str
    expected_tools: List[str]
    category: str = "generic"


def qa_corpus() -> List[QACase]:
    """Curated QA intent corpus used for planner eval/ablation.

    All cases are chosen so that glue mappings can handle them deterministically.
    """
    cases: List[QACase] = []

    # Navigation
    cases.extend(
        [
            QACase("nav_back", "go back", ["back"], "nav"),
            QACase("nav_forward", "go forward", ["forward"], "nav"),
            QACase("nav_next_page", "go to the next page", ["forward"], "nav"),
            QACase("nav_reload", "reload the page", ["reload"], "nav"),
            QACase("nav_new_tab", "open a new tab", ["newTab"], "nav"),
            QACase("nav_new_tab_login", "open the login page in a new tab", ["newTab"], "nav"),
            QACase("nav_switch_tab_2", "switch to tab 2", ["switchTab"], "nav"),
            QACase("nav_close_tab", "close this tab", ["closeTab"], "nav"),
            QACase("nav_close_window", "close current window", ["closeWindow"], "nav"),
            QACase("nav_switch_window_2", "switch to window 2", ["switchWindow"], "nav"),
        ]
    )

    # Scroll
    cases.extend(
        [
            QACase("scroll_down", "scroll down a bit", ["scroll"], "scroll"),
            QACase("scroll_up_small", "scroll up a little", ["scroll"], "scroll"),
            QACase("scroll_to_top", "scroll to the top", ["scroll"], "scroll"),
            QACase("scroll_left", "scroll left", ["scroll"], "scroll"),
            QACase("scroll_right", "scroll right", ["scroll"], "scroll"),
        ]
    )

    # Downloads
    cases.extend(
        [
            QACase("download_report", "download the report", ["download"], "download"),
            QACase("download_invoice_pdf", "download invoice.pdf", ["download"], "download"),
            QACase("download_csv_export", "download the CSV export", ["download"], "download"),
            QACase("download_logs", "download the logs archive", ["download"], "download"),
        ]
    )

    # URL and text asserts
    cases.extend(
        [
            QACase(
                "url_contains_dashboard",
                "check that the URL contains /dashboard",
                ["assertUrl"],
                "asserts",
            ),
            QACase(
                "url_contains_settings",
                "verify url contains /settings",
                ["assertUrl"],
                "asserts",
            ),
            QACase(
                "error_invalid_password",
                "assert that 'Invalid password' is shown",
                ["assertText"],
                "errors",
            ),
            QACase(
                "text_welcome_back",
                "check that 'Welcome back' is visible",
                ["assertText"],
                "asserts",
            ),
            QACase(
                "text_thank_you",
                "verify that 'Thank you' appears on the page",
                ["assertText"],
                "asserts",
            ),
        ]
    )

    # Forms and typing
    cases.extend(
        [
            QACase("submit_form", "submit the form", ["press"], "forms"),
            QACase("submit_form_short", "submit form", ["press"], "forms"),
            QACase(
                "type_email",
                "type user@example.com into email field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_password",
                "type secret into password field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_search_query",
                "type shoes into search box",
                ["type"],
                "forms",
            ),
            QACase(
                "type_username",
                "type john_doe into username field",
                ["type"],
                "forms",
            ),
        ]
    )

    return cases
