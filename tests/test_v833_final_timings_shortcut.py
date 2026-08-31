from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_wedding_quick_action_opens_final_timings_directly():
    js = (ROOT / "app/static/v832.js").read_text()
    timings = (ROOT / "app/static/v820.js").read_text()

    assert 'quickAction("◷", "Final timings", "timings")' in js
    assert 'record.kind === "wedding"' in js
    assert 'window.openFinalTimingsRecord?.(record)' in js
    assert 'window.openFinalTimingsRecord=async function(r)' in timings
    assert 'if(submission){showCompleteFinalTimings(r,submission);return}' in timings


def test_waiting_final_timings_opens_on_desktop_and_mobile_journey_views():
    timings = (ROOT / "app/static/v820.js").read_text()

    assert 'await selectRecordTab(r,"Journey",true)' in timings
    assert 'document.querySelector("#drawer .v820-final")' in timings
    assert 'if(tab==="Journey"||tab==="Quote")appendFinalTimings' in timings


def test_v833_build_and_cache_markers_are_consistent():
    index = (ROOT / "app/static/index.html").read_text()
    backup = (ROOT / "app/backup.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    build = (ROOT / "BUILD-VERSION.txt").read_text()

    expected = "2026.08.31-streaming-complete-backup-v8.33.2"
    assert expected in backup
    assert expected in build
    assert 'version="2.8.33.2-streaming-complete-backup"' in main
    assert "/static/v820.js?v=final-timings-pdf-download-v8-33-1" in index
    assert "/static/v832.js?v=final-timings-shortcut-v8-33" in index
    assert "FINAL TIMINGS PDF V8.33.1" in index
