"""Document builders: Excel, PowerPoint, Word, PDF and HTML files from structured specs.

The model describes *what* goes in the file (rows, slides, markdown); these
builders own the formatting, so output looks consistent across models.
"""
import io
import os
import re
import zipfile
from typing import Any, List

from markdown_it import MarkdownIt

ACCENT = "6366F1"  # RADHA indigo
MAX_ROWS = 20_000
MAX_SLIDES = 60

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "html": "text/html",
    "zip": "application/zip",
}

# Text files create_file can make, by extension. Office/PDF files have their own builders.
TEXT_TYPES = {
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv", "tsv": "text/tab-separated-values",
    "json": "application/json", "xml": "application/xml", "yaml": "text/plain", "yml": "text/plain",
    "toml": "text/plain", "ini": "text/plain", "env": "text/plain", "log": "text/plain",
    "html": "text/html", "htm": "text/html", "css": "text/plain", "scss": "text/plain", "svg": "image/svg+xml",
    "js": "text/plain", "mjs": "text/plain", "cjs": "text/plain", "jsx": "text/plain", "ts": "text/plain",
    "tsx": "text/plain", "vue": "text/plain", "py": "text/plain", "ipynb": "application/json",
    "java": "text/plain", "kt": "text/plain", "c": "text/plain", "h": "text/plain", "cpp": "text/plain",
    "hpp": "text/plain", "cs": "text/plain", "go": "text/plain", "rs": "text/plain", "rb": "text/plain",
    "php": "text/plain", "swift": "text/plain", "dart": "text/plain", "r": "text/plain", "lua": "text/plain",
    "sql": "text/plain", "sh": "text/plain", "bat": "text/plain", "ps1": "text/plain",
}
# Well-known files that have no extension.
EXTENSIONLESS = {"dockerfile", "makefile", "procfile", "license", "readme", "gemfile", ".gitignore", ".env",
                 ".dockerignore", ".npmrc", ".editorconfig", ".prettierrc"}
MAX_ZIP_FILES = 200


def text_file(filename: str) -> tuple:
    """(safe name, content type) for a text file, or ValueError for types that need another tool."""
    raw = (filename or "").strip().split("/")[-1]
    if raw.lower() in EXTENSIONLESS:
        return raw, "text/plain"
    ext = raw.rsplit(".", 1)[-1].lower() if "." in raw else "txt"
    if ext in ("xlsx", "xls", "docx", "doc", "pptx", "ppt", "pdf"):
        raise ValueError(f"Use the dedicated tool for .{ext} files (create_spreadsheet, create_document or "
                         "create_presentation)")
    if ext not in TEXT_TYPES:
        ext = "txt" if "." not in raw else ext
    return safe_filename(raw, ext), TEXT_TYPES.get(ext, "text/plain")


def _safe_path(path: str) -> str:
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError(f"Bad file path in project: {path!r}")
    return "/".join(re.sub(r"[^\w\-. ]+", "", p) or "file" for p in parts)


def build_zip(files: List[dict], folder: str = "") -> bytes:
    """A ZIP of text files [{path, content}], all inside one top folder."""
    if not isinstance(files, list) or not files:
        raise ValueError("'files' must be a non-empty list of {path, content}")
    if len(files) > MAX_ZIP_FILES:
        raise ValueError(f"Too many files (max {MAX_ZIP_FILES})")
    buf = io.BytesIO()
    seen = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if not isinstance(f, dict):
                raise ValueError("Each file must be {path, content}")
            path = _safe_path(f.get("path"))
            if path in seen:
                continue
            seen.add(path)
            zf.writestr(f"{folder}/{path}" if folder else path, str(f.get("content") or ""))
    return buf.getvalue()


def safe_filename(name: str, ext: str) -> str:
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", (name or "").strip())
    base = re.sub(r"[^\w\- ]+", "", base).strip().replace(" ", "-")[:80] or "document"
    return f"{base}.{ext}"


def _md():
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


# ------------------------------------------------------------------ Excel
# Number formats a sheet gets when the model writes "₹25,000", "26.7%" or "2026-01-01" as text.
# Rupees use Indian grouping (1,20,000 / 12,50,000) like people in India write them.
def _lakh(prefix: str = "", dec: str = "") -> str:
    """Indian grouping (1,20,000 / 1,20,00,000) as an Excel number format."""
    return (f'[>=10000000]{prefix}##\\,##\\,##\\,##0{dec};[>=100000]{prefix}##\\,##\\,##0{dec};'
            f'{prefix}##,##0{dec}')


_CURRENCY = {"$": '"$"', "€": '"€"', "£": '"£"'}


def _signed(fmt: str) -> str:
    """The lakh formats use Excel conditions, and a conditional format drops the minus sign of negative
    numbers. Columns that can go negative get a plain format with an explicit minus instead."""
    if not fmt or not fmt.startswith("[>="):
        return fmt
    last = fmt.split(";")[-1]
    return f"{last.replace('##,##0', '#,##0')};-{last.replace('##,##0', '#,##0')}"
_NUM_RE = re.compile(r"^(?P<neg>[-−(])?\s*(?P<cur>₹|Rs\.?|INR|\$|€|£)?\s*(?P<sign>[-+−])?\s*"
                     r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)\s*(?P<pct>%)?\s*\)?$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TOTAL_RE = re.compile(r"^\s*(grand\s+)?(total|totals|sum|net total|overall)\b", re.I)
_HEADER_FILL, _ZEBRA, _GRID, _TOTAL_FILL = ACCENT, "F5F6FE", "E2E4F0", "E8EAFC"


def _parse_cell(v: Any):
    """(value, number format or None). Text that looks like money, a percentage, a number with thousands
    separators or an ISO date becomes a real number or date, so formulas, sorting and charts work."""
    if isinstance(v, bool) or v is None:
        return v, None
    if isinstance(v, (int, float)):
        return v, None
    s = str(v).strip()
    if not s or s.startswith("="):
        return (s or None), None  # strings beginning with "=" are written as formulas by openpyxl
    if re.fullmatch(r"0\d+", s):
        return s, None  # phone numbers, PIN codes and IDs keep their leading zero
    m = _NUM_RE.match(s)
    if m and not (m.group("neg") == "(" and not s.endswith(")")):
        raw = m.group("num")
        groups = raw.split(".")[0].split(",")
        if len(groups) > 1 and not (all(len(g) == 3 for g in groups[1:]) or
                                    (len(groups[-1]) == 3 and all(len(g) == 2 for g in groups[1:-1]))):
            return s, None  # "1,2,3" is a list, not a number
        num = float(raw.replace(",", ""))
        if m.group("neg") or m.group("sign") in ("-", "−"):
            num = -num
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        if m.group("pct"):
            fmt = "0%" if decimals == 0 else "0." + "0" * min(decimals, 2) + "%"
            return num / 100, ("+" + fmt + ";-" + fmt) if m.group("sign") == "+" else fmt
        value = int(num) if decimals == 0 and abs(num) < 1e15 else num
        cur = m.group("cur")
        dec = ".00" if decimals else ""
        indian = len(groups) > 2 and all(len(g) == 2 for g in groups[1:-1])
        if cur in ("₹", "Rs", "Rs.", "INR"):
            return value, _lakh('"₹"', dec)
        if cur:
            return value, _CURRENCY[cur] + "#,##0" + dec
        if len(groups) > 1:
            return value, _lakh("", dec) if indian else "#,##0" + dec
        return value, None
    d = _DATE_RE.match(s)
    if d:
        import datetime
        try:
            return datetime.date(int(d.group(1)), int(d.group(2)), int(d.group(3))), "dd mmm yyyy"
        except ValueError:
            return s, None
    return s, None


def _cell_value(v: Any):
    return _parse_cell(v)[0]


def _formula_refs(formula: str) -> List[str]:
    return re.findall(r"(?<![A-Z])\$?([A-Z]{1,3})\$?\d+", formula.upper())


