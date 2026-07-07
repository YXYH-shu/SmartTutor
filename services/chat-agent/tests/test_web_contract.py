from pathlib import Path


WEB_APP = Path(__file__).resolve().parents[1] / "web" / "app.js"
WEB_HTML = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_web_binds_enter_to_send_and_shift_enter_to_newline():
    source = WEB_APP.read_text(encoding="utf-8")

    assert 'els.input.addEventListener("keydown"' in source
    assert 'event.key === "Enter"' in source
    assert "!event.shiftKey" in source
    assert "requestSubmit()" in source


def test_web_timeline_renders_full_command_and_result_details():
    source = WEB_APP.read_text(encoding="utf-8")

    assert "renderEventDetails(event)" in source
    assert '"command"' in source
    assert '"stdout"' in source
    assert '"stderr"' in source
    assert '"raw_result"' in source
    assert '"report_markdown"' in source
    assert "preview" not in source


def test_web_scenarios_use_student_tutor_conversation_flow():
    source = WEB_APP.read_text(encoding="utf-8")

    assert "学生视角：科学问答后学情分析" in source
    assert "我是学生 ID 40 的学生" in source
    assert "闭合回路" in source
    assert "请帮我做一个学情分析" in source
    assert "帮学生 5 做 KT 学情分析" not in source


def test_web_has_teacher_perspective_single_message_history_analysis_scenario():
    source = WEB_APP.read_text(encoding="utf-8")

    assert "教师视角：基于历史提问做学情分析" in source
    assert "学生 ID 是 42" in source
    assert "闭合回路才能让小灯泡亮起来" in source
    assert "摩擦力什么时候会帮助运动" in source
    assert "植物生长为什么需要阳光" in source
    assert "请基于这些历史提问，为该学生做一次学情分析" in source


def test_web_has_collapsible_side_panels_for_embedded_layout():
    app_source = WEB_APP.read_text(encoding="utf-8")
    html_source = WEB_HTML.read_text(encoding="utf-8")

    assert 'id="leftPanelToggle"' in html_source
    assert 'id="rightPanelToggle"' in html_source
    assert "isEmbedMode" in app_source
    assert "chatagent.panelState" in app_source
    assert "leftCollapsed" in app_source
    assert "rightCollapsed" in app_source
