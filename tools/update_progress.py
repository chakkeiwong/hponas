#!/usr/bin/env python3
"""Generate master status, progress and traceability from the work register."""
import argparse
from pathlib import Path
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.program_state import ROOT, check, generated_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    errors, view = check(verify_generated=args.verify)
    if errors:
        print("\n".join(errors))
        return 1
    if args.verify:
        print("All generated program views match current inputs.")
        return 0
    for name, content in generated_documents(ROOT, view).items():
        path = ROOT / name
        temporary = path.with_suffix(path.suffix + ".program-tmp")
        temporary.write_text(content)
        temporary.replace(path)
        print(f"Generated {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
