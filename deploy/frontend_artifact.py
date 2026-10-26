"""Package and install the frontend built by the exact successful CI commit."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory


# Referenced directly by the SSR document and shared store components, so Vite's
# hashed-asset manifest does not enumerate these required public files.
STOREFRONT_PUBLIC_ASSETS = (
    'startup-loader.js', 'favicon-96.png', 'logo-opening.webp',
    'logo-motion.webp', 'logo-opening-motion-v2.svg',
)
ERROR_PAGE_LOCALES = {
    'errors/404-zh.html': {'zh', 'zh-cn', 'zh-hans'},
    'errors/404-ru.html': {'ru', 'ru-ru'},
    'errors/404-en.html': {'en', 'en-us'},
}


class _ErrorPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_language = None
        self.has_html_end = False
        self.has_doctype = False
        self.has_robots_noindex = False
        self.has_canonical_or_hreflang = False

    def handle_decl(self, decl):
        self.has_doctype |= decl.lower().strip() == 'doctype html'

    def handle_starttag(self, tag, attrs):
        attributes = {key.lower(): (value or '') for key, value in attrs}
        if tag.lower() == 'html':
            self.html_language = attributes.get('lang', '').lower()
        elif tag.lower() == 'meta' and attributes.get('name', '').lower() == 'robots':
            self.has_robots_noindex |= 'noindex' in attributes.get('content', '').lower()
        elif tag.lower() == 'link':
            relationships = attributes.get('rel', '').lower().split()
            self.has_canonical_or_hreflang |= (
                'canonical' in relationships or 'hreflang' in attributes
            )

    def handle_endtag(self, tag):
        if tag.lower() == 'html':
            self.has_html_end = True


def validate_build(root):
    for name, allowed_languages in ERROR_PAGE_LOCALES.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f'Missing frontend 404 page: {name}')
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError as error:
            raise ValueError(f'Invalid UTF-8 frontend 404 page: {name}') from error
        if not content.strip():
            raise ValueError(f'Empty frontend 404 page: {name}')
        parser = _ErrorPageParser()
        try:
            parser.feed(content)
            parser.close()
        except Exception as error:
            raise ValueError(f'Invalid frontend 404 document: {name}') from error
        if (not parser.has_doctype or not parser.has_html_end
                or parser.html_language not in allowed_languages):
            raise ValueError(f'Invalid frontend 404 document or locale: {name}')
        if not parser.has_robots_noindex or parser.has_canonical_or_hreflang:
            raise ValueError(f'Frontend 404 page has unsafe SEO metadata: {name}')

    manifest = json.loads((root / '.vite/manifest.json').read_text())
    if not manifest or not any(chunk.get('isEntry') for chunk in manifest.values()):
        raise ValueError('Frontend manifest has no entry point')
    if 'src/storefront/client.tsx' in manifest:
        if not (root / 'storefront-render/render.mjs').is_file():
            raise ValueError('Frontend artifact is missing the storefront renderer')
        for name in STOREFRONT_PUBLIC_ASSETS:
            if not (root / name).is_file():
                raise ValueError(f'Missing storefront public asset: {name}')
    for chunk in manifest.values():
        for name in [chunk['file'], *chunk.get('css', []), *chunk.get('assets', [])]:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or not (root / name).is_file():
                raise ValueError(f'Missing or invalid frontend asset: {name}')


def validate_sha(sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected a full commit SHA')


def pack(source, output, sha):
    validate_sha(sha)
    validate_build(source)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'frontend.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        bundle.add(source, arcname='.')
    (output / 'metadata.json').write_text(json.dumps({
        'commit': sha,
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    }) + '\n')


def extract_verified(artifact, sha, target):
    validate_sha(sha)
    metadata = json.loads((artifact / 'metadata.json').read_text())
    archive = artifact / 'frontend.tar.gz'
    if metadata['commit'] != sha:
        raise ValueError('Frontend artifact commit does not match verified CI commit')
    if metadata['sha256'] != hashlib.sha256(archive.read_bytes()).hexdigest():
        raise ValueError('Frontend artifact checksum mismatch')
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError(f'Unsafe frontend archive member: {member.name}')
        bundle.extractall(target, filter='data')
    validate_build(target)


def verify(artifact, sha):
    with TemporaryDirectory(prefix='frontend-verify-') as directory:
        extract_verified(artifact, sha, Path(directory))


def install(artifact, sha, destination):
    # Stage on the same filesystem so replacement and rollback use renames.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.frontend-install-', dir=destination.parent) as directory:
        staging = Path(directory)
        release = staging / 'release'
        release.mkdir()
        extract_verified(artifact, sha, release)
        previous = staging / 'previous'
        if destination.is_symlink():
            raise ValueError('Frontend destination must not be a symlink')
        # Cached HTML still references immutable chunks from the previous build.
        # Retain only hashed static assets, never old entry points or renderers.
        old_assets = destination / 'assets'
        if old_assets.is_dir() and not old_assets.is_symlink():
            for source in old_assets.rglob('*'):
                if source.is_symlink() or not source.is_file():
                    continue
                if not re.search(r'-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$', source.name):
                    continue
                if any(parent.is_symlink() for parent in source.parents if parent != destination.parent):
                    continue
                target = release / 'assets' / source.relative_to(old_assets)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        if destination.exists():
            destination.rename(previous)
        try:
            release.rename(destination)
        except OSError:
            if previous.exists():
                previous.rename(destination)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    package = commands.add_parser('pack')
    package.add_argument('source', type=Path)
    package.add_argument('output', type=Path)
    package.add_argument('sha')
    for name in ('verify', 'install'):
        command = commands.add_parser(name)
        command.add_argument('artifact', type=Path)
        command.add_argument('sha')
        if name == 'install':
            command.add_argument('destination', type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    {'pack': pack, 'verify': verify, 'install': install}[command](**args)


if __name__ == '__main__':
    main()
