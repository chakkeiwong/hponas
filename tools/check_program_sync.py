#!/usr/bin/env python3
"""Check the current master, scope dispositions, work and evidence bindings.

Exit 0 means consistent, not certified. A truthful BLOCKED program is valid.
Use tools.gate_check for full campaign decision recomputation.
"""
from pathlib import Path
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.program_state import check


def main():
    errors, view = check()
    if errors:
        print("Program drift detected:")
        for error in errors:
            print(f"  - {error}")
        return 1
    data = view["program"]
    print(f"Program consistent: {len(data['requirements'])} requirements, "
          f"{len(data['work_items'])} work items, {len(data['protocol_bindings'])} exact protocol bindings.")
    stale = [c["id"] for c in view["campaigns"] if not c["fresh"]]
    print(f"Release status: {view['phase']['status']}. Stale current-source receipts: "
          + (", ".join(stale) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
