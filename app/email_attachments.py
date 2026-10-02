"""Bounded attachments for deliberate client emails; never saved publicly."""
import base64
import binascii
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile

from pydantic import BaseModel, Field, model_validator

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 5
TYPES = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class EmailAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=4 * ((MAX_ATTACHMENT_BYTES + 2) // 3))

    @model_validator(mode="after")
    def validate_file(self):
        # Strip directory components from both Windows and Unix filenames.
        self.filename = self.filename.replace("\\", "/").split("/")[-1].strip()
        if not self.filename or any(ord(c) < 32 or ord(c) == 127 for c in self.filename):
            raise ValueError("Attachment filename is invalid")
        suffix = PurePosixPath(self.filename).suffix.lower()
        if suffix not in TYPES:
            raise ValueError("Choose a PDF, JPG, PNG, GIF, WebP, DOC or DOCX file")
        try:
            data = self.decoded()
        except (ValueError, binascii.Error):
            raise ValueError("Attachment could not be read; choose the file again")
        if not data or len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Attachments must be non-empty and no more than 10 MB in total")
        valid = {
            ".pdf": data.startswith(b"%PDF-"),
            ".jpg": data.startswith(b"\xff\xd8\xff"),
            ".jpeg": data.startswith(b"\xff\xd8\xff"),
            ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
            ".gif": data.startswith((b"GIF87a", b"GIF89a")),
            ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
            ".doc": data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        }.get(suffix, False)
        if suffix == ".docx":
            try:
                with ZipFile(BytesIO(data)) as doc:
                    valid = "[Content_Types].xml" in doc.namelist() and "word/document.xml" in doc.namelist()
            except (BadZipFile, OSError):
                valid = False
        if not valid:
            raise ValueError("Attachment contents do not match its file type")
        return self

    def decoded(self):
        return base64.b64decode(self.content_base64, validate=True)

    def transport(self):
        return {"filename": self.filename, "content_type": TYPES[PurePosixPath(self.filename).suffix.lower()],
                "data": self.decoded()}