def build_xlsx(sheets: List[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if not sheets:
        raise ValueError("at least one sheet is required")
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Krish AI"
    thin = Side(style="thin", color=_GRID)
    grid = Border(left=thin, right=thin, top=thin, bottom=thin)
    total_border = Border(left=thin, right=thin, top=Side(style="medium", color="1F2937"),
                          bottom=Side(style="double", color="1F2937"))
    used_names = set()
    for i, spec in enumerate(sheets):
        name = re.sub(r"[\[\]\*\?/\\:]", "", str(spec.get("name") or f"Sheet{i + 1}"))[:31].strip() or f"Sheet{i + 1}"
        while name.lower() in used_names:
            name = f"{name[:28]} {i + 1}"
        used_names.add(name.lower())
        ws = wb.create_sheet(name)
        ws.sheet_view.showGridLines = False
        ws.sheet_view.zoomScale = 110
        columns = [str(c) for c in spec.get("columns") or []]
        rows = [r if isinstance(r, list) else [r] for r in spec.get("rows") or []]
        if len(rows) > MAX_ROWS:
            raise ValueError(f"too many rows (max {MAX_ROWS})")
        width = max(len(columns), max((len(r) for r in rows), default=0)) or 1
        first_data = 2 if columns else 1
        if columns:
            ws.append(columns)
            ws.row_dimensions[1].height = 26
            for cell in ws[1]:
                cell.font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
                cell.fill = PatternFill("solid", fgColor=_HEADER_FILL)
                cell.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True, indent=1)
                cell.border = grid
            ws.freeze_panes = "A2"

        # Parse every value once; remember the format each column's typed values asked for.
        parsed, col_fmts = [], [dict() for _ in range(width)]
        for row in rows:
            out = []
            for c, v in enumerate(row):
                value, fmt = _parse_cell(v)
                if isinstance(value, (int, float)) and value < 0:
                    fmt = _signed(fmt)
                out.append((value, fmt))
                if fmt and c < width:
                    col_fmts[c][fmt] = col_fmts[c].get(fmt, 0) + 1
            parsed.append(out)
        col_fmt = [max(f, key=f.get) if f else None for f in col_fmts]
        for c in range(width):
            if any(c < len(row) and isinstance(row[c][0], (int, float)) and row[c][0] < 0 for row in parsed):
                col_fmt[c] = _signed(col_fmt[c])
        letter_fmt = {get_column_letter(c + 1): f for c, f in enumerate(col_fmt) if f}

        total_rows = set()
        for r, row in enumerate(parsed):
            ws.append([v for v, _ in row])
            excel_row = first_data + r
            first_text = next((v for v, _ in row if v not in (None, "")), "")
            if isinstance(first_text, str) and _TOTAL_RE.match(first_text):
                total_rows.add(excel_row)
            for c, (value, fmt) in enumerate(row):
                cell = ws.cell(row=excel_row, column=c + 1)
                fmt = fmt or col_fmt[c] if c < width else fmt
                if isinstance(value, str) and value.startswith("=") and not (c < width and col_fmt[c]):
                    refs = {letter_fmt.get(L) for L in _formula_refs(value)}
                    up = value.upper()
                    header = columns[c].lower() if c < len(columns) else ""
                    if "/" in up and ("%" in header or "percent" in header or "share" in header or "used" in header
                                      or "margin" in header or "growth" in header or "rate" in header):
                        fmt = "0.0%"
                    elif len(refs) == 1 and None not in refs and "/" not in up and "*" not in up.split("(")[0]:
                        fmt = refs.pop()
                        if "-" in up.lstrip("=-"):
                            fmt = _signed(fmt)  # a difference can be negative
                if fmt:
                    cell.number_format = fmt
        for col_name, fmt in (spec.get("column_formats") or {}).items():
            if col_name in columns:
                letter = get_column_letter(columns.index(col_name) + 1)
                for cell in ws[letter][first_data - 1:]:
                    cell.number_format = fmt

        # Table look: light grid, zebra rows, numbers on the right, a bold total row.
        last_row = ws.max_row
        for r in range(first_data, last_row + 1):
            total = r in total_rows
            for c in range(1, width + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = total_border if total else grid
                numeric = isinstance(cell.value, (int, float)) or (isinstance(cell.value, str) and cell.value.startswith("="))
                long_text = isinstance(cell.value, str) and not numeric and len(cell.value) > 50
                cell.alignment = Alignment(vertical="center", horizontal="right" if numeric else "left",
                                           wrap_text=long_text, indent=0 if numeric else 1)
                if total:
                    cell.font = Font(name="Calibri", bold=True)
                    cell.fill = PatternFill("solid", fgColor=_TOTAL_FILL)
                elif (r - first_data) % 2 == 1:
                    cell.fill = PatternFill("solid", fgColor=_ZEBRA)
            ws.row_dimensions[r].height = None if any(
                isinstance(ws.cell(row=r, column=c).value, str) and len(ws.cell(row=r, column=c).value) > 50
                for c in range(1, width + 1)) else 20

        for col in range(1, width + 1):
            letter = get_column_letter(col)
            lengths = []
            for cell in ws[letter]:
                v = cell.value
                if v is None:
                    continue
                if isinstance(v, str) and v.startswith("="):
                    lengths.append(12)
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    lengths.append(len(f"{v:,.2f}") + 2)
                elif hasattr(v, "year"):
                    lengths.append(12)
                else:
                    lengths.append(min(len(str(v)), 50))
            header_len = len(columns[col - 1]) + 3 if col <= len(columns) else 0
            ws.column_dimensions[letter].width = min(max(10, header_len, max(lengths, default=8) + 3), 52)
        if columns and rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(width)}{last_row}"
        ws.page_setup.orientation = "landscape" if width > 5 else "portrait"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_title_rows = "1:1" if columns else None
        ws.oddFooter.center.text = "&A  ·  Page &P of &N"

        chart_spec = spec.get("chart")
        if chart_spec and columns and rows:
            kind = chart_spec.get("type", "bar")
            chart = {"line": LineChart, "pie": PieChart}.get(kind, BarChart)()
            chart.title = chart_spec.get("title")
            chart.height, chart.width = 9.5, 18
            chart.style = 10
            cat_col = columns.index(chart_spec["category_column"]) + 1 if chart_spec.get("category_column") in columns else 1
            value_cols = [columns.index(c) + 1 for c in chart_spec.get("value_columns") or [] if c in columns] or \
                         [c for c in range(2, width + 1) if c != cat_col and
                          isinstance(ws.cell(row=first_data, column=c).value, (int, float))][:3] or \
                         [c for c in range(1, width + 1) if c != cat_col][:1]
            if kind == "pie":
                value_cols = value_cols[:1]
            # A total row would dwarf every other bar: chart the data rows only.
            data_last = last_row
            while data_last in total_rows and data_last > first_data:
                data_last -= 1
            for vc in value_cols:
                chart.add_data(Reference(ws, min_col=vc, min_row=1, max_row=data_last), titles_from_data=True)
            chart.set_categories(Reference(ws, min_col=cat_col, min_row=2, max_row=data_last))
            colors = [ACCENT, "22C55E", "F59E0B", "0EA5E9", "EC4899", "14B8A6"]
            if kind == "pie":
                from openpyxl.chart.series import DataPoint
                for k in range(data_last - 1):
                    pt = DataPoint(idx=k)
                    pt.graphicalProperties.solidFill = colors[k % len(colors)]
                    chart.series[0].dPt.append(pt)
                chart.dataLabels = DataLabelList()
                chart.dataLabels.showPercent = True
            else:
                for k, series in enumerate(chart.series):
                    color = colors[k % len(colors)]
                    if kind == "line":
                        series.graphicalProperties.line.solidFill = color
                        series.graphicalProperties.line.width = 28575
                        series.smooth = False
                    else:
                        series.graphicalProperties.solidFill = color
                        series.graphicalProperties.line.solidFill = color
                if kind != "line":
                    chart.gap_width = 60
                # openpyxl hides both axes by default, which leaves Excel charts with no labels.
                chart.x_axis.delete = False
                chart.y_axis.delete = False
                from openpyxl.chart.shapes import GraphicalProperties
                from openpyxl.drawing.line import LineProperties
                chart.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E5E7EB"))
                fmt = ws.cell(row=first_data, column=value_cols[0]).number_format
                if fmt and fmt != "General":
                    chart.y_axis.number_format = fmt
                chart.legend.position = "b" if len(value_cols) > 1 else chart.legend.position
                if len(value_cols) == 1:
                    chart.legend = None
            ws.add_chart(chart, f"{get_column_letter(width + 2)}2")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------- PowerPoint
# Chat decks use the same designed renderer as the Decks page (deck_render), so a deck made in chat
# looks as good as one made there. "dark"/"light" are the old theme names.
THEME_ALIASES = {"dark": "aurora", "light": "snow"}
_CLOSING_RE = re.compile(r"^\s*(thank\s*you|thanks|questions\??|q\s*&\s*a|dhanyavaad|shukriya)\b", re.I)


def _bullet_items(items) -> List[tuple]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append((str(it.get("text", "")), int(it.get("level", 0) or 0)))
        else:
            s = str(it)
            level = (len(s) - len(s.lstrip(" "))) // 2
            out.append((s.strip().lstrip("-•* ").strip(), min(level, 4)))
    return out


def _flat_bullets(items) -> List[str]:
    """Nested bullets become "Parent: child" so nothing is lost on a one-level slide."""
    out = []
    for text, level in _bullet_items(items):
        if not text:
            continue
        if level and out and len(out[-1]) + len(text) < 120:
            out[-1] = f"{out[-1]} — {text}"
        else:
            out.append(text)
    return out


def _to_deck_slide(spec: dict, index: int, total: int) -> dict:
    spec = spec if isinstance(spec, dict) else {"title": str(spec)}
    layout = str(spec.get("layout") or "bullets").strip().lower().replace("-", "_").replace(" ", "_")
    slide = dict(spec)
    slide["bullets"] = _flat_bullets(spec.get("bullets"))
    if layout == "image":
        layout = "image_right"
    if layout in ("title", "cover") or (index == 0 and layout == "bullets" and not slide["bullets"]):
        slide["layout"] = "cover"
    elif layout in ("two_column", "comparison"):
        slide["layout"] = "comparison"
        for side in ("left", "right"):
            col = spec.get(side)
            if not isinstance(col, dict):
                slide[side] = {"title": spec.get(f"{side}_title") or "", "bullets": _flat_bullets(col)}
    elif layout == "quote":
        slide["quote"] = spec.get("quote") or spec.get("title")
        slide["author"] = spec.get("author") or spec.get("subtitle") or ""
        slide["subtitle"] = ""
    elif layout == "bullets" and index == total - 1 and total > 2 and _CLOSING_RE.match(str(spec.get("title") or "")) \
            and len(slide["bullets"]) <= 1:
        slide["layout"] = "closing"
        slide["subtitle"] = spec.get("subtitle") or (slide["bullets"][0] if slide["bullets"] else "")
    else:
        slide["layout"] = layout
    return slide


def build_pptx(slides: List[dict], title: str = "", theme: str = "dark", pictures: dict = None) -> bytes:
    import deck_render

    if not slides:
        raise ValueError("at least one slide is required")
    if len(slides) > MAX_SLIDES:
        raise ValueError(f"too many slides (max {MAX_SLIDES})")
    theme_id = THEME_ALIASES.get((theme or "dark").lower(), (theme or "").lower())
    if theme_id not in deck_render.THEME_IDS:
        theme_id = deck_render.DEFAULT_THEME
    deck = [_to_deck_slide(s, i, len(slides)) for i, s in enumerate(slides)]
    if not title:
        title = next((str(s.get("title")) for s in deck if s.get("layout") == "cover" and s.get("title")), "")
    return deck_render.build_deck_pptx(title, deck, theme_id, (pictures or {}).get if pictures else None)


# ------------------------------------------------------------------- Word
# Word files are read on phones as often as on laptops, so the body is 12pt on
# narrow margins and every heading level is clearly bigger, bolder or coloured.
_DOCX_INK, _DOCX_MUTED, _DOCX_ACCENT = "1F2937", "6B7280", "3730A3"
_DOCX_TINT, _DOCX_RULE = "EEF0FB", "C7CBEF"
# "(2 marks)", "[1 mark]", "(½ Mark)": shown in the accent colour so marks stand out from the question.
_MARKS_RE = re.compile(r"[(\[]\s*(?:\d+(?:\.\d+)?|[½¼¾])\s*marks?\s*[)\]]", re.I)
# A list item that already carries its own label, "(a) ..." or "ii) ...", needs no bullet in front of it.
_OWN_LABEL_RE = re.compile(r"^\s*\(?(?:[a-hA-H]|[ivxIVX]{1,4})\)\s")
# Sections that read best on their own page.
_NEW_PAGE_HEADINGS = re.compile(r"^\s*(answer key|answers|answer sheet|solutions|marking scheme)\b", re.I)


def normalize_markdown(markdown: str) -> str:
    """Repair the Markdown slips models make that would otherwise print raw symbols:
    "##Heading" without a space, and "**Name:**Rohit" (bold that CommonMark won't close)."""
    text = (markdown or "").replace("\r\n", "\n")
    text = re.sub(r"(?m)^( {0,3})(#{1,6})(?=[^#\s])", r"\1\2 ", text)
    return text


def _same_title(a: str, b: str) -> bool:
    """ "Solar Energy in India" and "Solar Energy in India: A Short Report" name the same document."""
    norm = lambda x: re.sub(r"[^\w]+", " ", (x or "").lower()).strip()  # noqa: E731
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or b.startswith(a) or a.startswith(b))


