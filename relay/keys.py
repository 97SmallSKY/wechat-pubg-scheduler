"""Issue and revoke API keys on the server."""

import argparse
import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")


def digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("action", choices=("issue", "revoke"))
    parser.add_argument("name")
    parser.add_argument("groups", nargs="*")
    args = parser.parse_args()
    if any(not IDENTIFIER.fullmatch(value) for value in [args.name] + args.groups):
        parser.error("Name and group IDs use lowercase letters, numbers and hyphens")
    entries = json.loads(args.path.read_text(encoding="utf-8")) if args.path.exists() else {}
    token = None
    if args.action == "issue":
        token = secrets.token_urlsafe(32)
        entries[args.name] = {"digest": digest(token), "groups": sorted(set(args.groups))}
    else:
        entries.pop(args.name, None)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(args.path.parent),
                                     prefix=".keys-", delete=False) as output:
        json.dump(entries, output)
    os.replace(output.name, str(args.path))
    if token:
        print(token)


if __name__ == "__main__":
    main()
