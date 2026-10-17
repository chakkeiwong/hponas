"""Prospective raw-process reconstruction; never trust a tool status alone."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RAW_OUTCOME_POLICY = "mutmut_3_8_forkserver_process_outcomes_v1"

# Exact labels emitted by the pinned tool, retained as a separate observation.
TOOL_STATUS = {
    1: "killed", 3: "killed", 0: "survived", 5: "no tests",
    2: "check was interrupted by user", None: "not checked", 33: "no tests",
    34: "skipped", 35: "suspicious", 36: "timeout", 37: "caught by type check",
    -24: "timeout", 24: "timeout", 152: "timeout", 255: "timeout",
    -11: "segfault", -9: "segfault",
}

# Only an ordinary failed test is a kill. The configured forkserver reports an
# actual SIGXCPU limit as -24. Other timeout-like labels are not evidence of it.
VERIFIED_STATUS = {
    0: "survived", 1: "killed", 2: "check was interrupted by user",
    5: "no tests", None: "not checked", 33: "no tests", 34: "skipped",
    35: "suspicious", 37: "caught by type check", -24: "timeout",
    -11: "segfault", -9: "segfault",
}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate raw mutation metadata key")
        result[key] = value
    return result


def read_raw_metadata(binding):
    path = Path(binding["path"])
    if not path.is_absolute():
        raise ValueError("Raw mutation metadata path must be absolute")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("Changed raw mutation metadata")
    record = json.loads(data, object_pairs_hook=_unique_pairs)
    rows = record.get("exit_code_by_key") if isinstance(record, dict) else None
    if not isinstance(rows, dict):
        raise ValueError("Missing raw mutation exit-code population")
    return rows


def reconstruct_raw_outcomes(listed, metadata, required_modules):
    """Reconcile complete pinned-tool labels with bound individual exit codes.

    Missing records and unknown outcomes cannot become timeout exclusions. The
    returned population preserves listing order and explicitly retains both the
    original tool label and raw code for independent downstream verification.
    """
    required = set(required_modules)
    modules, raw, paths = set(), {}, set()
    for entry in metadata:
        module, binding = entry["module"], entry["binding"]
        if module not in required or module in modules or binding["path"] in paths:
            raise ValueError("Unexpected or duplicate raw mutation module")
        modules.add(module)
        paths.add(binding["path"])
        for mid, code in read_raw_metadata(binding).items():
            prefix, separator, number = mid.rpartition("__mutmut_")
            if (not separator or not number.isdecimal() or int(number) < 1
                    or prefix.rsplit(".", 1)[0] != module or mid in raw):
                raise ValueError("Raw mutant identity/module mismatch")
            if code is not None and type(code) is not int:
                raise ValueError("Raw mutant exit code must be an integer or null")
            raw[mid] = code
    if modules != required:
        raise ValueError("Missing raw mutation modules")
    if len(listed) != len({row["id"] for row in listed}):
        raise ValueError("Duplicate listed mutant")
    if set(raw) != {row["id"] for row in listed}:
        raise ValueError("Raw mutation population differs from complete listing")
    reconstructed = []
    for row in listed:
        mid = row["id"]
        code = raw[mid]
        tool_status = TOOL_STATUS.get(code, "suspicious")
        if row["status"] != tool_status or row["module"] != mid.rsplit(".", 1)[0]:
            raise ValueError("Raw process outcome disagrees with pinned-tool listing")
        reconstructed.append({"id": mid, "module": row["module"],
                              "status": VERIFIED_STATUS.get(code, "suspicious"),
                              "tool_status": tool_status, "raw_exit_code": code})
    return reconstructed