def _set_xml(parent, tag: str, **attrs):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    el = parent.find(qn(tag))
    if el is None:
        el = OxmlElement(tag)
        parent.append(el)
    for k, v in attrs.items():
        el.set(qn(f"w:{k}"), str(v))
    return el


def _para_border(p_pr, side: str, color: str, size: int = 8, space: int = 4):
    from docx.oxml.ns import qn

    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        from docx.oxml import OxmlElement
        borders = OxmlElement("w:pBdr")
        # pBdr must come before shd/spacing/ind in CT_PPr; inserting early keeps Word happy.
        anchor = next((p_pr.find(qn(t)) for t in ("w:shd", "w:tabs", "w:spacing", "w:ind", "w:jc", "w:rPr")
                       if p_pr.find(qn(t)) is not None), None)
        anchor.addprevious(borders) if anchor is not None else p_pr.append(borders)
    _set_xml(borders, f"w:{side}", val="single", sz=size, space=space, color=color)


def _shade(p_pr_or_tc_pr, fill: str):
    _set_xml(p_pr_or_tc_pr, "w:shd", val="clear", color="auto", fill=fill)


def _add_hyperlink(paragraph, url: str, text: str):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    for tag, val in (("w:color", "4F46E5"), ("w:u", "single")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        props.append(el)
    run.append(props)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _add_text(paragraph, text: str, bold: bool, italic: bool, strike: bool, code: bool = False):
    """Add text as runs, colouring marks like "(2 marks)" so they stand apart from the question."""
    from docx.shared import Pt, RGBColor

    pos = 0
    pieces = []
    for m in ([] if code else _MARKS_RE.finditer(text)):
        pieces += [(text[pos:m.start()], False), (m.group(0), True)]
        pos = m.end()
    pieces.append((text[pos:], False))
    for piece, is_marks in pieces:
        if not piece:
            continue
        run = paragraph.add_run(piece)
        # None (not False) leaves the paragraph style in charge, so headings stay bold.
        run.bold, run.italic, run.font.strike = bold or None, italic or None, strike or None
        if is_marks:
            run.italic = True
            run.font.color.rgb = RGBColor.from_string(_DOCX_ACCENT)
        if code:
            run.font.name = "Consolas"
            run.font.size = Pt(10.5)
            run.font.color.rgb = RGBColor.from_string(_DOCX_ACCENT)


# Inline sub-parts: " (a) ", " (ii) ". Only split when the item has an "(a)" or "(i)" to start the run.
_SUBPART_RE = re.compile(r"\s+(?=\((?:[a-h]|i|ii|iii|iv|v|vi)\)\s)")


def _question_layout(segs: list) -> list:
    """Put a question's bold title on its own line, then the question, then each sub-part on its own line:
    "**Fill in the blanks:** (2 marks) (a) ... (b) ..." reads as three lines instead of one long one."""
    n = 0
    while n < len(segs) and segs[n][0] == "text" and segs[n][2]:
        n += 1  # the leading bold title, if any
    rest_text = "".join(seg[1] for seg in segs[n:] if seg[0] == "text")
    # Marks right after the title stay on the title line.
    m = re.match(r"\s*" + _MARKS_RE.pattern + r"\s*", rest_text, re.I)
    keep = len(m.group(0)) if m else 0
    after = rest_text[keep:].strip()
    out = segs[:n]
    split_parts = bool(re.search(r"\((?:a|i)\)\s", rest_text))
    # No title, or "Name: ______" (a blank belongs on the same line): no title line break.
    broke = n == 0 or not after or after.startswith("_")
    for seg in segs[n:]:
        if seg[0] != "text":
            out.append(seg)
            continue
        text = seg[1]
        if not broke:
            take = min(keep, len(text))
            head, text = text[:take], text[take:]
            keep -= take
            if head:
                if head.strip() and not any(o[0] == "text" and o[1] == "\t" for o in out):
                    if out and out[-1][0] == "text":
                        out[-1] = ("text", out[-1][1].rstrip()) + out[-1][2:]
                    out.append(("text", "\t") + seg[2:])  # marks sit at the right margin
                    head = head.lstrip()
                out.append(("text", head.rstrip() if keep == 0 else head) + seg[2:])
            if keep == 0 and text.strip():
                out.append(("text", "\n") + seg[2:])
                text = text.lstrip()
                broke = True
        if split_parts and text:
            text = _SUBPART_RE.sub("\n", text)
        if text:
            out.append(("text", text) + seg[2:])
    if not m:
        # Marks at the end instead ("... its antonym. (1 mark)"): move them to the right margin too.
        for k in range(len(out) - 1, -1, -1):
            if out[k][0] != "text" or not out[k][1].strip():
                continue
            tail = re.search(r"\s*(" + _MARKS_RE.pattern + r")\s*$", out[k][1], re.I)
            if tail and tail.start() > 0 or (tail and k > 0):
                body = out[k][1][:tail.start()]
                out[k:k + 1] = ([("text", body) + out[k][2:]] if body else []) + [
                    ("text", "\t") + out[k][2:], ("text", tail.group(1)) + out[k][2:]]
            break
    return out


def _info_bar(p):
    """ "Time Allowed: 20 Minutes | Total Marks: 15" as one ruled bar, left part left and right part right."""
    from docx.shared import Pt

    ppr = p._p.get_or_add_pPr()
    _para_border(ppr, "top", "1F2937", size=8, space=4)
    _para_border(ppr, "bottom", "1F2937", size=8, space=4)
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(4), Pt(14)
    _right_tab(p)


def _inline_segments(inline_token, question: bool = False, bar: bool = False) -> list:
    """Inline Markdown as segments shared by the Word and PDF builders:
    ("text", text, bold, italic, strike, code) | ("link", url, text). "\n" breaks a line, "\t" jumps to the
    right margin (marks in a question, the right half of a Time | Marks bar)."""
    bold = italic = strike = False
    link = None
    link_text = []
    segs = []  # ("text", text, bold, italic, strike, code) | ("link", url, text)
    for tok in inline_token.children or []:
        if tok.type == "strong_open":
            bold = True
        elif tok.type == "strong_close":
            bold = False
        elif tok.type == "em_open":
            italic = True
        elif tok.type == "em_close":
            italic = False
        elif tok.type == "s_open":
            strike = True
        elif tok.type == "s_close":
            strike = False
        elif tok.type == "link_open":
            link, link_text = tok.attrs.get("href", ""), []
        elif tok.type == "link_close":
            segs.append(("link", link, "".join(link_text) or link))
            link = None
        elif tok.type in ("text", "code_inline", "softbreak", "hardbreak", "html_inline", "image"):
            if tok.type == "html_inline":
                if not re.fullmatch(r"<br\s*/?>", tok.content.strip(), re.I):
                    continue  # <u>, <span> and friends: keep the words, drop the tag
                text = "\n"
            elif tok.type == "image":
                text = tok.content or ""
            else:
                text = "\n" if tok.type == "hardbreak" else " " if tok.type == "softbreak" else tok.content
            if link is not None:
                link_text.append(text)
                continue
            if tok.type == "code_inline":
                segs.append(("text", text, bold, italic, strike, True))
                continue
            # Bold that CommonMark left unclosed ("**Name:**Rohit") arrives as literal **: honour it.
            parts = text.split("**") if tok.type == "text" else [text]
            for n, part in enumerate(parts):
                if n:
                    bold = not bold
                if part:
                    segs.append(("text", part, bold, italic, strike, False))
    merged = []
    for seg in segs:
        if merged and seg[0] == "text" and merged[-1][0] == "text" and merged[-1][2:] == seg[2:]:
            merged[-1] = ("text", merged[-1][1] + seg[1]) + seg[2:]
        else:
            merged.append(seg)
    segs = merged
    if question:
        segs = _question_layout(segs)
    if bar:
        segs = [(seg[0], re.sub(r"\s*\|\s*", "\t", seg[1])) + seg[2:] if seg[0] == "text" else seg for seg in segs]
    return segs


def _inline_runs(paragraph, inline_token, question: bool = False, bar: bool = False):
    for seg in _inline_segments(inline_token, question, bar):
        if seg[0] == "link":
            _add_hyperlink(paragraph, seg[1], seg[2])
        else:
            _add_text(paragraph, seg[1], seg[2], seg[3], seg[4], code=seg[5])


def _style_docx(doc):
    """Page setup and named styles: a readable, consistent house style."""
    from docx.enum.text import WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)  # A4
        section.left_margin = section.right_margin = Cm(2)
        section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
        section.header_distance = section.footer_distance = Cm(0.9)

    def font(style, size, bold=None, color=_DOCX_INK, name="Calibri", italic=None):
        f = style.font
        f.name, f.size = name, Pt(size)
        rpr = style.element.get_or_add_rPr()
        _set_xml(rpr, "w:rFonts", ascii=name, hAnsi=name, eastAsia=name, cs=name)
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            rpr.find(qn("w:rFonts")).attrib.pop(qn(f"w:{attr}"), None)
        if bold is not None:
            f.bold = bold
        if italic is not None:
            f.italic = italic
        f.color.rgb = RGBColor.from_string(color)

    def spacing(style, before, after, line=1.2):
        pf = style.paragraph_format
        pf.space_before, pf.space_after = Pt(before), Pt(after)
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = line

    normal = doc.styles["Normal"]
    font(normal, 12)
    spacing(normal, 0, 6, 1.25)

    title = doc.styles["Title"]
    font(title, 26, bold=True)
    spacing(title, 0, 4, 1.0)
    t_ppr = title.element.get_or_add_pPr()
    for b in t_ppr.findall(qn("w:pBdr")):
        t_ppr.remove(b)
    _para_border(t_ppr, "bottom", _DOCX_ACCENT, size=18, space=8)
    title.paragraph_format.space_after = Pt(14)

    heads = {1: (19, _DOCX_ACCENT, 20, 8), 2: (15.5, _DOCX_INK, 16, 6),
             3: (13.5, _DOCX_ACCENT, 12, 5), 4: (12.5, _DOCX_INK, 10, 4)}
    for level, (size, color, before, after) in heads.items():
        st = doc.styles[f"Heading {level}"]
        font(st, size, bold=True, color=color, italic=False)
        spacing(st, before, after, 1.1)
        st.paragraph_format.keep_with_next = True
    _para_border(doc.styles["Heading 1"].element.get_or_add_pPr(), "bottom", _DOCX_RULE, size=8, space=4)
    # Heading 3 is usually a section of a test or report: a tinted band makes it easy to find.
    h3 = doc.styles["Heading 3"].element.get_or_add_pPr()
    _para_border(h3, "left", _DOCX_ACCENT, size=24, space=6)
    _shade(h3, _DOCX_TINT)

    for name in ("List Bullet", "List Bullet 2", "List Bullet 3", "List Number", "List Number 2", "List Number 3"):
        st = doc.styles[name]
        font(st, 12)
        spacing(st, 2, 4, 1.25)

    quote = doc.styles["Quote"]
    font(quote, 12, italic=True, color="374151")
    spacing(quote, 6, 8, 1.25)
    q_ppr = quote.element.get_or_add_pPr()
    _para_border(q_ppr, "left", _DOCX_ACCENT, size=18, space=10)
    quote.paragraph_format.left_indent = Cm(0.5)


