#!/usr/bin/env python3
"""Run supported campaigns and preserve immutable results with V16 receipts."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import time
import uuid

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hponas.persistence import atomic_json
from validation.evidence import (
    ROOT, AuditContextError, decision, digest, metadata, source_digest,
    require_audit_checkout,
)
from validation.v16_audit_enforcer import V16Enforcer
from validation.protocol_identity import canonical_id, protocol_path
from validation.tier1_contract import ENTRIES as TIER1


class ValidationRunner:
    def __init__(self, validation_id, artifact_root=None, *, run_name=None):
        require_audit_checkout()
        self.validation_id = canonical_id(validation_id)
        if self.validation_id == 'V15b':
            raise ValueError('V15b is not frozen; verified V15a PASS and separate integration allocation are required')
        self.protocol_path = protocol_path(self.validation_id)
        if self.validation_id in {*TIER1, 'V07', 'V08', 'V12', 'V15a'}:
            if self.validation_id == 'V07':
                from validation.dehb_finite import require_phase
                allocated = Path(require_phase()['run_path'])
            elif self.validation_id == 'V12':
                from validation.warm_finite_campaign import require_phase
                allocated = Path(require_phase()['run_path'])
            elif self.validation_id == 'V15a':
                from validation.ifbo_finite_campaign import require_phase
                allocated = Path(require_phase()['run_path'])
            elif self.validation_id == 'V08':
                from validation.population_campaign import require_phase
                allocated = Path(require_phase()['run_path'])
            else:
                from validation.tier1_campaign import require_phase
                allocated = Path(require_phase(self.validation_id)['run_path'])
            if run_name is not None and run_name != allocated.name:
                raise ValueError('Run name differs from frozen finite allocation')
            if artifact_root is not None and Path(artifact_root).resolve() != allocated.parent.parent:
                raise ValueError('Artifact root differs from frozen finite allocation')
            run_name = allocated.name
            artifact_root = allocated.parent.parent
        self.enforcer = V16Enforcer(self.protocol_path)
        self.parent = (
            Path(artifact_root or ROOT / "validation/artifacts") / self.validation_id
        )
        if run_name is not None and (not isinstance(run_name, str) or not run_name
                                     or Path(run_name).name != run_name or run_name in {".", ".."}):
            raise ValueError("Campaign run name must be a single directory name")
        self.run_dir = self.parent / (run_name or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            + "_"
            + uuid.uuid4().hex[:8]
        ))
        self.run_dir.mkdir(parents=True, exist_ok=False)

    def run(self, validation_fn):
        meta = metadata(self.validation_id)
        shutil.copyfile(self.protocol_path, self.run_dir / "protocol.md")
        started = time.monotonic()
        try:
            results = validation_fn()
            if source_digest() != meta["source_digest"]:
                raise ValueError("Source changed while the campaign was running")
            verdict = decision(self.validation_id, results)
        except Exception as exc:
            results = {
                "schema_version": 1,
                "validation_id": self.validation_id,
                "blocked_reason": f"{type(exc).__name__}: {exc}",
            }
            verdict = "BLOCKED"
        results.update(verdict=verdict, passed=verdict == "PASS")
        atomic_json(self.run_dir / "results.json", results)
        meta.update(
            results_sha256=digest(self.run_dir / "results.json"),
            duration_seconds=time.monotonic() - started,
        )
        atomic_json(self.run_dir / "metadata.json", meta)
        audit = self.enforcer.audit_execution(self.run_dir)
        atomic_json(self.run_dir / "v16_audit.json", audit.to_dict())
        atomic_json(self.parent / "latest.json", {"run": self.run_dir.name})
        print(
            f"{self.validation_id}: {verdict}; V16 audit {'PASS' if audit.passed else 'FAIL'}; {self.run_dir}"
        )
        return verdict == "PASS" and audit.passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "validation_id", type=canonical_id, choices=["V01", "V02", "V03", "V04-T0", "V05", "V07", "V08", "V12", "V14", 'V15a', *TIER1]
    )
    parser.add_argument("--run-mutations", action="store_true")
    parser.add_argument("--design", type=Path, help="Certified V04-T0/V05 design manifest")
    parser.add_argument("--phase", choices=["pilot", "confirmation", "replication"], default="confirmation")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Bounded real workload run; cannot certify performance",
    )
    args = parser.parse_args(argv)
    try:
        run_name = None
        if args.validation_id in {"V04-T0", "V05", 'V07', 'V08', 'V12', 'V15a', *TIER1} and (
            args.design or args.smoke or args.phase != "confirmation"
        ):
            raise ValueError("V04-T0/V05 v4 use the fixed stylized contract; legacy PPO design/phase/smoke arguments are retired")
        runner = ValidationRunner(args.validation_id, run_name=run_name)
    except (AuditContextError, ValueError, OSError) as exc:
        parser.exit(2, f"Campaign not started: {exc}\n")
    if args.validation_id == 'V07':
        from validation.dehb_finite import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id == 'V12':
        from validation.warm_finite_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id == 'V15a':
        from validation.ifbo_finite_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id == 'V08':
        from validation.population_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id in TIER1:
        from validation.tier1_campaign import campaign

        fn = lambda: campaign(args.validation_id, runner.run_dir)
    elif args.validation_id == "V03":
        from validation.v03_mutation_testing import campaign

        fn = lambda: campaign(run=args.run_mutations, artifact_dir=runner.run_dir)
    elif args.validation_id == "V01":
        from validation.v01_finite_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id == "V02":
        from validation.v02_final_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif args.validation_id == "V14":
        from validation.v14_day_one_walk import campaign

        fn = lambda: campaign(runner.run_dir, smoke=args.smoke)
    else:
        from validation.stylized_campaign import campaign

        fn = lambda: campaign(args.validation_id, runner.run_dir)
    return 0 if runner.run(fn) else 1


if __name__ == "__main__":
    raise SystemExit(main())
