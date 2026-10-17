"""Bounded PPO integration example with separate protected checkpoint evaluation.

This example works with the installed library and retains its artifacts. It does
not produce an audited V14 campaign or certify Tier 0. Audited campaigns require
the full checkout and ``python -m validation.run_validation_with_audit V14``.
"""

import argparse
import json
from pathlib import Path
import tempfile

from validation.v14_day_one_walk import campaign


def run_day_one_walk(output_dir=None):
    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="hponas-ppo-example-", dir=output_dir))
    result = campaign(directory)
    result.update(kind="integration_example", scientific_acceptance=False)
    path = directory / "example-result.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PPO integration example completed; {len(result['trials'])} training trial(s).")
    print(f"Protected seed evaluated after search observations; artifacts={directory}")
    print("This demonstration does not certify V14 or Tier 0.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    run_day_one_walk(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
