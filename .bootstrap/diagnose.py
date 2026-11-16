#!/usr/bin/env python3
"""Inspect the already uploaded public transport; never write repository refs."""
import base64
import hashlib
import json
import lzma
from pathlib import Path
import runpy
import urllib.request

config = runpy.run_path('.bootstrap/publish.py', run_name='transport_definition')
out = Path('transport-diagnostics')
out.mkdir(exist_ok=True)
chunks = []
for i, sha in enumerate(config['BLOBS'], 1):
    request = urllib.request.Request(f'https://api.github.com/repos/{config["REPO"]}/git/blobs/{sha}', headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'legenda-import-diagnostic'})
    with urllib.request.urlopen(request, timeout=30) as response:
        record = json.load(response)
    content = base64.b64decode(record['content'])
    print('CHUNK', i, sha, 'bytes', len(content), 'prefix', content[:16].hex(), 'suffix', content[-16:].hex(), flush=True)
    (out / f'chunk-{i:02d}.bin').write_bytes(content)
    chunks.append(content)
packed = b''.join(chunks)
(out / 'transport.xz').write_bytes(packed)
print('PACKED', len(packed), hashlib.sha256(packed).hexdigest(), flush=True)
decoder = lzma.LZMADecompressor(memlimit=256*1024*1024)
raw = bytearray()
last_ok = 0
try:
    for pos in range(0, len(packed), 256):
        raw.extend(decoder.decompress(packed[pos:pos+256], max_length=8*1024*1024))
        last_ok = pos + 256
        if decoder.eof:
            print('END_OF_STREAM', pos, 'unused', len(decoder.unused_data), flush=True)
            break
except lzma.LZMAError as error:
    print('DECOMPRESSION_ERROR', str(error), 'compressed_offset', last_ok, 'decompressed', len(raw), flush=True)
(out / 'recovered-prefix.json').write_bytes(raw)
print('DECOMPRESSED', len(raw), hashlib.sha256(raw).hexdigest(), flush=True)
print('JSON_PREFIX', repr(bytes(raw[:400])), flush=True)
print('JSON_SUFFIX', repr(bytes(raw[-400:])), flush=True)
