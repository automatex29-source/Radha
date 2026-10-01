"""Real text extraction from uploaded documents.

No simulation: each format is parsed with a real library. Pictures and scanned
PDFs are read with OCR (Tesseract) when it is installed. Web pages and XML are
read as text, archives (zip, 7z, tar, gz) are opened and the files inside are
read, and any other file that turns out to be text is read as text. Remaining
binary formats return empty text and produce zero chunks.
"""
import csv
import gzip
import io
import json
import posixpath
import tarfile
import zipfile

SUPPORTED_TEXT = {"txt", "md", "markdown", "json", "csv", "log"}
MARKUP_EXTS = {"html", "htm", "xhtml", "xml", "svg", "rss", "atom", "plist", "xsd", "xsl", "kml", "gpx"}
ARCHIVE_EXTS = {"zip", "7z", "tar", "tgz", "gz", "jar", "apk", "epub", "odt", "ods", "odp"}
ARCHIVE_MAX_FILES = 200
ARCHIVE_MAX_BYTES = 40 * 1024 * 1024  # total unpacked size read from one archive
ARCHIVE_MAX_TEXT = 2_000_000  # characters of text kept from one archive
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
        if ext in MARKUP_EXTS:
            return _markup(data, ext)
        if ext in ARCHIVE_EXTS or ext in ("tbz2", "txz") or zipfile.is_zipfile(io.BytesIO(data)):
            return _archive(data, ext)
    except Exception as exc:  # extraction failures propagate as file error status
        raise RuntimeError(f"Failed to extract {ext}: {exc}")
    return _maybe_text(data)  # code, config and other plain-text files; real binaries give ""


def is_binary(data: bytes) -> bool:
    """True when the bytes don't look like text in any common encoding."""
    sample = data[:8192]
    if not sample:
        return False
    if b"\x00" in sample and not (sample.startswith((b"\xff\xfe", b"\xfe\xff"))):
        return True
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError as exc:
        if exc.start >= len(sample) - 4:  # a character cut off by the sample's end
            return False
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127 or b >= 160)
    return printable / len(sample) < 0.85


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _maybe_text(data: bytes) -> str:
    return "" if is_binary(data) else _decode(data)


def _markup(data: bytes, ext: str) -> str:
    """Readable text of a web page or XML file (scripts and styles dropped)."""
    raw = _decode(data)
    try:
        if ext in ("html", "htm", "xhtml"):
            import lxml.html
            doc = lxml.html.fromstring(raw)
            for bad in doc.xpath("//script|//style|//noscript"):
                bad.drop_tree()
            title = (doc.findtext(".//title") or "").strip()
            body = doc.find("body") if doc.find("body") is not None else doc
            text = "\n".join(t.strip() for t in body.itertext() if t.strip())
            return (f"Title: {title}\n\n" if title else "") + text
        from lxml import etree
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
        if root is not None:
            # Keep the tags: in XML they carry the meaning (<price>, <name>...).
            return etree.tostring(root, pretty_print=True, encoding="unicode")
    except Exception:
        pass
    return raw


def _archive_members(data: bytes, ext: str):
    """(name, bytes) for each file inside an archive, within the size limits."""
    total = 0
    if ext == "7z":
        import py7zr
        with py7zr.SevenZipFile(io.BytesIO(data)) as z:
            infos = [i for i in z.list() if not i.is_directory][:ARCHIVE_MAX_FILES]
            names = []
            for i in infos:
                total += i.uncompressed or 0
                if total > ARCHIVE_MAX_BYTES:
                    break
                names.append(i.filename)
            if names:
                factory = py7zr.io.BytesIOFactory(ARCHIVE_MAX_BYTES)
                z.extract(targets=names, factory=factory)
                for name in names:
                    if name in factory.products:
                        yield name, factory.products[name].read()
        return
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in [i for i in z.infolist() if not i.is_dir()][:ARCHIVE_MAX_FILES]:
                total += info.file_size
                if total > ARCHIVE_MAX_BYTES or info.flag_bits & 0x1:  # too big, or password-protected
                    break
                yield info.filename, z.read(info)
        return
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for member in [m for m in t.getmembers() if m.isfile()][:ARCHIVE_MAX_FILES]:
                total += member.size
                if total > ARCHIVE_MAX_BYTES:
                    break
                f = t.extractfile(member)
                if f:
                    yield member.name, f.read()
        return
    except tarfile.ReadError:
        pass
    if data[:2] == b"\x1f\x8b":  # a single gzipped file
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as g:
            yield "file", g.read(ARCHIVE_MAX_BYTES)


def _archive(data: bytes, ext: str, depth: int = 0) -> str:
    """Text of every readable file inside an archive, each under a '# File: name' heading."""
    parts, size, skipped = [], 0, []
    for name, blob in _archive_members(data, ext):
        if posixpath.basename(name).startswith(".") or "__MACOSX/" in name:
            continue
        inner_ext = name.rsplit(".", 1)[-1].lower() if "." in posixpath.basename(name) else ""
        try:
            if depth == 0 and (inner_ext in ARCHIVE_EXTS):
                text = _archive(blob, inner_ext, depth + 1)
            elif inner_ext in ARCHIVE_EXTS:
                text = ""
            else:
                text = extract_text(blob, inner_ext)
        except Exception:
            text = ""
        if not text.strip():
            skipped.append(name)
            continue
        parts.append(f"# File: {name}\n{text.strip()}")
        size += len(parts[-1])
        if size > ARCHIVE_MAX_TEXT:
            parts.append("# (archive truncated: too much text)")
            break
    if skipped:
        parts.append("# Files with no readable text: " + ", ".join(skipped[:50]))
    return "\n\n".join(parts)


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
