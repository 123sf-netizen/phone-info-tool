"""SHA-256 sidecar checks for SQL backups; older backups may lack a sidecar."""
import hashlib
from pathlib import Path


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path):
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + '.sha256')
    if not sidecar.exists():
        return 'missing'
    expected = sidecar.read_text(encoding='ascii').strip()
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        return 'invalid'
    return 'ok' if digest_file(path) == expected else 'mismatch'
