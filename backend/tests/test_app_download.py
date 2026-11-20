"""The builder's Download button: the app as one HTML file that opens straight from the computer."""
import io
import zipfile

import pytest

import app_bundle
import apps
import jsx_compile

KIT_PAGE = """<!doctype html><html><head><title>Cakes</title><link rel="stylesheet" href="krish-ui.css">
<link rel="stylesheet" href="style.css"></head><body class="theme-editorial"><h1>Soft inside</h1>
<img src="https://krish-image.invalid/chocolate-cake.jpg?w=800&h=600"><script src="app.js"></script></body></html>"""


def test_one_page_app_is_one_file_with_everything_inside():
    files = {"index.html": KIT_PAGE, "krish-ui.css": apps.KIT_CSS, "style.css": "h1{color:red}",
             "app.js": "document.title = 'x</script>'; RADHA.db.list('cakes')"}
    html = app_bundle.single_file(files, "app1", "https://krish.example")
    assert 'href="krish-ui.css"' not in html and 'src="app.js"' not in html and 'href="style.css"' not in html
    assert "h1{color:red}" in html and ".theme-editorial" in html and "__krishUI" in html
    assert "x<\\/script>" in html  # a script can't end the page's <script> early
    assert "fonts.googleapis.com" in html and "Bodoni" in html
    assert '"https://krish.example"' in html and "/api/appdata/" in html  # logins and data reach this server
    assert "https://krish.example/api/site-image?prompt=chocolate%20cake" in html


def test_outside_links_and_missing_files_are_left_alone():
    page = '<html><head><link rel="stylesheet" href="https://cdn.example/x.css"></head><body><script src="gone.js"></script></body></html>'
    html = app_bundle.single_file({"index.html": page})
    assert 'href="https://cdn.example/x.css"' in html and 'src="gone.js"' in html


def test_several_pages_download_as_pages_that_work_alone():
    files = {"index.html": KIT_PAGE, "about.html": KIT_PAGE.replace("Soft inside", "About"),
             "krish-ui.css": apps.KIT_CSS, "style.css": "h1{color:red}", "app.js": "1", "menu.json": "[]"}
    assert app_bundle.single_file(files) is None
    zf = zipfile.ZipFile(io.BytesIO(app_bundle.pages_zip(files, "cakes")))
    assert sorted(zf.namelist()) == ["cakes/about.html", "cakes/index.html", "cakes/menu.json"]
    assert "h1{color:red}" in zf.read("cakes/about.html").decode()


@pytest.mark.skipif(not jsx_compile.available(), reason="esbuild not installed")
def test_react_app_is_bundled_into_the_page():
    files = {"index.html": '<html><head></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
             "src/main.jsx": "import { createRoot } from 'react-dom/client';\nimport App from './App';\nimport './app.css';\ncreateRoot(document.getElementById('root')).render(<App />);",
             "src/App.jsx": "export default function App() { return <h1>Hello cakes</h1>; }",
             "src/app.css": "h1 { color: rebeccapurple }"}
    html = app_bundle.single_file(files)
    assert 'src="/src/main.jsx"' not in html and '<script type="module">' in html
    assert "Hello cakes" in html and "https://esm.sh/react" in html and "color:#639" in html
