"""Turn simple LaTeX into readable plain text, for pages that show text without a formula renderer
(practice quizzes and flashcards). "$\\frac{3}{7}$" becomes "3/7", "$x^{2} \\times y$" becomes "x² × y".

Anything it does not know is left as it was, minus the $ signs and backslashes around it.
"""
import re

_SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "approx": "≈", "equiv": "≡", "infty": "∞", "to": "→", "rightarrow": "→",
    "Rightarrow": "⇒", "leftarrow": "←", "leftrightarrow": "↔", "degree": "°", "circ": "°", "angle": "∠",
    "triangle": "△", "parallel": "∥", "perp": "⊥", "therefore": "∴", "because": "∵", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "sum": "Σ", "prod": "Π", "int": "∫", "partial": "∂", "nabla": "∇", "propto": "∝", "sim": "~",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ", "epsilon": "ε", "varepsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ", "sigma": "σ", "Sigma": "Σ", "tau": "τ",
    "phi": "φ", "varphi": "φ", "omega": "ω", "Omega": "Ω", "eta": "η", "nu": "ν", "chi": "χ", "psi": "ψ",
    "ldots": "…", "cdots": "…", "dots": "…", "%": "%", "$": "$", "{": "{", "}": "}", ",": " ", ";": " ",
    "quad": " ", "qquad": " ", "left": "", "right": "", "displaystyle": "", ",\\": " ",
}
_SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_GROUP = r"\{((?:[^{}]|\{[^{}]*\})*)\}"


def _script(body: str, table) -> str:
    out = body.translate(table)
    return out if all(c != o or c in " " for c, o in zip(body, out)) else None


def _convert(m: str) -> str:
    for _ in range(4):  # nested fractions and roots
        new = re.sub(r"\\[dt]?frac\s*" + _GROUP + r"\s*" + _GROUP,
                     lambda g: f"{_wrap(g.group(1))}/{_wrap(g.group(2))}", m)
        new = re.sub(r"\\sqrt\s*\[([^\]]+)\]\s*" + _GROUP, lambda g: f"{g.group(1)}√({g.group(2)})", new)
        new = re.sub(r"\\sqrt\s*" + _GROUP, lambda g: "√" + _wrap(g.group(1)), new)
        new = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|vec|overline|bar|hat)\s*" + _GROUP,
                     r"\1", new)
        if new == m:
            break
        m = new
    m = re.sub(r"\\sqrt\s*(\w)", r"√\1", m)
    m = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", m)
    for mark, table in (("^", _SUP), ("_", _SUB)):
        def script(g, table=table, mark=mark):
            body = g.group(1) if g.group(1) is not None else g.group(2)
            small = _script(body, table)
            return small if small is not None else f"{mark}({body})" if len(body) > 1 else mark + body
        m = re.sub(re.escape(mark) + r"(?:" + _GROUP + r"|(\w))", script, m)
    m = re.sub(r"\\([A-Za-z]+|[%${},;])", lambda g: _SYMBOLS.get(g.group(1), g.group(1)), m)
    m = m.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]{2,}", " ", m).strip()


def _wrap(part: str) -> str:
    part = _convert(part)
    return part if re.fullmatch(r"[\w.√²³⁰¹⁴-⁹]+", part) else f"({part})"


def plain_math(text: str) -> str:
    """Replace $...$, $$...$$, \\(...\\) and \\[...\\] with readable text. Prices like "$5" are kept."""
    if not text or ("$" not in text and "\\" not in text):
        return text or ""
    text = re.sub(r"\$\$([\s\S]+?)\$\$", lambda g: _convert(g.group(1)), text)
    text = re.sub(r"\\\[([\s\S]+?)\\\]", lambda g: _convert(g.group(1)), text)
    text = re.sub(r"\\\(([\s\S]+?)\\\)", lambda g: _convert(g.group(1)), text)
    # $...$ only when the inside looks like a formula, so "$5 and $10" stays as prices
    text = re.sub(r"\$([^$\n]+?)\$",
                  lambda g: _convert(g.group(1)) if re.search(r"[\\^_{}=]", g.group(1))
                  or not re.search(r"\s", g.group(1)) and not re.match(r"\d", g.group(1)) else g.group(0), text)
    if re.search(r"\\(?:[dt]?frac|sqrt|times|cdot|le|ge|alpha|beta|theta|pi)\b", text):
        text = _convert(text)  # LaTeX written without $ signs
    return text