def _page_footer(doc, title: str):
    """Footer with the title and "Page N of M", in small grey type."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    p = doc.sections[0].footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _para_border(p._p.get_or_add_pPr(), "top", "E5E7EB", size=4, space=6)

    def run(text=""):
        r = p.add_run(text)
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor.from_string(_DOCX_MUTED)
        return r

    def field(code):
        for kind, text in (("begin", None), (None, code), ("separate", None), (None, "1"), ("end", None)):
            r = run()
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            elif text == code:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = code
            else:
                el = OxmlElement("w:t")
                el.text = text
            r._r.append(el)

    if title:
        run(f"{title}   ·   ")
    run("Page ")
    field(" PAGE ")
    run(" of ")
    field(" NUMPAGES ")


def _restart_numbering(doc, paragraph, start: int):
    """Give an ordered list its own numbering so a new list starts at 1 (or its own start)."""
    from docx.oxml.ns import qn

    style_ppr = paragraph.style.element.pPr
    if style_ppr is None or style_ppr.numPr is None or style_ppr.numPr.numId is None:
        return None
    numbering = doc.part.numbering_part.element
    base = next((n for n in numbering.findall(qn("w:num")) if n.numId == style_ppr.numPr.numId.val), None)
    if base is None:
        return None
    num = numbering.add_num(base.abstractNumId.val)
    num.add_lvlOverride(ilvl=0).add_startOverride(start)
    return num.numId


def _style_table(table):
    """Header row in the accent colour, light rules, zebra rows, header repeats on each page."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    table.style = "Table Grid"
    tbl_pr = table._tbl.tblPr
    borders = _set_xml(tbl_pr, "w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        _set_xml(borders, f"w:{side}", val="single", sz=4, space=0, color="D1D5DB")
    margins = _set_xml(tbl_pr, "w:tblCellMar")
    for side, w in (("top", 70), ("bottom", 70), ("left", 110), ("right", 110)):
        _set_xml(margins, f"w:{side}", w=w, type="dxa")
    for r, row in enumerate(table.rows):
        if r == 0:
            tr_pr = row._tr.get_or_add_trPr()
            tr_pr.append(OxmlElement("w:tblHeader"))
        for cell in row.cells:
            if r == 0:
                _shade(cell._tc.get_or_add_tcPr(), _DOCX_ACCENT)
            elif r % 2 == 0:
                _shade(cell._tc.get_or_add_tcPr(), "F7F7FB")
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                for run in p.runs:
                    run.font.size = Pt(11)
                    if r == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


_PAPER_WORDS = re.compile(r"\b(test|tests|exam|exams|examination|worksheet|question paper|quiz|assessment|"
                          r"practice paper|sample paper|mock)\b", re.I)
_TEXT_WIDTH_CM = 17.0  # A4 width minus the two 2 cm margins


def _is_paper(title: str, markdown: str) -> bool:
    """A test, worksheet or question paper: laid out like a printed school paper."""
    head = title + " " + "\n".join((markdown or "").splitlines()[:3])
    return bool(_PAPER_WORDS.search(head)) or len(_MARKS_RE.findall(markdown or "")) >= 3


def _right_tab(paragraph, leader=None, pos=_TEXT_WIDTH_CM):
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm

    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Cm(pos), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES if leader else WD_TAB_LEADER.SPACES)


