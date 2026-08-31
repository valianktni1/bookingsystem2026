import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_large_backup_streams_each_generated_pdf_into_the_zip():
    source = (ROOT / "app/backup.py").read_text()
    browser = (ROOT / "app/static/v814.js").read_text()
    index = (ROOT / "app/static/index.html").read_text()

    assert "def _generated_pdf_entries(" in source
    assert "Iterator[tuple[str, bytes]]" in source
    assert "Creating backup PDFs (" in source
    assert "for name, content in _generated_pdf_entries(db, pdf_warnings, progress):" in source
    assert "generated_pdfs: dict[str, bytes]" not in source
    assert "Large backups can take several minutes" in browser
    assert "/static/v814.js?v=streaming-backup-v8-33-2" in index


def test_streaming_backup_release_keeps_zip64_and_checksums():
    source = (ROOT / "app/backup.py").read_text()

    assert "allowZip64=True" in source
    assert 'archive.writestr("checksums.sha256"' in source
    assert 'report(96, "Writing and checking backup checksums")' in source
