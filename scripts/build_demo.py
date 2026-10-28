"""Create a single-file interactive solo practice using the same assets as live game.

Run: python scripts/build_demo.py [optional-output-path]
Does not emulate multiplayer: server.py must be hosted separately for that.
"""
from pathlib import Path
import base64
import sys
root=Path(__file__).resolve().parents[1]
static=root/'static'
html=(static/'index.html').read_text(encoding='utf-8')
html=html.replace('<link rel="stylesheet" href="/static/style.css">',f'<style>\n{(static/"style.css").read_text(encoding="utf-8")}\n</style>')
for asset in ('arena-plate.webp','arena-mobile.webp'):
    encoded=base64.b64encode((static/asset).read_bytes()).decode('ascii')
    html=html.replace(f'/static/{asset}',f'data:image/webp;base64,{encoded}')
html=html.replace('<script defer src="/static/fallback.js"></script><script defer src="/static/scene.js"></script><script defer src="/static/app.js"></script>','')
# Standalone preview is ALWAYS offline practice, including when hosted by a file-preview server.
# Do not let the bundled create-room button contact a server that is not part of this file.
js='\n'.join((static/file).read_text(encoding='utf-8') for file in ['fallback.js','scene.js','app.js'])
js=js.replace("if(new URLSearchParams(location.search).get('demo')==='1'){", "if(true){")
html=html.replace('</body></html>',f'<script>\n{js}\n</script></body></html>')
output=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'CONFLUX_CORE_COMPACT_PLAYABLE_DEMO.html'
output.write_text(html,encoding='utf-8')
print(f'{output} ({output.stat().st_size:,} bytes)')
