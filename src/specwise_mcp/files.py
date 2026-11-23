"""Reading local files for tools that accept a path instead of the content.

A path is only read when, after resolving symlinks, it sits inside the root (the environment variable
SPECWISE_MCP_ROOT, or the current working directory when it is not set) and has an allowed extension.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

_REF = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/@^~{}-]{0,199}")
ROOT_ENV = "SPECWISE_MCP_ROOT"
ALLOWED_TEXT = "*.yaml, *.yml, *.json"


def root() -> Path:
    return Path(os.environ.get(ROOT_ENV) or Path.cwd()).expanduser().resolve()


def _allowed(name: str) -> bool:
    return name.lower().endswith((".yaml", ".yml", ".json"))


def resolve(path: str) -> Path:
    base = root()
    given = Path(path).expanduser()
    p = (given if given.is_absolute() else base / given).resolve()
    if not p.is_relative_to(base):
        raise ToolError(f"{path} is outside the allowed folder {base} (set {ROOT_ENV} to allow another one).")
    if not p.is_file():
        raise ToolError(f"No such file: {path} (relative paths start from {base}).")
    if not _allowed(p.name):
        raise ToolError(f"{p.name} is not an allowed file type: {ALLOWED_TEXT}.")
    return p


def read_text(path: str, max_bytes: int) -> str:
    p = resolve(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ToolError(f"{p} is {size:,} bytes; the limit is {max_bytes:,}.")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"{p} is not UTF-8 text.")

def git_show(path: str, ref: str) -> str:
    """The file as it is at `ref` (a branch, tag or commit) in the git repository that contains it."""
    if not _REF.fullmatch(ref) or ".." in ref:
        raise ToolError(f"{ref!r} is not a valid git ref: use a branch, tag or commit, not starting with '-'.")
    p = resolve(path)

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(p.parent), *args], check=False, capture_output=True, text=True)

    top = run("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise ToolError(f"{p} is not in a git repository.")
    rel = p.relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    shown = run("show", "--end-of-options", f"{ref}:{rel}")
    if shown.returncode != 0:
        raise ToolError(f"Could not read {rel} at {ref!r}: {shown.stderr.strip()[:200]}")
    return shown.stdout
