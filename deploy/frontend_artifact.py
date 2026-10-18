"""Package and install the frontend built by the exact successful CI commit."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
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
