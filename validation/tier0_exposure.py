"""Reconstruct the declared local exposure scan, without attesting non-exposure.

The producer is intentionally separate. Git objects, current file bytes and
pinned Python/XML sources are the observations; summary/approval fields have
no evidential force. The current-file portion is a freshness check, so a
historical snapshot must not be relabelled current after source changes.
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from validation.tier0_objectivity import read_bound_json


LIMITS = [
    "Only locally reachable Git refs and the declared current text scope are covered.",
    "Literal alias absence does not establish unrestricted absence of exposure.",
    "Shared XML elements do not decide capability-specific lineage eligibility.",
    "Local files, hashes and Git dates cannot authenticate external chronology or seed secrecy.",
]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def _local(root, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Invalid local exposure path")
    candidate = root / path
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
        raise ValueError("Exposure source symlink or path escape")
    return candidate


def _lineage(root, lineage, names):
    sources = lineage.get("sources", [])
    if [row.get("environment") for row in sources] != names:
        raise ValueError("Incomplete or duplicate lineage source inventory")
    signatures = {}
    for row in sources:
        if row.get("status") == "missing_pinned_source":
            # An absent source cannot establish lineage; no signature invented.
            continue
        path = _local(root, row["path"])
        raw = path.read_bytes()
        if _sha(raw) != row["sha256"]:
            raise ValueError("Changed lineage source")
        nodes = list(ast.walk(ast.parse(raw)))
        imports = sorted({node.module for node in nodes if isinstance(node, ast.ImportFrom) and node.module})
        bases = [ast.unparse(base) for node in nodes if isinstance(node, ast.ClassDef) for base in node.bases]
        assets = sorted({node.value for node in nodes if isinstance(node, ast.Constant)
                         and isinstance(node.value, str) and node.value.endswith(".xml") and "assets/" in node.value})
        expected, signature = [], Counter()
        for name in assets:
            asset_path = path.parent / name
            if not asset_path.is_file():
                expected.append({"path": name, "status": "not_in_pinned_source_package"})
                continue
            asset_path = _local(root, str(asset_path.relative_to(root)))
            body = asset_path.read_bytes()
            xml = ET.fromstring(body)
            signature.update((element.tag, tuple(sorted(element.attrib.items()))) for element in xml.iter())
            expected.append({"path": str(asset_path.relative_to(root)), "sha256": _sha(body),
                             "elements": sum(1 for _ in xml.iter()),
                             "body_names": sorted({e.attrib["name"] for e in xml.iter("body") if "name" in e.attrib}),
                             "joint_names": sorted({e.attrib["name"] for e in xml.iter("joint") if "name" in e.attrib})})
        if row["imports"] != imports or row["class_bases"] != bases or row["assets"] != expected:
            raise ValueError("Lineage syntax or asset reconstruction differs")
        signatures[row["environment"]] = signature
    for pair in lineage["related_pairs"]:
        if pair["candidate"] not in signatures or pair["previously_exposed"] not in signatures:
            raise ValueError("Lineage pair lacks source evidence")
        a, b = signatures[pair["candidate"]], signatures[pair["previously_exposed"]]
        actual = (sum(a.values()), sum(b.values()), sum((a & b).values()))
        declared = tuple(pair[k] for k in ("candidate_xml_elements", "prior_xml_elements", "exact_shared_element_occurrences"))
        if actual != declared:
            raise ValueError("Lineage shared-element counts differ")


def verify_local_exposure(root, scope_ref, review_ref):
    """Check the exact producer scope against live local raw inputs.

    The caller must bind the intended scope as well as the report. A narrower
    scope is a different question; no choice of scope establishes global
    non-exposure. Neither status labels nor an external signer's name matters.
    """
    root = Path(root).resolve()
    scope, review = read_bound_json(root, scope_ref), read_bound_json(root, review_ref)
    if scope.get("kind") != "scoped_exposure_coverage_plan" or review.get("kind") != "local_exposure_history_and_lineage_review":
        raise ValueError("Unknown local exposure evidence contract")
    names = scope["names"]
    if not names or len(set(names)) != len(names) or set(scope["patterns"]) != set(names):
        raise ValueError("Incomplete exposure alias scope")
    documents = {}
    for ref in review["files"]:
        name = Path(ref["path"]).name
        if name in documents:
            raise ValueError("Duplicate exposure evidence document")
        documents[name] = read_bound_json(root, ref)
    if set(documents) != {"history.json", "current.json", "lineage.json"}:
        raise ValueError("Incomplete exposure evidence documents")
    history, current, lineage = (documents[name] for name in ("history.json", "current.json", "lineage.json"))
    refs = _git(root, "show-ref", "--head")
    if refs.decode().splitlines() != history["refs"] or _sha(refs) != history["refs_sha256"]:
        raise ValueError("Local Git refs differ from declared snapshot")
    commits = sorted(_git(root, "rev-list", "--all", "HEAD").decode().splitlines())
    if [row["commit"] for row in history["commits"]] != commits:
        raise ValueError("Reachable commit coverage incomplete or duplicated")
    selected = lambda path: path.endswith(tuple(scope["history_suffixes"])) and not path.startswith(tuple(scope["history_exclusions"]))
    patterns = {name: re.compile(pattern, re.I) for name, pattern in scope["patterns"].items()}

    def matches(raw):
        lines = raw.decode("utf-8", errors="replace").splitlines()
        found = {name: [i for i, line in enumerate(lines, 1) if pattern.search(line)] for name, pattern in patterns.items()}
        return {name: indices for name, indices in found.items() if indices}

    used, exclusions = defaultdict(set), Counter()
    for row in history["commits"]:
        raw = _git(root, "ls-tree", "-rz", "--full-tree", row["commit"])
        if _sha(raw) != row["tree_listing_sha256"]:
            raise ValueError("Git tree listing differs")
        entries = []
        for item in raw.split(b"\0"):
            if not item:
                continue
            header, filename = item.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            name = filename.decode("utf-8", errors="surrogateescape")
            if kind != "blob" or mode == "120000":
                exclusions["nonfile_or_symlink"] += 1
            elif not selected(name):
                exclusions["out_of_text_scope"] += 1
            else:
                entries.append({"path": name, "blob": oid})
                used[oid].add(name)
        if entries != row["selected_entries"]:
            raise ValueError("Selected history entries omitted or substituted")
    if history["excluded_entries"] != dict(exclusions):
        raise ValueError("Historical exclusion inventory differs")
    if [row["git_blob"] for row in history["blobs"]] != sorted(used):
        raise ValueError("History blob coverage incomplete or duplicated")
    for row in history["blobs"]:
        raw = _git(root, "cat-file", "blob", row["git_blob"])
        oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if (oid != row["git_blob"] or _sha(raw) != row["sha256"] or len(raw) != row["bytes"]
                or sorted(used[oid]) != row["paths"] or matches(raw) != row["literal_matches"]):
            raise ValueError("Historical raw bytes, paths or matches differ")
    roots = scope["current_roots"]
    for name in roots:
        _local(root, name)
    if current["roots"] != roots:
        raise ValueError("Current scope differs")
    raw_names = subprocess.check_output(["rg", "--files", "--hidden", *roots], cwd=root).decode().splitlines()
    paths = sorted(name for name in raw_names if selected(name)
                   and not (root / name).is_symlink() and _local(root, name).is_file())
    if paths != [row["path"] for row in current["files"]]:
        raise ValueError("Current file coverage differs; snapshot is historical")
    for row in current["files"]:
        raw = _local(root, row["path"]).read_bytes()
        if _sha(raw) != row["sha256"] or len(raw) != row["bytes"] or matches(raw) != row["literal_matches"]:
            raise ValueError("Current raw bytes or matches differ; snapshot is historical")
    _lineage(root, lineage, names)
    if _git(root, "show-ref", "--head") != refs:
        raise ValueError("Refs changed during exposure verification")
    return {"kind": "verified_local_exposure_scope_v1", "scope": scope_ref, "review": review_ref,
            "commits_verified": len(commits), "blobs_verified": len(used), "current_files_verified": len(paths),
            "names_without_literal_matches": [name for name in names if all(name not in row["literal_matches"]
                for row in history["blobs"] + current["files"])],
            "lineage_reconstructed": True, "verdict": "INCONCLUSIVE", "certifies_eligibility": False,
            "certifies_acceptance": False, "limitations": LIMITS}