def _student_box(doc):
    """Name / Class / Roll No. / Date with ruled write-in lines, in a light box, as on a printed paper."""
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm, Pt, RGBColor

    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    tbl_pr = table._tbl.tblPr
    borders = _set_xml(tbl_pr, "w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        _set_xml(borders, f"w:{side}", val="single", sz=6, space=0, color="C7CBEF")
    for side in ("insideH", "insideV"):
        _set_xml(borders, f"w:{side}", val="nil")
    margins = _set_xml(tbl_pr, "w:tblCellMar")
    for side, w in (("top", 60), ("bottom", 120), ("left", 160), ("right", 160)):
        _set_xml(margins, f"w:{side}", w=w, type="dxa")
    cell = table.cell(0, 0)
    _shade(cell._tc.get_or_add_tcPr(), "F8F9FD")
    cell.width = Cm(_TEXT_WIDTH_CM)
    inner = _TEXT_WIDTH_CM - 1.6  # inside the cell padding, with room to spare
    for n, (left, right) in enumerate((("Name", "Class"), ("Roll No.", "Date"))):
        p = cell.paragraphs[0] if n == 0 else cell.add_paragraph()
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(10), Pt(0), 1.0
        stops = pf.tab_stops
        stops.add_tab_stop(Cm(inner * 0.58), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES)
        stops.add_tab_stop(Cm(inner * 0.58 + 0.6), WD_TAB_ALIGNMENT.LEFT)
        for k, label in enumerate((left, right)):
            r = p.add_run(f"{label}: ")
            r.bold = True
            r.font.size = Pt(11)
            r.font.color.rgb = RGBColor.from_string("374151")
            # Left field: a ruled tab leader up to the middle. Right field: a fixed write-in line
            # (a leader on the last tab of a table cell is not drawn by every viewer).
            p.add_run("\t\t" if k == 0 else "_" * 24)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _answer_lines(doc, count: int, indent_cm: float = 0.0):
    """Full-width ruled lines to write an answer on."""
    from docx.shared import Cm, Pt

    for _ in range(max(1, min(count, 20))):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(indent_cm)
        pf.space_before, pf.space_after = Pt(14), Pt(0)
        _para_border(p._p.get_or_add_pPr(), "bottom", "9CA3AF", size=4, space=1)


def build_docx(markdown: str, title: str = "") -> bytes:
    from docx import Document
    from docx.enum.text import WD_BREAK
    from docx.shared import Cm, Pt

    doc = Document()
    _style_docx(doc)
    tokens = _md().parse(normalize_markdown(markdown))
    first = next((t for t in tokens if t.type != "hr"), None)
    lead_h1 = first is not None and first.type == "heading_open" and first.tag == "h1"
    if title:
        doc.core_properties.title = title
    lead_text = tokens[tokens.index(first) + 1].content.strip().strip("*") if lead_h1 else ""
    paper = _is_paper(title or lead_text, markdown)
    student_box = paper and not re.search(r"(?im)\bname\s*[:_]", markdown or "")
    if title and not (lead_h1 and _same_title(title, lead_text)):
        t = doc.add_paragraph(title, style="Title")
        if paper:
            t.alignment = 1  # centred, like the top of a printed paper
        lead_h1 = False
        if student_box:
            _student_box(doc)
            student_box = False
    elif lead_h1 and not title:
        doc.core_properties.title = tokens[tokens.index(first) + 1].content.strip().strip("*")
    _page_footer(doc, doc.core_properties.title or "")

    lists = []  # stack of [kind, numId or None]
    quote = 0
    seen_block = False
    seen_h2 = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            text = tokens[i + 1].content
            is_title = lead_h1 and not seen_block and level == 1
            if is_title:
                h = doc.add_paragraph(style="Title")
                if paper:
                    h.alignment = 1
            else:
                h = doc.add_heading(level=min(level, 4))
                if _NEW_PAGE_HEADINGS.match(text.strip("*# ")) and seen_block:
                    h.paragraph_format.page_break_before = True
                elif paper and level == 2:
                    # Each test or part of a paper starts on a fresh page, centred like a paper heading.
                    h.alignment = 1
                    if seen_h2:
                        h.paragraph_format.page_break_before = True
                    seen_h2 = True
            _inline_runs(h, tokens[i + 1])
            if is_title and student_box:
                _student_box(doc)
                student_box = False
            seen_block = True
            i += 3
            continue
        seen_block = seen_block or tok.type.endswith("_open") or tok.type in ("fence", "code_block", "hr")
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            kind = "bullet" if tok.type == "bullet_list_open" else "ordered"
            start = int(tok.attrs.get("start", 1) or 1) if kind == "ordered" else 1
            lists.append([kind, None, start])
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif tok.type == "blockquote_open":
            quote += 1
        elif tok.type == "blockquote_close":
            quote -= 1
        elif tok.type == "paragraph_open":
            inline = tokens[i + 1]
            blank_lines = [ln for ln in inline.content.split("\n") if ln.strip()]
            if blank_lines and all(re.fullmatch(r"\\?_[\\_ ]{4,}", ln.strip()) for ln in blank_lines):
                # A line of nothing but underscores: a proper ruled answer line instead.
                _answer_lines(doc, len(blank_lines), 0.63 * len(lists))
                i += 3
                continue
            if lists and not tokens[i].hidden and tokens[i - 1].type != "list_item_open":
                # A second paragraph inside a list item: indent it under the item, no new number.
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.63 * len(lists))
            elif lists:
                kind, num_id, start = lists[-1]
                base = "List Bullet" if kind == "bullet" else "List Number"
                depth = min(len(lists), 3)
                style = base if depth == 1 else f"{base} {depth}"
                if kind == "bullet" and _OWN_LABEL_RE.match(inline.content):
                    # "(a) ..." already has a label; a bullet in front of it is noise.
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Cm(0.63 * max(depth - 1, 1) + 0.1)
                    p.paragraph_format.space_after = Pt(4)
                else:
                    p = doc.add_paragraph(style=style)
                    if kind == "ordered":
                        if num_id is None:
                            num_id = lists[-1][1] = _restart_numbering(doc, p, start)
                        if num_id is not None:
                            num_pr = p._p.get_or_add_pPr().get_or_add_numPr()
                            num_pr.get_or_add_ilvl().val = 0
                            num_pr.get_or_add_numId().val = num_id
            else:
                p = doc.add_paragraph(style="Quote" if quote else None)
                if tokens[i - 1].type == "heading_close" and len(inline.content) < 160:
                    # A heading's short subline ("Total Marks: 15 | Time: 20 min") stays with what follows.
                    p.paragraph_format.keep_with_next = True
                    if paper and inline.content.count("|") == 1:
                        _info_bar(p)
                        _inline_runs(p, inline, bar=True)
                        i += 3
                        continue
            question = bool(lists) and lists[-1][0] == "ordered"
            if question:
                _right_tab(p)
            _inline_runs(p, inline, question=question)
            i += 3
            continue
        elif tok.type in ("fence", "code_block"):
            p = doc.add_paragraph()
            ppr = p._p.get_or_add_pPr()
            _shade(ppr, "F3F4F6")
            p.paragraph_format.left_indent = Cm(0.2)
            p.paragraph_format.line_spacing = 1.0
            lines = tok.content.rstrip("\n").split("\n")
            for n, line in enumerate(lines):
                run = p.add_run(line)
                run.font.name = "Consolas"
                run.font.size = Pt(10)
                if n < len(lines) - 1:
                    run.add_break(WD_BREAK.LINE)
        elif tok.type == "hr" and paper and "_" in (tok.markup or ""):
            _answer_lines(doc, 1, 0.63 * len(lists))
        elif tok.type == "hr":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(10)
            _para_border(p._p.get_or_add_pPr(), "bottom", "D1D5DB", size=6, space=1)
        elif tok.type == "table_open":
            rows, j = [], i + 1
            while tokens[j].type != "table_close":
                if tokens[j].type == "tr_open":
                    rows.append([])
                elif tokens[j].type == "inline":
                    rows[-1].append(tokens[j])
                j += 1
            n_cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=n_cols)
            for r, row in enumerate(rows):
                for c, cell_tok in enumerate(row):
                    cell_p = table.cell(r, c).paragraphs[0]
                    _inline_runs(cell_p, cell_tok)
            _style_table(table)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
            i = j
        i += 1
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# -------------------------------------------------------------------- PDF
# Noto Sans ships with the app (assets/fonts/noto) so PDFs look the same everywhere and Indian scripts
# render: Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi and Urdu.
_NOTO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "noto")
_NOTO_SCRIPTS = ["Devanagari", "Bengali", "Tamil", "Telugu", "Gujarati", "Kannada", "Malayalam", "Gurmukhi"]
_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"]
# Wide-coverage fonts used for glyphs the bundled fonts lack (CJK). Extend with PDF_FALLBACK_FONTS=path1:path2.
_FALLBACK_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/truetype/unifont/unifont.ttf",
]


