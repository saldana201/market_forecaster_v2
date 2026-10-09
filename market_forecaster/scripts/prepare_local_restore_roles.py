"""Prepare a Supabase roles dump for a disposable local restore drill.

The hosted Supabase roles dump can include platform-owned ALTER ROLE ... SET
statements that a local Supabase restore connection cannot change. The encrypted
backup remains untouched; this module writes a derived local-only roles file.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


_ROLE_SETTING = re.compile(r"(?ims)^\s*ALTER\s+ROLE\b.*?\bSET\b.*?;\s*")


def prepare_local_roles(source: Path, target: Path) -> int:
    sql = source.read_text(encoding="utf-8")
    matches = _ROLE_SETTING.findall(sql)
    filtered = _ROLE_SETTING.sub(
        "-- skipped in disposable local restore: "
        "Supabase local owns server-level role settings\n",
        sql,
    )

    if _ROLE_SETTING.search(filtered):
        raise RuntimeError(
            "Server-level ALTER ROLE ... SET statement remained after local filtering."
        )

    if re.search(r"(?i)\blog_min_messages\b", filtered):
        raise RuntimeError(
            "log_min_messages remained in the local roles file after filtering."
        )

    target.write_text(filtered, encoding="utf-8")
    return len(matches)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()

    skipped = prepare_local_roles(args.source, args.target)
    print(
        "Prepared local roles file; skipped "
        f"{skipped} server-level role setting statements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
