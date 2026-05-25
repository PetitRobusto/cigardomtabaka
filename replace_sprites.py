#!/usr/bin/env python3
"""Replace all <use href="#hi-XXX"/> with full inline SVG. 
Run from project root: python3 replace_sprites.py"""

import re, os, glob

# Parse icons from sprite
with open("templates/_heroicons.html") as f:
    sprite = f.read()

icons = {}
for m in re.finditer(r'<symbol id="(hi-\S+?)".*?>(.*?)</symbol>', sprite, re.DOTALL):
    name = m.group(1)
    inner = m.group(2).strip()
    # Compact: remove newlines and extra spaces from SVG paths
    inner_compact = ' '.join(inner.split())
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="icon">{inner_compact}</svg>'
    icons[name] = svg

HTML_FILES = glob.glob("templates/**/*.html", recursive=True) + \
             glob.glob("**/templates/**/*.html", recursive=True)
HTML_FILES = [f for f in HTML_FILES if "_heroicons.html" not in f and ".superpowers" not in f]
HTML_FILES = list(set(HTML_FILES))

count = 0
for filepath in sorted(HTML_FILES):
    with open(filepath) as f:
        content = f.read()
    
    original = content
    for name, svg in icons.items():
        content = content.replace(f'<use href="#{name}"/>', svg)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✓ {filepath} ({content.count('<svg')} SVGs)")
        count += 1

print(f"\nUpdated {count} files")
