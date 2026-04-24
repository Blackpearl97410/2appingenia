from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def docx_to_markdown(document: Document) -> str:
    blocks = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style and "heading" in paragraph.style.name.lower():
            blocks.append(f"## {text}")
        else:
            blocks.append(text)
    return "\n\n".join(blocks)


def get_uploaded_suffix(uploaded_file) -> str:
    return Path(uploaded_file.name).suffix.lower() or "inconnu"


def get_uploaded_bytes(uploaded_file) -> bytes:
    return uploaded_file.getvalue()


def parse_text_bytes(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore")


def parse_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(BytesIO(file_bytes))


def parse_excel_bytes(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    return pd.read_excel(BytesIO(file_bytes), sheet_name=None)


def parse_pdf_bytes(file_bytes: bytes) -> tuple[str, int, int, str | None]:
    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text.strip())
        return "\n\n".join(pages_text), len(reader.pages), len(pages_text), None
    except PdfReadError as exc:
        return "", 0, 0, f"PDF illisible par le parseur ({exc})"
    except Exception as exc:
        return "", 0, 0, f"Erreur de lecture PDF ({exc.__class__.__name__})"


def parse_docx_bytes(file_bytes: bytes) -> tuple[str, str, int]:
    document = Document(BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    text_content = "\n\n".join(paragraphs)
    markdown_content = docx_to_markdown(document)
    return text_content, markdown_content, len(paragraphs)
