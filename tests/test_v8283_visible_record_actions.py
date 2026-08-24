from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static(name: str) -> str:
    return (ROOT / "app" / "static" / name).read_text(encoding="utf-8")


def test_more_actions_button_has_a_visible_label_and_menu_state():
    script = read_static("v895.js")

    assert 'id="record-more"' in script
    assert 'aria-haspopup="menu"' in script
    assert 'aria-expanded="false"' in script
    assert 'More actions <span aria-hidden="true">⌄</span>' in script
    assert '$("#record-more").setAttribute("aria-expanded", String(opening))' in script


def test_nested_more_actions_button_has_explicit_header_contrast():
    css = read_static("v895.css")
    index = read_static("index.html")

    assert ".record-more-wrap>#record-more" in css
    assert "color:#fff" in css
    assert "background:#ffffff12" in css
    assert "/static/v895.css?v=visible-record-actions-v8-28-3" in index
    assert "/static/v895.js?v=visible-record-actions-v8-28-3" in index

