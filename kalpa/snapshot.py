from __future__ import annotations

import difflib
import hashlib
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import zstandard as zstd
except ImportError:
    zstd = None


def compute_hash(file_path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def compute_hash_from_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_raw_diff(original: bytes, modified: bytes) -> bytes:
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)

    ops: list = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ops.append(f"{tag}:{i1}:{i2}:{j1}:{j2}")

    result = "\n".join(ops).encode("utf-8") + b"\n==DATA==\n"
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            result += b"".join(modified_lines[j1:j2])

    return result


def apply_raw_diff(original: bytes, delta_bytes: bytes) -> bytes:
    parts = delta_bytes.split(b"\n==DATA==\n", 1)
    if len(parts) != 2:
        return original

    ops_str = parts[0].decode("utf-8")
    data = parts[1]

    original_lines = original.splitlines(keepends=True)
    result: list[bytes] = []
    data_offset = 0

    for line in ops_str.split("\n"):
        if not line.strip():
            continue
        parts_line = line.split(":")
        if len(parts_line) != 5:
            continue
        tag, i1_s, i2_s, j1_s, j2_s = parts_line
        i1, i2, j1, j2 = int(i1_s), int(i2_s), int(j1_s), int(j2_s)

        if tag == "equal":
            result.extend(original_lines[i1:i2])
        elif tag == "delete":
            pass
        elif tag in ("insert", "replace"):
            needed = j2 - j1
            for _ in range(needed):
                if data_offset >= len(data):
                    break
                nl = data.find(b"\n", data_offset)
                if nl == -1:
                    line_data = data[data_offset:]
                    data_offset = len(data)
                else:
                    line_data = data[data_offset : nl + 1]
                    data_offset = nl + 1
                result.append(line_data)

    return b"".join(result)


def compute_delta(
    old_content: bytes, new_content: bytes, algorithm: str = "zstd"
) -> Tuple[bytes, str]:
    diff_data = compute_raw_diff(old_content, new_content)
    if algorithm == "zstd" and zstd is not None:
        try:
            compressed = zstd.compress(diff_data)
            return compressed, "zstd"
        except Exception:
            return diff_data, "raw"
    return diff_data, "raw"


def apply_delta(
    original: bytes, delta_bytes: bytes, algorithm: str
) -> bytes:
    if algorithm == "zstd" and zstd is not None:
        try:
            decompressed = zstd.decompress(delta_bytes)
            return apply_raw_diff(original, decompressed)
        except (zstd.ZstdError, Exception):
            return original
    elif algorithm == "raw":
        return apply_raw_diff(original, delta_bytes)
    return original


class SnapshotEngine:
    def __init__(self, algorithm: str = "zstd", compression_level: int = 3):
        self.algorithm = algorithm
        self.compression_level = compression_level
        self._lock = threading.Lock()

    def hash_bytes(self, data: bytes) -> str:
        return compute_hash_from_bytes(data)

    def compute_file_hash(self, path: str) -> Optional[str]:
        return compute_hash(path)

    def create_delta(
        self, old_content: bytes, new_content: bytes
    ) -> Tuple[bytes, str]:
        return compute_delta(old_content, new_content, self.algorithm)

    def apply_delta(
        self, original: bytes, delta_bytes: bytes, algorithm: str
    ) -> bytes:
        return apply_delta(original, delta_bytes, algorithm)

    def build_file_manifest(self, folder_path: Path) -> Dict[str, str]:
        manifest: Dict[str, str] = {}
        folder_resolved = folder_path.resolve()
        kalpa_dir = (folder_resolved / ".kalpa").resolve()

        for root, dirs, files in os.walk(folder_resolved):
            root_path = Path(root).resolve()
            if root_path == kalpa_dir or kalpa_dir in root_path.parents:
                dirs.clear()
                continue

            for file in files:
                file_path = root_path / file
                if file_path == kalpa_dir or kalpa_dir in file_path.parents:
                    continue
                try:
                    rel_path = str(file_path.relative_to(folder_resolved))
                except ValueError:
                    continue
                file_hash = self.compute_file_hash(str(file_path))
                if file_hash:
                    manifest[rel_path] = file_hash

        return manifest
