"""Regenerate ../CONFLUX_CORE_PROJECT_MANUAL.md from the maintained docs.  Run: python scripts/build_manual.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = [('README', 'README.md'), ('Current status', 'docs/CURRENT_STATUS.md'), ('Protocol', 'docs/PROTOCOL.md'),
         ('Deployment', 'docs/DEPLOYMENT.md'), ('Testing', 'docs/TESTING.md'), ('Changelog', 'docs/CHANGELOG.md'),
         ('Submission copy', 'SUBMISSION_COPY.md')]

out = ['# CONFLUX CORE — Complete Project Manual', '',
       'Generated from the maintained files in `conflux-core/` by `scripts/build_manual.py` (edit those, not this file).', '']
out += [f'{i}. {title} (`{name}`)' for i, (title, name) in enumerate(PARTS, start=1)]
for title, name in PARTS:
    body = (ROOT / name).read_text(encoding='utf-8')
    body = body.replace('](docs/', '](conflux-core/docs/').replace('](SUBMISSION', '](conflux-core/SUBMISSION')
    out += ['', '---', '', f'<!-- source: conflux-core/{name} -->', body]
target = ROOT.parent / 'CONFLUX_CORE_PROJECT_MANUAL.md'
target.write_text('\n'.join(out), encoding='utf-8')
print(f'{target} ({len(out)} blocks)')
