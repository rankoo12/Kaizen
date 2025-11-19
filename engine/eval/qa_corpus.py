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
            QACase(
                "nav_back_prev_page",
                "go back to the previous page",
                ["back"],
                "nav",
            ),
            QACase(
                "nav_back_prev_screen",
                "go back to the previous screen",
                ["back"],
                "nav",
            ),
            QACase("nav_forward", "go forward", ["forward"], "nav"),
            QACase("nav_next_page", "go to the next page", ["forward"], "nav"),
            QACase(
                "nav_next_screen",
                "go to the next screen",
                ["forward"],
                "nav",
            ),
            QACase("nav_reload", "reload the page", ["reload"], "nav"),
            QACase("nav_refresh_page", "refresh the page", ["reload"], "nav"),
            QACase("nav_refresh", "refresh", ["reload"], "nav"),
            QACase("nav_new_tab", "open a new tab", ["newTab"], "nav"),
            QACase("nav_new_tab_login", "open the login page in a new tab", ["newTab"], "nav"),
            QACase(
                "nav_new_tab_settings",
                "open settings in a new tab",
                ["newTab"],
                "nav",
            ),
            QACase(
                "nav_new_window",
                "open a new window",
                ["newWindow"],
                "nav",
            ),
            QACase("nav_switch_tab_2", "switch to tab 2", ["switchTab"], "nav"),
            QACase("nav_go_to_tab_3", "go to tab 3", ["switchTab"], "nav"),
            QACase("nav_close_tab", "close this tab", ["closeTab"], "nav"),
            QACase("nav_close_current_tab", "close current tab", ["closeTab"], "nav"),
            QACase("nav_close_window", "close current window", ["closeWindow"], "nav"),
            QACase("nav_switch_window_2", "switch to window 2", ["switchWindow"], "nav"),
            QACase("nav_switch_window_1", "switch to window 1", ["switchWindow"], "nav"),
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
            QACase(
                "scroll_down_footer",
                "scroll down to the footer",
                ["scroll"],
                "scroll",
            ),
            QACase(
                "scroll_down_pricing",
                "scroll down until you see pricing",
                ["scroll"],
                "scroll",
            ),
            QACase(
                "scroll_up_header",
                "scroll up to the header",
                ["scroll"],
                "scroll",
            ),
            QACase(
                "scroll_up_top_page",
                "scroll up to the top of the page",
                ["scroll"],
                "scroll",
            ),
            QACase(
                "scroll_to_bottom",
                "scroll to the bottom",
                ["scroll"],
                "scroll",
            ),
            QACase(
                "scroll_down_more",
                "scroll down a little bit more",
                ["scroll"],
                "scroll",
            ),
            QACase("scroll_left_bit", "scroll left a bit", ["scroll"], "scroll"),
            QACase("scroll_right_bit", "scroll right a bit", ["scroll"], "scroll"),
        ]
    )

    # Downloads
    cases.extend(
        [
            QACase("download_report", "download the report", ["download"], "download"),
            QACase("download_invoice_pdf", "download invoice.pdf", ["download"], "download"),
            QACase("download_csv_export", "download the CSV export", ["download"], "download"),
            QACase("download_logs", "download the logs archive", ["download"], "download"),
            QACase(
                "download_monthly_report_pdf",
                "download the monthly report PDF",
                ["download"],
                "download",
            ),
            QACase(
                "download_user_export_csv",
                "download the user export CSV",
                ["download"],
                "download",
            ),
            QACase(
                "download_error_log",
                "download error-log.txt",
                ["download"],
                "download",
            ),
            QACase(
                "download_screenshots_zip",
                "download the screenshots zip",
                ["download"],
                "download",
            ),
            QACase(
                "download_audit_log",
                "download the audit log",
                ["download"],
                "download",
            ),
            QACase(
                "download_backup_archive",
                "download the backup archive",
                ["download"],
                "download",
            ),
            QACase(
                "download_latest_results",
                "download latest results",
                ["download"],
                "download",
            ),
            QACase(
                "download_transaction_report",
                "download the transaction report",
                ["download"],
                "download",
            ),
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
                "url_contains_settings_assert",
                "assert that url contains /settings",
                ["assertUrl"],
                "asserts",
            ),
            QACase(
                "url_contains_profile_assert",
                "assert that url contains /profile",
                ["assertUrl"],
                "asserts",
            ),
            QACase(
                "url_contains_login_verify",
                "verify that url contains /login",
                ["assertUrl"],
                "asserts",
            ),
            QACase(
                "url_contains_orders_check",
                "check url contains /orders",
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
                "error_email_required",
                "assert that 'Email is required' is shown",
                ["assertText"],
                "errors",
            ),
            QACase(
                "error_password_required",
                "assert that 'Password is required' is shown",
                ["assertText"],
                "errors",
            ),
            QACase(
                "error_username_exists",
                "verify that 'Username already exists' message is shown",
                ["assertText"],
                "errors",
            ),
            QACase(
                "error_invalid_email",
                "check that 'Invalid email address' error is visible",
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
            QACase(
                "text_order_complete",
                "assert that 'Order complete' is visible",
                ["assertText"],
                "asserts",
            ),
            QACase(
                "text_payment_failed",
                'assert that "Payment failed" is shown',
                ["assertText"],
                "asserts",
            ),
            QACase(
                "text_profile_updated",
                "verify that 'Profile updated' appears on the page",
                ["assertText"],
                "asserts",
            ),
            QACase(
                "text_settings_saved",
                "check that 'Settings saved' is visible",
                ["assertText"],
                "asserts",
            ),
            QACase(
                "text_welcome_dashboard",
                "verify that 'Welcome to the dashboard' appears",
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
            QACase(
                "type_first_name",
                "type john into first name field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_last_name",
                "type doe into last name field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_email_input",
                "type john.doe@example.com into email input",
                ["type"],
                "forms",
            ),
            QACase(
                "type_otp_field",
                "type 123456 into otp field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_phone_field",
                "type 555-1234 into phone field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_api_key_field",
                "type my-secret into api key field",
                ["type"],
                "forms",
            ),
            QACase(
                "type_comment_box",
                "type hello world into comment box",
                ["type"],
                "forms",
            ),
            QACase(
                "type_message_field",
                "type this is a test into message field",
                ["type"],
                "forms",
            ),
        ]
    )

    # Clicks and key presses (treated as generic actions)
    cases.extend(
        [
            QACase("click_login", "click Login", ["click"], "actions"),
            QACase("click_signup", "click Sign up", ["click"], "actions"),
            QACase("click_profile_link", "click Profile link", ["click"], "actions"),
            QACase("click_css_button", "click #submit-button", ["click"], "actions"),
            QACase("press_enter", "press Enter", ["press"], "actions"),
            QACase("press_escape", "press Escape", ["press"], "actions"),
            QACase("press_tab", "press Tab", ["press"], "actions"),
            QACase("click_save", "click Save", ["click"], "actions"),
            QACase("click_cancel", "click Cancel", ["click"], "actions"),
            QACase("click_continue", "click Continue", ["click"], "actions"),
            QACase("click_next", "click Next", ["click"], "actions"),
            QACase("click_previous", "click Previous", ["click"], "actions"),
            QACase("click_close_dialog", "click Close dialog", ["click"], "actions"),
            QACase("press_enter_key", "press Enter key", ["press"], "actions"),
            QACase("press_escape_key", "press Escape key", ["press"], "actions"),
            QACase("press_space", "press Space", ["press"], "actions"),
            QACase("press_arrow_down", "press ArrowDown", ["press"], "actions"),
            QACase("press_arrow_up", "press ArrowUp", ["press"], "actions"),
            QACase("press_tab_key", "press Tab key", ["press"], "actions"),
        ]
    )

    return cases
