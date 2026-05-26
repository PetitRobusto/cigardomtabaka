"""Django template tag: dynamically resolve Vite asset hashes from manifest."""
from django import template
from django.conf import settings
from django.templatetags.static import static
from pathlib import Path
import json, os

register = template.Library()

@register.simple_tag
def vite_asset(entry_name):
    """Read .vite/manifest.json and return static URL for the built asset."""
    manifest_path = Path(settings.BASE_DIR) / 'static' / 'price-tracker' / '.vite' / 'manifest.json'
    if not manifest_path.exists():
        # Fallback: try frontend dist
        manifest_path = Path(settings.BASE_DIR) / 'frontend' / 'dist' / '.vite' / 'manifest.json'
    
    if not manifest_path.exists():
        return ''

    with open(manifest_path) as f:
        manifest = json.load(f)

    entry = manifest.get(entry_name, {})
    if not entry:
        return ''

    if entry_name.endswith('.html'):
        # Return JS + CSS links for HTML entry
        js_file = entry.get('file', '')
        css_files = entry.get('css', [])
        out = ''
        if js_file:
            out += f'<script type="module" crossorigin src="{static("price-tracker/assets/" + js_file)}"></script>'
        for css_file in css_files:
            out += f'\n    <link rel="stylesheet" crossorigin href="{static("price-tracker/assets/" + css_file)}">'
        return out

    return static(f'price-tracker/assets/{entry["file"]}')
