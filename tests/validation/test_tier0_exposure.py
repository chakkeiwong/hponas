import hashlib
import json

import pytest

from validation import tier0_exposure as exposure


def bind(root, name, value):
    path = root / name
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    raw = b"# ant\n"
    oid = hashlib.sha1(b"blob 6\0" + raw).hexdigest()
    refs = b"a HEAD\n"
    tree = f"100644 blob {oid}\tsrc/model.py\0".encode()
    responses = {("show-ref", "--head"): refs, ("rev-list", "--all", "HEAD"): b"a\n",
                 ("ls-tree", "-rz", "--full-tree", "a"): tree, ("cat-file", "blob", oid): raw}
    monkeypatch.setattr(exposure, "_git", lambda root, *args: responses[args])
    (tmp_path / "src").mkdir()
    (tmp_path / "src/model.py").write_bytes(raw)
    scope = {"kind": "scoped_exposure_coverage_plan", "names": ["ant"], "patterns": {"ant": "ant"},
             "history_suffixes": [".py"], "history_exclusions": [], "current_roots": ["src"]}
    row = {"path": "src/model.py", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
           "literal_matches": {"ant": [1]}}
    history = {"refs": ["a HEAD"], "refs_sha256": hashlib.sha256(refs).hexdigest(),
               "commits": [{"commit": "a", "tree_listing_sha256": hashlib.sha256(tree).hexdigest(),
                            "selected_entries": [{"path": row["path"], "blob": oid}]}],
               "blobs": [{k: v for k, v in row.items() if k != "path"} | {"git_blob": oid, "paths": [row["path"]]}],
               "excluded_entries": {}}
    current = {"roots": ["src"], "files": [row]}
    lineage = {"sources": [{"environment": "ant", "status": "missing_pinned_source"}], "related_pairs": []}
    return tmp_path, scope, history, current, lineage


def verify(snapshot, **labels):
    root, scope, history, current, lineage = snapshot
    scope_ref = bind(root, "scope.json", scope)
    refs = [bind(root, name, value) for name, value in (
        ("history.json", history), ("current.json", current), ("lineage.json", lineage))]
    review = {"kind": "local_exposure_history_and_lineage_review", "files": refs, **labels}
    return exposure.verify_local_exposure(root, scope_ref, bind(root, "review.json", review))


def test_local_reconstruction_has_no_global_eligibility_or_chronology_claim(snapshot):
    report = verify(snapshot, verdict="PASS", approved=True, externally_unexposed=True)
    assert report["commits_verified"] == report["blobs_verified"] == report["current_files_verified"] == 1
    assert report["names_without_literal_matches"] == []
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["certifies_eligibility"] is report["certifies_acceptance"] is False
    assert len(report["limitations"]) == 4


@pytest.mark.parametrize("fault", ["commit", "duplicate_commit", "entry", "blob", "path", "matches",
                                   "current", "duplicate_current", "lineage", "exclusions"])
def test_rebound_producer_omissions_and_fabrications_are_recomputed(snapshot, fault):
    root, scope, history, current, lineage = snapshot
    if fault == "commit":
        history["commits"].clear()
    elif fault == "duplicate_commit":
        history["commits"] *= 2
    elif fault == "entry":
        history["commits"][0]["selected_entries"].clear()
    elif fault == "blob":
        history["blobs"].clear()
    elif fault == "path":
        history["blobs"][0]["paths"] = ["elsewhere.py"]
    elif fault == "matches":
        history["blobs"][0]["literal_matches"] = {}
    elif fault == "current":
        (root / "src/extra.py").write_text("new bytes")
    elif fault == "duplicate_current":
        current["files"] *= 2
    elif fault == "lineage":
        lineage["sources"] = []
    else:
        history["excluded_entries"] = {"out_of_text_scope": 1}
    with pytest.raises(ValueError):
        verify(snapshot, verdict="PASS", approved=True)


def test_lineage_is_rebuilt_from_xml_not_claimed_similarity(snapshot):
    root, scope, history, current, lineage = snapshot
    (root / "assets").mkdir()
    (root / "assets/ant.xml").write_text('<world><body name="torso"><joint name="hip"/></body></world>')
    (root / "ant.py").write_text('from core import Base\nclass Ant(Base):\n    asset = "assets/ant.xml"\n')
    source = {"environment": "ant", "path": "ant.py", "sha256": hashlib.sha256((root / "ant.py").read_bytes()).hexdigest(),
              "imports": ["core"], "class_bases": ["Base"], "assets": [{"path": "assets/ant.xml",
              "sha256": hashlib.sha256((root / "assets/ant.xml").read_bytes()).hexdigest(), "elements": 3,
              "body_names": ["torso"], "joint_names": ["hip"]}]}
    lineage["sources"] = [source]
    lineage["related_pairs"] = [{"candidate": "ant", "previously_exposed": "ant", "candidate_xml_elements": 3,
                                  "prior_xml_elements": 3, "exact_shared_element_occurrences": 3}]
    assert verify(snapshot)["lineage_reconstructed"]
    lineage["related_pairs"][0]["exact_shared_element_occurrences"] = 2
    with pytest.raises(ValueError, match="shared-element"):
        verify(snapshot)
