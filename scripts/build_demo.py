"""Create a single-file offline practice build from the same client source as the live game.

Run: python scripts/build_demo.py [output-path]
The result never contacts a server: it always starts solo practice (window.CONFLUX_OFFLINE).
"""
from pathlib import Path
import base64
import re
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from server import VERSION  # noqa: E402

static = root / 'static'
SCRIPTS = ('logic.js', 'fallback.js', 'scene.js', 'app.js')


def data_url(name: str, mime: str) -> str:
    return f'data:{mime};base64,{base64.b64encode((static / name).read_bytes()).decode("ascii")}'


def build() -> str:
    html = (static / 'index.html').read_text(encoding='utf-8').replace('{{VERSION}}', VERSION)
    css = (static / 'style.css').read_text(encoding='utf-8')
    html = html.replace(f'<link rel="stylesheet" href="/static/style.css?v={VERSION}">', f'<style>\n{css}\n</style>')
    for asset in ('arena-plate.webp', 'arena-mobile.webp'):
        html = html.replace(f'/static/{asset}', data_url(asset, 'image/webp'))
    html = html.replace('href="/static/favicon.svg"', f'href="{data_url("favicon.svg", "image/svg+xml")}"')
    html = re.sub(r'<meta property="og:image"[^>]*>', '', html)
    html = re.sub(r'<script defer src="/static/[a-z]+\.js\?v=[^"]+"></script>', '', html)
    js = '\n'.join((static / name).read_text(encoding='utf-8') for name in SCRIPTS)
    bundle = f'<script>\nwindow.CONFLUX_OFFLINE = true;\n{js}\n</script>'
    assert '</body></html>' in html and '/static/' not in html.replace('/static/cover.png', ''), 'unbundled asset'
    return html.replace('</body></html>', f'{bundle}</body></html>')


if __name__ == '__main__':
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / 'CONFLUX_CORE_OFFLINE_PRACTICE.html'
    output.write_text(build(), encoding='utf-8')
    print(f'{output} ({output.stat().st_size:,} bytes)')