def _find_font():
    for d in _FONT_DIRS:
        regular = os.path.join(d, "DejaVuSans.ttf")
        if os.path.exists(regular):
            return d
    return None


def _setup_pdf_fonts(pdf) -> tuple:
    """Register fonts on the FPDF object. Returns (body family, mono family, unicode ok)."""
    noto = os.path.join(_NOTO_DIR, "NotoSans-Regular.ttf")
    dejavu = _find_font()
    fallbacks = []
    if os.path.exists(noto):
        for style, name in (("", "Regular"), ("B", "Bold"), ("I", "Italic"), ("BI", "BoldItalic")):
            path = os.path.join(_NOTO_DIR, f"NotoSans-{name}.ttf")
            pdf.add_font("Noto", style, path if os.path.exists(path) else noto)
        family = "Noto"
        for script in _NOTO_SCRIPTS + ["Arabic"]:
            base = f"NotoNaskh{script}" if script == "Arabic" else f"NotoSans{script}"
            regular = os.path.join(_NOTO_DIR, f"{base}-Regular.ttf")
            if not os.path.exists(regular):
                continue
            pdf.add_font(script, "", regular)
            bold = os.path.join(_NOTO_DIR, f"{base}-Bold.ttf")
            pdf.add_font(script, "B", bold if os.path.exists(bold) else regular)
            fallbacks.append(script)
    elif dejavu:
        regular = os.path.join(dejavu, "DejaVuSans.ttf")
        pdf.add_font("DejaVu", "", regular)
        for style, fname in (("B", "DejaVuSans-Bold.ttf"), ("I", "DejaVuSans-Oblique.ttf"),
                             ("BI", "DejaVuSans-BoldOblique.ttf")):
            path = os.path.join(dejavu, fname)
            pdf.add_font("DejaVu", style, path if os.path.exists(path) else regular)
        family = "DejaVu"
    else:
        return "Helvetica", "Courier", False
    mono = "Courier"
    if dejavu:
        mono_path = os.path.join(dejavu, "DejaVuSansMono.ttf")
        if os.path.exists(mono_path):
            pdf.add_font("DejaVuMono", "", mono_path)
            mono = "DejaVuMono"
        if family != "DejaVu":
            # Symbols and arrows Noto Sans lacks (✓ ★ → ∑ ...).
            pdf.add_font("DejaVuFallback", "", os.path.join(dejavu, "DejaVuSans.ttf"))
            fallbacks.append("DejaVuFallback")
    extra = [p for p in os.environ.get("PDF_FALLBACK_FONTS", "").split(":") if p]
    for i, path in enumerate(extra + _FALLBACK_FONTS):
        if os.path.exists(path) and path.lower().endswith((".ttf", ".otf")):
            try:
                pdf.add_font(f"Fallback{i}", "", path)
                fallbacks.append(f"Fallback{i}")
            except Exception:
                pass
    if fallbacks:
        pdf.set_fallback_fonts(fallbacks, exact_match=False)
    try:
        # Shaping joins Indian-script letters and matras correctly (needs uharfbuzz).
        pdf.set_text_shaping(True)
    except Exception:
        pass
    return family, mono, True


