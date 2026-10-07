#!/usr/bin/env python3
"""Zip each skills/<name>/ folder for Claude skill upload (skill root at zip root)."""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")


def package_skill(name: str) -> str:
    src = os.path.join(SKILLS, name)
    if not os.path.isdir(src):
        raise SystemExit(f"missing skill directory: {src}")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{name}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(src):
            for fn in filenames:
                if fn.startswith(".") and fn != ".gitkeep":
                    continue
                path = os.path.join(dirpath, fn)
                arc = os.path.relpath(path, src)
                zf.write(path, arc)
    return out


def main():
    names = sorted(
        d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)) and not d.startswith(".")
    )
    if not names:
        raise SystemExit("no skills found")
    for name in names:
        path = package_skill(name)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
