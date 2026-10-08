#!/usr/bin/env python3
"""Fail if the tree looks like it contains client PII or non-template config."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", ".venv", "node_modules"}
SKIP_FILES = {"check_public_safety.py", "test_public_safety.py"}

# SHA-256 of lowercase forbidden tokens/phrases (never store plaintext in repo).
TOKEN_DENY = {
    "910be7b5be5ae465d80123808b1f9d533e5e8e9ca85a40781213f74bde34798c",
    "3a521aed687a013373ca909e49ca2be360e4606037934f870ea3fee8c1a35970",
    "fd36d80fe16f0daad18e6cecdef36628667562afc9599540b005c7cb3310f838",
    "e8136cb5b8addf9d4f0ba4e492fad7f187e100e1b535c362150f658eb2fbd7fa",
    "f7f376a1fcd0d0e11a10ed1b6577c99784d3a6bbe669b1d13fae43eb64634f6e",
    "7e4a00ca807c4106dfb2756c9f88fe53f62f4b93fe5f00ad90441cad8463b214",
    "13a551bd8d116b90e0c302f4537c2b2698b5e6b2204f877e00378e1476824e19",
    "04659112470a156ae0efc01d12ae97d21faf9ade8860a6721fe7476f633bed0b",
    "553a61ed0c7a4c5761f1c6db7d113f05db7fedaf3bbbe0651ecdd7e09b377ed9",
    "3c60b64f7abf686c9c00608ef0722101fe6761e63cf992920dfdcacb01059927",
    "2f316dd5c0d2a28b9f7e30bf36ebd3a2049499ba60b6307885ac0a00fe6d86c4",
    "7200ba2827444d683cb383358e00df51cd4d54113f272aa3899ae6bc18f44052",
    "f7f63a9261fa1014b68d011d0e56685c112e99050705bf6c75c782029ba4cd07",
    "3f1558ad7200113cb9ce92b429a9e76ba66a6eba65c4890fc5c3d5271770a52e",
    "f943de12f111c893a8250b62893ee23f00fd9012aacd45eb80e61b20af29ede5",
    "3e7a475906d086ec84a3a8a5600b210c97a052f2f2a2d351022690cc84f3903f",
    "edb6be9701cb61d0ebd929d22145b40c7513fcba7f0fae94f67c0cb3467b8a48",
    "d334cbac4bb3f242dfe5e11a656333345ce05c8409bc347be201f2447e14b480",
    "b58d19b912901f0db015f7a76dc78458a2e0ce8da951bdc803156d8011787bca",
    "76279b1913fd38dd2c276ae57060e6b38cc1dbce9d92908d7268543486565878",
    "bd58e5612a63b7b5c777e0b21c0573468da4910ce7645e4c373fc31b21758e5d",
}

PHRASE_DENY = {
    "7e4a00ca807c4106dfb2756c9f88fe53f62f4b93fe5f00ad90441cad8463b214",
    "13a551bd8d116b90e0c302f4537c2b2698b5e6b2204f877e00378e1476824e19",
    "b58d19b912901f0db015f7a76dc78458a2e0ce8da951bdc803156d8011787bca",
    "2f316dd5c0d2a28b9f7e30bf36ebd3a2049499ba60b6307885ac0a00fe6d86c4",
    "3c60b64f7abf686c9c00608ef0722101fe6761e63cf992920dfdcacb01059927",
    "edb6be9701cb61d0ebd929d22145b40c7513fcba7f0fae94f67c0cb3467b8a48",
    "f7f63a9261fa1014b68d011d0e56685c112e99050705bf6c75c782029ba4cd07",
    "76279b1913fd38dd2c276ae57060e6b38cc1dbce9d92908d7268543486565878",
    "bd58e5612a63b7b5c777e0b21c0573468da4910ce7645e4c373fc31b21758e5d",
    "e8136cb5b8addf9d4f0ba4e492fad7f187e100e1b535c362150f658eb2fbd7fa",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
PHONE_RE = re.compile(r"(?<!\d)(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
PMID_RE = re.compile(r'\bpmid\b["\']?\s*[:=#]?\s*["\']?(\d{3,})', re.IGNORECASE)
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org"}
ALLOWED_PHONE_PREFIX = re.compile(r"^\+?1?[\s.-]?555-01\d{2}[\s.-]?\d{4}$")

PLACEHOLDER_OK = re.compile(
    r"^(<[^>]+>|\[CONFIRM[^\]]*\]|REPLACE-ME|n/a|null|)$|^\s*$",
    re.I,
)


def h(text: str) -> str:
    return hashlib.sha256(text.lower().encode()).hexdigest()


def iter_files(base: str):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, base)
            if rel.startswith("tests/fixtures/bad/"):
                continue
            yield path


def check_denylist(text: str, path: str, errors: list[str]):
    words = re.findall(r"[a-z0-9]+", text.lower())
    for w in words:
        if h(w) in TOKEN_DENY:
            errors.append(f"{path}: denylisted token hash match")
            return
    for n in (2, 3, 4):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n])
            if h(phrase) in PHRASE_DENY:
                errors.append(f"{path}: denylisted phrase hash match")
                return


def check_email_phone(text: str, path: str, errors: list[str]):
    for m in EMAIL_RE.finditer(text):
        domain = m.group(1).lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            errors.append(f"{path}: email outside example.com/org ({m.group(0)})")
    for m in PHONE_RE.finditer(text):
        raw = re.sub(r"\s", " ", m.group(0).strip())
        compact = re.sub(r"[^\d+]", "-", raw)
        if not ALLOWED_PHONE_PREFIX.match(compact.replace("--", "-")):
            if "555-01" not in raw:
                errors.append(f"{path}: phone outside 555-01xx ({m.group(0)})")


def check_pmid(text: str, path: str, errors: list[str]):
    for m in PMID_RE.finditer(text):
        if m.group(1) != "999999":
            errors.append(f"{path}: pmid {m.group(1)} (expected 999999 in repo)")


def check_client_config(path: str, errors: list[str]):
    if not path.endswith("client-config.json"):
        return
    try:
        cfg = json.load(open(path))
    except json.JSONDecodeError as ex:
        errors.append(f"{path}: invalid JSON ({ex})")
        return

    if "skills/" not in path.replace("\\", "/"):
        return

    def walk(node, p=""):
        if isinstance(node, dict):
            for key, val in node.items():
                walk(val, f"{p}.{key}" if p else key)
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{p}[{i}]")
        elif isinstance(node, str):
            leaf = p.split(".")[-1]
            if leaf == "report_salt" and node:
                errors.append(f"{path}: report_salt must be empty in packaged template")
            elif leaf in ("phone", "reply_to", "website", "logo_url", "pmcom_profile_url", "name", "short_name", "from_name"):
                if node and not node.startswith("<") and "example." not in node.lower() and "REPLACE-ME" not in node and "[CONFIRM" not in node:
                    errors.append(f"{path}: non-placeholder string at {p}: {node[:60]}")
            elif leaf in ("full_name", "ops_lead", "comms_lead", "owner", "first_name") and node:
                if not node.startswith("<") and "[CONFIRM" not in node:
                    errors.append(f"{path}: non-placeholder team string at {p}")

    walk(cfg)


def scan_tree(base: str) -> list[str]:
    errors: list[str] = []
    for path in iter_files(base):
        try:
            if path.endswith((".png", ".jpg", ".jpeg", ".gif", ".zip", ".woff", ".woff2")):
                continue
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        check_denylist(text, path, errors)
        check_email_phone(text, path, errors)
        check_pmid(text, path, errors)
        check_client_config(path, errors)
    return errors


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else ROOT
    base = os.path.abspath(base)
    errors = scan_tree(base)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"public-safety check failed ({len(errors)} issue(s))", file=sys.stderr)
        return 1
    print(f"public-safety check passed for {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
