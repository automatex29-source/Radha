"""The browser test goes past pressing buttons: it follows the nav links, fills in and submits each form like a
person would, and opens the app at phone size (apps.smoke_test with _link_problems, _form_problems and
_phone_problems)."""
from test_builder_smoke import _smoke

BROKEN = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
@media(max-width:700px){.links{display:none}} .wide{width:800px;height:40px}</style></head><body>
<header><a href="#">Logo</a><span class="links"><a href="#menu">Menu</a><a href="#pricing">Pricing</a><a href="#contact">Contact</a></span></header>
<section id="menu">Menu</section><div class="wide"></div><a href="about.html">About</a>
<form id="contact"><input name="name" required><input type="email" name="email" required><button>Send</button></form>
<form aria-label="Newsletter" onsubmit="event.preventDefault()"><input type="email" required><button>Join</button></form>
</body></html>"""

WORKING = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"></head><body>
<header><a href="#a">A</a> <a href="#b">B</a> <a href="#f">Book</a></header><section id="a">a</section><section id="b">b</section>
<form id="f"><label>Name<input name="name" required></label><label>Phone<input type="tel" name="phone" required></label>
<label>Day<input type="date" name="day" required></label><select name="s" required><option value="">Pick</option><option value="cut">Cut</option></select>
<button>Book</button></form><p id="ok"></p>
<form id="g"><input name="q" required><button>Ask</button></form>
<script>f.onsubmit = e => { e.preventDefault(); ok.textContent = 'Booked! See you soon.'; };
g.onsubmit = e => { e.preventDefault(); alert('Thanks, we will reply soon'); };</script></body></html>"""


def test_broken_links_forms_and_phone_layout_are_found():
    found = " | ".join(_smoke({"index.html": BROKEN}))
    assert 'goes to #pricing, but no section has id="pricing"' in found
    assert "opens about.html, which isn't one of the app's files" in found
    assert "“contact” form: submitting it reloads the page" in found
    assert "“Newsletter” form: submitting it with valid details does nothing" in found
    assert "On a phone (390px wide): the page scrolls sideways" in found
    assert "the menu links are hidden and there's no button to open them" in found


def test_a_working_app_with_forms_passes():
    assert _smoke({"index.html": WORKING}) == []
