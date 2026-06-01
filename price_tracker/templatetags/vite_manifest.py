"""
Vite 静态文件 manifest 读取器

用法:
  {% load vite_manifest %}
  {% vite_asset 'index.html' %}
  → 自动输出 <script> + <link> 标签
"""
import json
import os
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()

MANIFEST_CACHE = {}
MANIFEST_MTIME = 0


def _load_manifest():
    """加载 Vite manifest.json（带文件时间戳缓存）"""
    global MANIFEST_CACHE, MANIFEST_MTIME

    manifest_path = os.path.join(
        settings.BASE_DIR, 'static', 'frontend', '.vite', 'manifest.json'
    )
    try:
        mtime = os.path.getmtime(manifest_path)
    except OSError:
        return {}

    if mtime != MANIFEST_MTIME:
        with open(manifest_path) as f:
            MANIFEST_CACHE = json.load(f)
        MANIFEST_MTIME = mtime

    return MANIFEST_CACHE


@register.simple_tag
def vite_asset(entry: str):
    """
    从 Vite manifest 获取入口文件，输出完整 <script> + <link> 标签。

    用法: {% vite_asset 'index.html' %}
    """
    manifest = _load_manifest()
    chunk = manifest.get(entry, {})
    js_file = chunk.get('file', '')
    css_files = chunk.get('css', [])

    out = ''
    if js_file:
        out += f'<script type="module" crossorigin src="{static("frontend/" + js_file)}"></script>'
    for css_file in css_files:
        out += f'\n<link rel="stylesheet" crossorigin href="{static("frontend/" + css_file)}">'
    return mark_safe(out)


@register.simple_tag
def vite_css(entry: str):
    """
    从 Vite manifest 获取入口 CSS 文件路径。

    用法: {% vite_css 'index.html' %}
    """
    manifest = _load_manifest()
    chunk = manifest.get(entry, {})
    css_files = chunk.get('css', [])
    if css_files:
        return static(f'frontend/{css_files[0]}')
    return ''
