"""Package and install the frontend built by the exact successful CI commit."""

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory


def validate_build(root):
    manifest = json.loads((root / '.vite/manifest.json').read_text())
    if not manifest or not any(chunk.get('isEntry') for chunk in manifest.values()):
        raise ValueError('Frontend manifest has no entry point')
    for chunk in manifest.values():
        for name in [chunk['file'], *chunk.get('css', []), *chunk.get('assets', [])]:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or not (root / name).is_file():
                raise ValueError(f'Missing or invalid frontend asset: {name}')
    if (root / '__seo_private__').exists():
        validate_seo(root / '__seo_private__')


def validate_seo(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('schemaVersion') != 1 or not manifest.get('pages'):
        raise ValueError('Missing public page manifest')
    for entry in manifest['pages'].values():
        if not re.fullmatch(r'[a-f0-9]{64}\.html', entry['file']):
            raise ValueError('Invalid private HTML path')
        if hashlib.sha256((root / entry['file']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Public page checksum mismatch')


def validate_sha(sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected a full commit SHA')


def pack(source, output, sha, seo_source=None):
    validate_sha(sha)
    validate_build(source)
    if (source / '__seo_private__').exists():
        raise ValueError('Private pages must be provided outside the public asset directory')
    if seo_source is not None:
        if seo_source.resolve().is_relative_to(source.resolve()):
            raise ValueError('Private HTML must be outside public static assets')
        validate_seo(seo_source)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'frontend.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        bundle.add(source, arcname='.')
        if seo_source is not None:
            bundle.add(seo_source, arcname='__seo_private__')
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


def install(artifact, sha, destination, seo_destination=None):
    # Stage on the same filesystem so replacement and rollback use renames.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        directory = stack.enter_context(TemporaryDirectory(prefix='.frontend-install-', dir=destination.parent))
        staging = Path(directory)
        release = staging / 'release'
        release.mkdir()
        extract_verified(artifact, sha, release)
        replacements = [(release, destination, staging / 'previous')]
        private = release / '__seo_private__'
        if private.exists():
            if seo_destination is None or seo_destination.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Provide a private SEO destination outside public static assets')
            seo_destination.parent.mkdir(parents=True, exist_ok=True)
            seo_staging = Path(stack.enter_context(TemporaryDirectory(prefix='.seo-install-', dir=seo_destination.parent)))
            seo_release = seo_staging / 'seo-release'
            shutil.copytree(private, seo_release)
            shutil.rmtree(private)
            replacements.append((seo_release, seo_destination, seo_staging / 'previous'))
        elif seo_destination is not None:
            raise ValueError('Verified artifact is missing private public-page HTML')
        for _, target, _ in replacements:
            if target.is_symlink():
                raise ValueError('Frontend destination must not be a symlink')
        saved, installed = [], []
        try:
            for staged, target, previous in replacements:
                if target.exists():
                    target.rename(previous)
                    saved.append((previous, target))
                staged.rename(target)
                installed.append(target)
        except OSError:
            for target in reversed(installed):
                shutil.rmtree(target)
            for previous, target in reversed(saved):
                previous.rename(target)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    package = commands.add_parser('pack')
    package.add_argument('source', type=Path)
    package.add_argument('output', type=Path)
    package.add_argument('sha')
    package.add_argument('--seo-source', type=Path)
    for name in ('verify', 'install'):
        command = commands.add_parser(name)
        command.add_argument('artifact', type=Path)
        command.add_argument('sha')
        if name == 'install':
            command.add_argument('destination', type=Path)
            command.add_argument('--seo-destination', type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    {'pack': pack, 'verify': verify, 'install': install}[command](**args)


if __name__ == '__main__':
    main()