class _PdfRenderer:
    """Renders markdown-it tokens with fpdf2 primitives in the same house style as the Word builder."""

    INK, ACCENT, MUTED, SOFT = (17, 24, 39), (79, 70, 229), (75, 85, 99), (107, 114, 128)
    TINT, RULE = (238, 240, 251), (199, 203, 239)
    HEADINGS = {1: (19, INK), 2: (15, ACCENT), 3: (12.5, INK), 4: (11.5, INK), 5: (11, MUTED), 6: (10.5, MUTED)}
    BODY = 11

    def __init__(self, pdf, family: str, mono: str, paper: bool = False):
        self.pdf, self.family, self.mono, self.paper = pdf, family, mono, paper
        self.base_margin = pdf.l_margin

    def _font(self, style="", size=11, mono=False):
        self.pdf.set_font(self.mono if mono else self.family, style=style if not mono else "", size=size)

    def _right(self):
        return self.pdf.w - self.pdf.r_margin

    def _room(self, mm: float):
        """Start a new page when less than `mm` is left, so a heading never sits alone at the bottom."""
        pdf = self.pdf
        if pdf.get_y() + mm > pdf.h - pdf.b_margin:
            pdf.add_page()

    def write_segs(self, segs, size=None, color=None, base_style="", align_center=False):
        pdf = self.pdf
        size = size or self.BODY
        color = color or self.INK
        h = size * 0.52
        if align_center:
            text = "".join(seg[1] if seg[0] == "text" else seg[2] for seg in segs).replace("\t", "  ")
            bold = all(seg[2] for seg in segs if seg[0] == "text" and seg[1].strip()) or "B" in base_style
            self._font("B" if bold else base_style.replace("B", ""), size)
            pdf.set_text_color(*color)
            pdf.multi_cell(0, h * 1.05, text.strip(), align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*self.INK)
            return
        # Split into lines at "\n"; within a line, pieces after a "\t" sit against the right margin.
        lines = [[[], []]]
        for seg in segs:
            if seg[0] == "link":
                lines[-1][1 if lines[-1][1] else 0].append(seg)
                continue
            for part in re.split(r"(\n|\t)", seg[1]):
                if part == "\n":
                    lines.append([[], []])
                elif part == "\t":
                    lines[-1][1].append(("text", "") + seg[2:])  # marks the jump even if nothing follows yet
                elif part:
                    lines[-1][1 if lines[-1][1] else 0].append(("text", part) + seg[2:])
        for n, (left, right) in enumerate(lines):
            if n:
                pdf.ln(h + 0.6)
                pdf.set_x(pdf.l_margin)
            for seg in left:
                self._piece(seg, size, color, base_style, h)
            right = [seg for seg in right if seg[0] == "link" or seg[1]]
            if right:
                width = 0
                for seg in right:
                    self._piece(seg, size, color, base_style, h, measure=True)
                    width += pdf.get_string_width(seg[2] if seg[0] == "link" else seg[1])
                x = self._right() - width
                if x < pdf.get_x() + 3:
                    pdf.ln(h)
                pdf.set_x(max(pdf.l_margin, x))
                for seg in right:
                    self._piece(seg, size, color, base_style, h, cell=True)
        pdf.set_text_color(*self.INK)

    def _piece(self, seg, size, color, base_style, h, measure=False, cell=False):
        """Write one segment (or only set its font, to measure it)."""
        pdf = self.pdf
        if seg[0] == "link":
            self._font("U" + ("B" if "B" in base_style else ""), size)
            if not measure:
                pdf.set_text_color(*self.ACCENT)
                first_word = (seg[2] or "").split(" ")[0]
                if pdf.get_x() > pdf.l_margin + 1 and pdf.get_x() + pdf.get_string_width(first_word) > self._right():
                    pdf.ln(h)
                    pdf.set_x(pdf.l_margin)
                pdf.write(h, seg[2], link=seg[1] if re.match(r"https?://|mailto:", seg[1] or "") else "")
                pdf.set_text_color(*self.INK)
            return
        text, bold, italic, _strike, code = seg[1:6]
        style = base_style + ("B" if bold else "") + ("I" if italic else "")
        style = "".join(sorted(set(style), key="BIU".index))
        if code:
            self._font(size=size * 0.88, mono=True)
            pdf.set_text_color(55, 48, 163)
        else:
            self._font(style, size)
            pdf.set_text_color(*(self.ACCENT if _MARKS_RE.fullmatch(text.strip()) else color))
        if measure:
            return
        if cell:  # right-margin pieces never wrap
            pdf.cell(pdf.get_string_width(text) + 0.4, h, text)
            return
        first = re.match(r"\S+", text)
        if first and pdf.get_x() > pdf.l_margin + 1 and \
                pdf.get_x() + pdf.get_string_width(first.group()) > self._right() and len(first.group()) < 30:
            pdf.ln(h)  # a word that doesn't fit moves to the next line instead of being cut in two
            pdf.set_x(pdf.l_margin)
        pdf.write(h, text)

    def title_block(self, text: str):
        pdf = self.pdf
        self._font("B", 23)
        pdf.set_text_color(*self.INK)
        pdf.multi_cell(0, 10, text, align="C" if self.paper else "L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
        pdf.set_draw_color(*self.ACCENT)
        pdf.set_line_width(0.8)
        y = pdf.get_y()
        if self.paper:
            mid = pdf.w / 2
            pdf.line(mid - 12, y, mid + 12, y)
        else:
            pdf.line(pdf.l_margin, y, pdf.l_margin + 22, y)
        pdf.ln(7)

    def student_box(self):
        pdf = self.pdf
        x, y, w = pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_fill_color(248, 249, 253)
        pdf.set_draw_color(*self.RULE)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, w, 22, style="DF")
        self._font("B", 10.5)
        pdf.set_text_color(55, 65, 81)
        pdf.set_draw_color(156, 163, 175)
        pdf.set_line_width(0.25)
        for row, (left, right) in enumerate((("Name", "Class"), ("Roll No.", "Date"))):
            ty = y + 8 + row * 9
            for col, label in enumerate((left, right)):
                lx = x + 5 + col * w * 0.58
                end = x + w * (0.54 if col == 0 else 1) - 5
                pdf.set_xy(lx, ty - 3.2)
                pdf.cell(pdf.get_string_width(label + ": ") + 1, 5, label + ":")
                pdf.line(pdf.get_x() + 1, ty + 1.2, end, ty + 1.2)
        pdf.set_text_color(*self.INK)
        pdf.set_xy(pdf.l_margin, y + 28)

    def info_bar(self, segs):
        pdf = self.pdf
        pdf.set_draw_color(31, 41, 55)
        pdf.set_line_width(0.35)
        y = pdf.get_y() + 1
        pdf.line(pdf.l_margin, y, self._right(), y)
        pdf.set_xy(pdf.l_margin, y + 2)
        self.write_segs(segs, 10.5, base_style="B")
        pdf.ln(6.5)
        pdf.line(pdf.l_margin, pdf.get_y(), self._right(), pdf.get_y())
        pdf.ln(5)

    def answer_lines(self, count: int):
        pdf = self.pdf
        pdf.set_draw_color(156, 163, 175)
        pdf.set_line_width(0.25)
        for _ in range(max(1, min(count, 20))):
            self._room(9)
            pdf.ln(8)
            pdf.line(pdf.l_margin, pdf.get_y(), self._right(), pdf.get_y())
        pdf.ln(4)

    def heading(self, level: int, segs, new_page: bool = False, centre: bool = False):
        pdf = self.pdf
        size, color = self.HEADINGS[level]
        if self.paper and level == 2:
            color = self.INK
        if new_page and pdf.get_y() > pdf.t_margin + 1:
            pdf.add_page()
        else:
            self._room(28)
            pdf.ln(5 if level <= 2 else 3)
        pdf.set_x(pdf.l_margin)
        if level == 3:
            # A tinted band with an accent edge, like the Word file's section headings.
            y, hh = pdf.get_y(), size * 0.52 + 3.2
            pdf.set_fill_color(*self.TINT)
            pdf.rect(pdf.l_margin, y, pdf.w - pdf.l_margin - pdf.r_margin, hh, style="F")
            pdf.set_fill_color(*self.ACCENT)
            pdf.rect(pdf.l_margin, y, 1.1, hh, style="F")
            pdf.set_xy(pdf.l_margin + 3.5, y + 1.6)
            self.write_segs(segs, size, color, "B")
            pdf.set_y(y + hh)
            pdf.ln(2.5)
            return
        self.write_segs(segs, size, color, "B", align_center=centre)
        if not centre:
            pdf.ln(size * 0.52)
        if level == 1 or (level == 2 and not self.paper):
            pdf.set_draw_color(*(self.ACCENT if level == 1 else self.RULE))
            pdf.set_line_width(0.6 if level == 1 else 0.3)
            y = pdf.get_y() + 0.8
            pdf.line(pdf.l_margin, y, pdf.l_margin + 18 if level == 1 else self._right(), y)
            pdf.ln(3.5)
        else:
            pdf.ln(2)

    def table(self, rows):
        pdf = self.pdf
        from fpdf.fonts import FontFace

        n = max(len(r) for r in rows)
        rows = [r + [""] * (n - len(r)) for r in rows]
        body = rows[1:] or rows
        numeric = [c > 0 and sum(bool(re.fullmatch(r"[-+(]?[₹$€£]?\s?[\d,.]+%?\)?", v.strip())) for v in
                                 (r[c] for r in body) if v.strip()) * 2 > len(body) for c in range(n)]
        longest = [max(min(len(r[c]), 40) for r in rows) + 4 for c in range(n)]
        pdf.ln(1.5)
        self._font(size=9.5 if n > 4 else 10)
        pdf.set_draw_color(209, 213, 219)
        pdf.set_line_width(0.2)
        with pdf.table(headings_style=FontFace(emphasis="B", color=(255, 255, 255), fill_color=(79, 70, 229)),
                       line_height=5.4, padding=(1.8, 2.4, 1.8, 2.4), col_widths=tuple(longest),
                       text_align=tuple("RIGHT" if num else "LEFT" for num in numeric),
                       cell_fill_color=(246, 247, 254), cell_fill_mode="ROWS", repeat_headings=1) as table:
            for r in rows:
                row = table.row()
                for c in range(n):
                    row.cell(r[c])
        pdf.ln(4)

    @staticmethod
    def _plain(inline_tok) -> str:
        return "".join(seg[1] if seg[0] == "text" else seg[2] for seg in _inline_segments(inline_tok)).replace("\t", " ")

    def render(self, tokens, title: str = "", student_box: bool = False):
        pdf = self.pdf
        lists = []  # [kind, counter]
        quote = 0
        seen_block = bool(title)
        seen_h2 = False
        item_started = False
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            t = tok.type
            if t == "heading_open":
                level = int(tok.tag[1])
                inline = tokens[i + 1]
                text = inline.content.strip("*# ")
                if level == 1 and not seen_block:
                    self.title_block(self._plain(inline))
                    if student_box:
                        self.student_box()
                        student_box = False
                else:
                    new_page = bool(_NEW_PAGE_HEADINGS.match(text)) and seen_block
                    centre = self.paper and level == 2
                    if centre:
                        new_page = new_page or seen_h2
                        seen_h2 = True
                    self.heading(level, _inline_segments(inline), new_page=new_page, centre=centre)
                seen_block = True
                i += 3
                continue
            seen_block = seen_block or t.endswith("_open") or t in ("fence", "code_block", "hr")
            if t in ("bullet_list_open", "ordered_list_open"):
                lists.append(["ul" if t == "bullet_list_open" else "ol", int(tok.attrs.get("start", 1) or 1) - 1])
                pdf.set_left_margin(self.base_margin + 6.5 * len(lists) + 6 * quote)
            elif t in ("bullet_list_close", "ordered_list_close"):
                lists.pop()
                pdf.set_left_margin(self.base_margin + 6.5 * len(lists) + 6 * quote)
                if not lists:
                    pdf.ln(1.5)
            elif t == "list_item_open":
                kind = lists[-1]
                kind[1] += 1
                nxt = tokens[i + 2] if i + 2 < len(tokens) else None
                own_label = kind[0] == "ul" and nxt is not None and nxt.type == "inline" and \
                    bool(_OWN_LABEL_RE.match(nxt.content))
                if kind[0] == "ol":
                    self._room(14)
                pdf.set_x(pdf.l_margin)
                if not own_label:
                    marker = f"{kind[1]}." if kind[0] == "ol" else ("•" if len(lists) % 2 else "◦")
                    self._font("B" if kind[0] == "ol" else "", self.BODY)
                    pdf.set_text_color(*self.ACCENT)
                    pdf.set_x(pdf.l_margin - 6)
                    pdf.cell(6, self.BODY * 0.52, marker)
                    pdf.set_text_color(*self.INK)
                item_started = True
            elif t == "list_item_close":
                if lists and lists[-1][0] == "ol":
                    pdf.ln(1.2)
            elif t == "blockquote_open":
                quote += 1
                pdf.set_left_margin(pdf.l_margin + 6)
                self._quote_top = pdf.get_y()
            elif t == "blockquote_close":
                quote -= 1
                pdf.set_draw_color(*self.RULE)
                pdf.set_line_width(1)
                pdf.line(pdf.l_margin - 3.5, self._quote_top, pdf.l_margin - 3.5, pdf.get_y() - 1.5)
                pdf.set_left_margin(pdf.l_margin - 6)
                pdf.ln(1)
            elif t == "paragraph_open":
                inline = tokens[i + 1]
                lines = [ln for ln in inline.content.split("\n") if ln.strip()]
                if lines and all(re.fullmatch(r"\\?_[\\_ ]{4,}", ln.strip()) for ln in lines):
                    self.answer_lines(len(lines))
                    item_started = False
                    i += 3
                    continue
                if self.paper and not lists and tokens[i - 1].type == "heading_close" and \
                        inline.content.count("|") == 1 and len(inline.content) < 160:
                    self.info_bar(_inline_segments(inline, bar=True))
                    i += 3
                    continue
                if not item_started:
                    pdf.set_x(pdf.l_margin)
                    if lists:
                        pdf.ln(0.5)
                item_started = False
                question = bool(lists) and lists[-1][0] == "ol"
                self.write_segs(_inline_segments(inline, question=question), self.BODY,
                                self.MUTED if quote else self.INK, "I" if quote else "")
                pdf.ln(self.BODY * 0.52 + (0.9 if lists else 2.6))
                i += 3
                continue
            elif t in ("fence", "code_block"):
                pdf.ln(1)
                self._font(size=9, mono=True)
                pdf.set_fill_color(243, 244, 246)
                pdf.set_text_color(31, 41, 55)
                pdf.multi_cell(0, 4.6, tok.content.rstrip("\n"), fill=True, padding=(2.5, 3, 2.5, 3),
                               new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(*self.INK)
                pdf.ln(3)
            elif t == "hr" and self.paper and "_" in (tok.markup or ""):
                self.answer_lines(1)  # "______" under a question is a line to write on, not a divider
            elif t == "hr":
                pdf.ln(2)
                pdf.set_draw_color(209, 213, 219)
                pdf.set_line_width(0.3)
                pdf.line(pdf.l_margin, pdf.get_y(), self._right(), pdf.get_y())
                pdf.ln(4)
            elif t == "table_open":
                rows, j = [], i + 1
                while tokens[j].type != "table_close":
                    if tokens[j].type == "tr_open":
                        rows.append([])
                    elif tokens[j].type == "inline":
                        rows[-1].append(self._plain(tokens[j]))
                    j += 1
                if rows:
                    self.table(rows)
                i = j
            i += 1


def build_pdf(markdown: str, title: str = "") -> bytes:
    from fpdf import FPDF

    class _Doc(FPDF):
        doc_title = ""
        footer_family = "Helvetica"

        def footer(self):
            self.set_y(-13)
            self.set_draw_color(229, 231, 235)
            self.set_line_width(0.2)
            self.line(self.l_margin_base, self.get_y() - 1.5, self.w - self.r_margin, self.get_y() - 1.5)
            self.set_font(self.footer_family, "", 8.5)
            self.set_text_color(107, 114, 128)
            self.set_x(self.l_margin_base)
            self.cell(120, 5, self.doc_title[:90])
            self.set_x(self.w - self.r_margin - 40)
            self.cell(40, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    pdf = _Doc(format="A4")
    pdf.set_margins(20, 18, 20)
    pdf.l_margin_base = 20
    pdf.set_auto_page_break(True, margin=20)
    family, mono, unicode_ok = _setup_pdf_fonts(pdf)
    markdown = normalize_markdown(markdown)
    if not unicode_ok:
        # Core fonts are Latin-1 only.
        markdown = markdown.replace("•", "-").replace("₹", "Rs.").encode("latin-1", "replace").decode("latin-1")
        title = (title or "").encode("latin-1", "replace").decode("latin-1")
    pdf.footer_family = family
    tokens = _md().parse(markdown)
    first = next((t for t in tokens if t.type != "hr"), None)
    lead_h1 = first is not None and first.type == "heading_open" and first.tag == "h1"
    lead_text = tokens[tokens.index(first) + 1].content.strip().strip("*") if lead_h1 else ""
    paper = _is_paper(title or lead_text, markdown)
    student_box = paper and not re.search(r"(?im)\bname\s*[:_]", markdown or "")
    show_title = bool(title) and not (lead_h1 and _same_title(title, lead_text))
    pdf.doc_title = lead_text if lead_h1 and not show_title else (title or lead_text)
    if pdf.doc_title:
        pdf.set_title(pdf.doc_title)
    pdf.set_creator("Krish AI by EmpireX")
    pdf.set_author("Krish AI")
    pdf.add_page()
    renderer = _PdfRenderer(pdf, family, mono, paper=paper)
    if show_title:
        renderer.title_block(title)
        if student_box:
            renderer.student_box()
            student_box = False
    renderer.render(tokens, title=title if show_title else "", student_box=student_box)
    return bytes(pdf.output())
