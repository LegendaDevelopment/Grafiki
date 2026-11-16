#!/usr/bin/env python3
"""Publish the verified public project without overwriting concurrent changes."""
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import urllib.request

REPO = 'LegendaDevelopment/Grafiki'
EXPECTED_MAIN = '4c595c2be6a9cd6e0b33abb8287d8a08f5208979'
CHECKSUM = '53825ccdeaef3b12f9f7341fd5d86a05c9ec4e22cf7fe6921273b0347c9b5284'
BLOBS = [
'873aa7de5d777080f70e3e1a37611c1be0b1b8c7',
'ef1e1bcfd545cb9acbae9f44f5acdc0edf44f830',
'49710f20fcd3765d2fd0c69a934eb473d4ffc93a',
'673ab11aacd684f0c2c0ec33056f3aa5a72a273d',
'e23eba442907b9a25536d2cf3c3beed1e0c2f5ae',
'23abb5e1355158809290f0c0887fe7c0fec8a49a',
'b79f3b9741a995c3d8251f3a77d4e2766cbdbf05',
'23da33cf4e57a2de734e267e90f061fb40925173',
'6af534766fdc04cefbc3a7e057a7226f79d2c560',
'56b3bb8b08611ed49f02e7f86f11fdf5dc481771',
'3c965c51c66cb8e6557a8514c90d3dbb446fc342',
'520f2f6da68eabec53b28fff5675557757d31b69',
'0d4ede84ce0c248f881764e87b69b82642e37f4c',
]

def git(*args, data=None, env=None):
    result = subprocess.run(['git', *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True, env=env)
    return result.stdout.decode('utf-8').strip()


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    git('fetch', 'origin', 'main')
    actual = git('rev-parse', 'origin/main')
    if actual != EXPECTED_MAIN:
        raise RuntimeError('Main changed since initial inspection; refusing to overwrite it')
    chunks = []
    for sha in BLOBS:
        request = urllib.request.Request(
            f'https://api.github.com/repos/{REPO}/git/blobs/{sha}',
            headers={'Accept': 'application/vnd.github+json',
                     'User-Agent': 'LEGENDA-PLANNER-verified-import'})
        with urllib.request.urlopen(request, timeout=30) as response:
            record = json.load(response)
        if record.get('sha') != sha or record.get('encoding') != 'base64':
            raise ValueError('Unexpected blob representation')
        content = base64.b64decode(record['content'])
        blob_hash = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        if blob_hash != sha:
            raise ValueError('Blob integrity failure')
        chunks.append(content)
    packed = b''.join(chunks)
    if len(packed) != 148384 or hashlib.sha256(packed).hexdigest() != CHECKSUM:
        raise ValueError('Transport checksum mismatch')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=256*1024*1024)
    raw = decoder.decompress(packed, max_length=677489)
    if len(raw) != 677488 or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid decompressed payload')
    snapshot = json.loads(raw)
    if snapshot.get('format') != 'legenda-planner-initial-import-v1' or len(snapshot['files']) != 31:
        raise ValueError('Invalid manifest')
    with tempfile.TemporaryDirectory(prefix='legenda-public-') as temporary:
        package = Path(temporary)
        verified = {}
        for name, record in snapshot['files'].items():
            path = PurePosixPath(name)
            if (path.is_absolute() or '\\' in name or name != path.as_posix()
                    or any(part in ('..', '.git', '.github', '.bootstrap') for part in path.parts)):
                raise ValueError('Unsafe path')
            if record['encoding'] == 'utf-8':
                content = record['content'].encode('utf-8')
            elif record['encoding'] == 'base64':
                content = base64.b64decode(record['content'], validate=True)
            else:
                raise ValueError('Unsupported content encoding')
            if hashlib.sha256(content).hexdigest() != record['sha256']:
                raise ValueError('File checksum mismatch: ' + name)
            verified[name] = content
        for name, content in verified.items():
            target = package / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        subprocess.run([sys.executable, 'scripts/build.py'], cwd=package, check=True)
        subprocess.run([sys.executable, 'scripts/check.py'], cwd=package, check=True)
        for name in ('index.html', 'dist/index.html', 'dist/LEGENDA_PLANNER.html'):
            content = (package / name).read_bytes()
            if len(content) != 561793:
                raise ValueError('Unexpected build output size')
            verified[name] = content
        git('config', 'user.name', 'github-actions[bot]')
        git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
        with tempfile.TemporaryDirectory(prefix='legenda-index-') as indexdir:
            environment = os.environ.copy()
            environment['GIT_INDEX_FILE'] = str(Path(indexdir) / 'index')
            git('read-tree', EXPECTED_MAIN, env=environment)
            for name, content in verified.items():
                blob = git('hash-object', '-w', '--stdin', data=content)
                git('update-index', '--add', '--cacheinfo', '100644', blob, name, env=environment)
            tree = git('write-tree', env=environment)
            commit = git('commit-tree', tree, '-p', EXPECTED_MAIN,
                         '-m', 'Add LEGENDA PLANNER application, documentation and validated development skill')
        git('push', 'origin', commit + ':refs/heads/main')
        print('Published verified project commit:', commit)
        print('Source files:', len(snapshot['files']), 'Generated application files: 3')
        print('Original source PDF excluded. All eight checks passed.')


if __name__ == '__main__':
    main()
