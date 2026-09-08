"""Browser smoke: the deployed artefact renders and answers in a real browser."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def test_page_loads_with_title_and_sidebar(page: Page, app_url: str) -> None:
    page.goto(app_url)
    expect(page.get_by_text("PropCo Agent — real-estate asset assistant")).to_be_visible(
        timeout=30_000
    )
    expect(page.get_by_text("Rows:")).to_be_visible()
    expect(page.get_by_role("tab", name="Chat")).to_be_visible()


def test_question_gets_a_grounded_answer(page: Page, app_url: str) -> None:
    page.goto(app_url)
    box = page.get_by_placeholder("Ask about the portfolio…")
    expect(box).to_be_visible(timeout=30_000)
    box.fill("total P&L for 2024")
    box.press("Enter")
    expect(page.get_by_text("€1,171,521.55").first).to_be_visible(timeout=60_000)
    expect(page.get_by_text("Steps:").first).to_be_visible()


def test_anomalies_tab_shows_findings(page: Page, app_url: str) -> None:
    page.goto(app_url)
    page.get_by_role("tab", name="Anomalies").click()
    expect(page.get_by_text("exact duplicates").first).to_be_visible(timeout=30_000)
