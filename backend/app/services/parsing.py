from pathlib import Path

from app.services.chunking import ParsedSection


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def parse_document(path: str) -> list[ParsedSection]:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {suffix}")
    if suffix == ".pdf":
        return _parse_pdf(file_path)
    if suffix == ".docx":
        return _parse_docx(file_path)
    return _parse_text(file_path)


def _parse_text(path: Path) -> list[ParsedSection]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not parts and text.strip():
        parts = [text.strip()]
    return [ParsedSection(text=part, paragraph_index=i + 1) for i, part in enumerate(parts)]


def _parse_pdf(path: Path) -> list[ParsedSection]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sections: list[ParsedSection] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            sections.append(ParsedSection(text=text, page_number=index + 1))
    return sections


def _parse_docx(path: Path) -> list[ParsedSection]:
    from docx import Document

    doc = Document(str(path))
    sections = []
    for index, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if text:
            sections.append(ParsedSection(text=text, paragraph_index=index + 1))
    return sections
