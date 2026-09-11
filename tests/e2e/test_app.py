"""End-to-end flows through the Streamlit UI (headless AppTest)."""

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.e2e


def ask(app: AppTest, text: str) -> AppTest:
    app.chat_input[0].set_value(text).run()
    return app


def last_assistant(app: AppTest) -> str:
    messages = [m for m in app.chat_message if m.avatar == "assistant"]
    return "\n".join(md.value for md in messages[-1].markdown)


class TestShell:
    def test_renders_title_sidebar_and_tabs(self, app: AppTest) -> None:
        assert not app.exception
        assert any("PropCo" in t.value for t in app.title)
        sidebar_text = " ".join(m.value for m in app.sidebar.markdown)
        assert "3,924" in sidebar_text
        assert "2025-M03" in sidebar_text
        assert "fake" in sidebar_text
        assert [t.label for t in app.tabs] == ["Chat", "Data explorer", "Anomalies", "Graph"]

    def test_welcome_message_lists_examples(self, app: AppTest) -> None:
        text = last_assistant(app)
        assert "P&L" in text
        assert "Building 17" in text


class TestChat:
    def test_pnl_question_is_answered_with_trace(self, app: AppTest) -> None:
        ask(app, "total P&L for 2024")
        text = last_assistant(app)
        assert "€1,171,521.55" in text
        assert "Steps:" in text
        assert any("trace" in e.label.lower() for e in app.expander)
        assert not app.exception

    def test_pnl_answer_shows_a_headline_metric(self, app: AppTest) -> None:
        ask(app, "total P&L for 2024")
        assert any(m.value == "€1,171,521.55" for m in app.metric)

    def test_period_compare_shows_both_quarters(self, app: AppTest) -> None:
        ask(app, "How does this quarter compare to the same period last year?")
        values = {m.value for m in app.metric}
        assert {"€361,810.32", "€262,309.07"} <= values

    def test_degraded_mode_is_flagged(self, app: AppTest) -> None:
        ask(app, "total P&L for 2024")
        assert any(
            "rule-based" in w.value.lower() or "degraded" in w.value.lower() for w in app.warning
        )

    def test_policy_toggle_changes_numbers(self, app: AppTest) -> None:
        app.radio[0].set_value("dedup").run()
        ask(app, "total P&L for 2024")
        assert "€682,529.72" in last_assistant(app)

    def test_clarification_then_resume(self, app: AppTest) -> None:
        ask(app, "hmm")
        text = last_assistant(app)
        assert "?" in text
        assert any("waiting" in i.value.lower() for i in app.info)
        ask(app, "total P&L for 2024")
        assert "€1,171,521.55" in last_assistant(app)

    def test_resume_turn_shows_a_status_widget(
        self, app: AppTest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # st.rerun() normally wipes the transient status widget immediately; disable it
        # for the turn under test so we can inspect the tree it produced.
        ask(app, "hmm")
        monkeypatch.setattr("streamlit.rerun", lambda: None)
        ask(app, "total P&L for 2024")
        assert len(app.status) >= 1

    def test_unknown_property_suggests_candidates(self, app: AppTest) -> None:
        ask(app, "details for 123 Main St")
        text = last_assistant(app)
        assert "123 Main St" in text
        assert "Building" in text

    def test_history_is_kept_across_turns(self, app: AppTest) -> None:
        ask(app, "total P&L for 2024")
        ask(app, "top 3 tenants in 2024")
        user_messages = [m for m in app.chat_message if m.avatar == "user"]
        assert len(user_messages) == 2
        assert "Tenant 7" in last_assistant(app)

    def test_new_conversation_button_resets_history(self, app: AppTest) -> None:
        ask(app, "total P&L for 2024")
        app.sidebar.button[0].click().run()
        assert len([m for m in app.chat_message if m.avatar == "user"]) == 0

    def test_example_button_asks_the_example(self, app: AppTest) -> None:
        examples = [b for b in app.sidebar.button if "P&L" in b.label]
        assert examples
        examples[0].click().run()
        assert "€" in last_assistant(app)


class TestOtherTabs:
    def test_explorer_shows_tables(self, app: AppTest) -> None:
        assert len(app.dataframe) >= 2
        assert any("Building 120" in str(df.value) for df in app.dataframe)

    def test_anomalies_tab_lists_findings(self, app: AppTest) -> None:
        text = " ".join(m.value for m in app.markdown)
        assert "duplicate" in text.lower()
        assert "4650" in text

    def test_graph_tab_shows_mermaid(self, app: AppTest) -> None:
        # a live-rendered mermaid diagram inside a Streamlit components iframe hit a real,
        # confirmed-with-a-browser rendering bug (every node measured at zero size); a
        # pre-rendered static image sidesteps it entirely and always shows something.
        assert len(app.image) >= 1
        assert any("graph TD" in c.value for c in app.code)
