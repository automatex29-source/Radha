"""Real text extraction from uploaded documents.

No simulation: each format is parsed with a real library. Pictures and scanned
PDFs are read with OCR (Tesseract) when it is installed; other binary formats
return empty text and produce zero chunks.
"""
import csv
import io
import json

SUPPORTED_TEXT = {"txt", "md", "markdown", "json", "csv", "log"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}
OCR_MAX_PAGES = 15


def extract_text(data: bytes, ext: str, content_type: str = "") -> str:
    ext = (ext or "").lower()
    try:
        if ext == "pdf":
            return _pdf(data)
        if ext in ("docx",):
            return _docx(data)
        if ext == "pptx":
            return _pptx(data)
        if ext in ("xlsx", "xlsm"):
            return _xlsx(data)
        if ext == "csv":
            return _csv(data)
        if ext == "json":
            return _json(data)
        if ext in SUPPORTED_TEXT:
            return data.decode("utf-8", errors="replace")
        if ext in IMAGE_EXTS:
            return _ocr(data)
    except Exception as exc:  # extraction failures propagate as file error status
        raise RuntimeError(f"Failed to extract {ext}: {exc}")
    return ""  # images and other binaries: no text (vision handled later)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if len(text.strip()) >= 20 * max(1, len(reader.pages)):
        return text
    # Little or no text layer: a scanned PDF. Read the page pictures with OCR.
    scanned = []
    for n, page in enumerate(reader.pages[:OCR_MAX_PAGES], 1):
        try:
            page_text = "\n".join(t for t in (_ocr(img.data) for img in page.images) if t)
        except Exception:
            page_text = ""
        if page_text:
            scanned.append(f"# Page {n}\n{page_text}")
    return "\n\n".join(scanned) if len("".join(scanned)) > len(text.strip()) else text


def _ocr(data: bytes) -> str:
    from vision import ocr
    return ocr(data)


def _docx(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _pptx(data: bytes) -> str:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    out = []
    for n, slide in enumerate(prs.slides, 1):
        out.append(f"# Slide {n}")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    out.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(out)


def _xlsx(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"# Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                out.append(" | ".join(cells))
    wb.close()
    return "\n".join(out)


def _csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    return "\n".join(" | ".join(r) for r in rows)


def _json(data: bytes) -> str:
    obj = json.loads(data.decode("utf-8", errors="replace"))
    return json.dumps(obj, indent=2, ensure_ascii=False)


def chunk_text(text: str, size: int = 220, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks
