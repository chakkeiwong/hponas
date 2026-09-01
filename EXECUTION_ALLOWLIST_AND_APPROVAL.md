# Execution Allowlists and Upfront Approval

**Date:** 2026-09-01
**Repository:** `/home/ubuntu/workspace/hponas`
**Scope:** Lock the generated build program and establish governance before Tier 0 execution

## Executive answer

The repository is **not yet ready for unattended Tier 0 execution**. The plan itself is in good shape, but three operational gates remain:

1. `BUILD_PROGRAM_v2.md` must receive formal human approval and be locked as `program-v2.0`.
2. The execution environment must be bootstrapped once. In the current shell, `hponas` is not installed and `pytest-cov` is missing.
3. The governance changes (approval record, progress generator, CI checks, and archival of superseded plans) must be authorized.

The generated program is internally consistent: `python3 tools/generate_build_program.py --verify` passes. With `PYTHONPATH=.` the current code also passes 56 tests and both spike examples. The ordinary gate command currently reports **BLOCKED** only because it runs in an uninstalled environment and the configured coverage plugin is absent.

## Current state checked

| Check | Result | Meaning |
|---|---|---|
| Build-program regeneration | Pass | `BUILD_PROGRAM_v2.md` matches its inputs |
| Tests with source path supplied | Pass | 56 tests pass; two Sobol balance warnings |
| Spike examples with source path supplied | Pass | Determinism and crash recovery pass |
| `python3 tools/gate_check.py --phase r1` in the current shell | Blocked | `hponas` is not installed; pytest rejects `--cov` options |
| `BUILD_PROGRAM_v2_APPROVAL.md` | Missing | No human sign-off has been recorded |
| `program-v2.0` tag | Missing | The plan is not locked |
| Governance workflow | Missing | Existing `.github/workflows/ci.yml` is R1 CI, not governance CI |
| Remote push | Not authorized | No push should be performed implicitly |

## Allowlist amendments

There are two separate permission layers. The project file `.claude/settings.local.json` controls command approval in the Claude client; it cannot grant this Codex sandbox network access or write access outside the workspace. A host-level escalation/prefix approval is still required for environment installation and any external push.

A written approval in chat does not itself change the host policy. To guarantee a no-click run, the operator must either pre-approve the exact command prefixes in the host UI or approve one audited runner command whose contents are reviewed in advance.

There is no such runner script in the repository yet. Until one is created and reviewed, use the exact command entries below; do not approve a generic shell prefix as a substitute.

| Operation | Project-local entry | Host-level approval |
|---|---|---|
| Read files, inspect status/diffs, edit files in the repository | Usually none beyond the normal workspace policy | None |
| Run Python tests, examples, generator, and gate checks | Add the exact entries below | None after the package is installed |
| Create the conda environment and install dependencies | Add the exact bootstrap entries below | Yes: network plus writes to the conda environment |
| Commit, tag, and archive locally | Add exact git entries or use an audited runner | Usually none in the workspace, but human authorization is required |
| Push `origin main --tags` | Add the exact push entry only if desired | Yes: shared remote-state change |
| GPU/Ray campaigns | Add only the named runner path | Yes: explicit resource and cost authorization |

### 1. Local, low-risk commands

Add exact entries like these to the project-local allowlist for this run (use the client's equivalent syntax if it differs):

```json
[
  "Bash(python3 tools/generate_build_program.py --verify)",
  "Bash(python3 tools/gate_check.py --phase r1)",
  "Bash(python3 -m pytest tests/ -q)",
  "Bash(python3 examples/spike_branin.py)",
  "Bash(python3 examples/spike_crash_recovery.py)",
  "Bash(conda run -n hponas python -m pytest tests/ -q)",
  "Bash(conda run -n hponas python tools/gate_check.py --phase r1)"
]
```

These cover regeneration, the R1 gate, tests, and examples after installation without allowing arbitrary shell commands.

### 2. Environment/bootstrap commands

Approve one of the following exact commands, depending on the available package manager:

```text
mamba env create --yes -f setup/environment.yml
conda env create --yes -f setup/environment.yml
```

The matching project-local entries are:

```text
Bash(mamba env create --yes -f setup/environment.yml)
Bash(conda env create --yes -f setup/environment.yml)
```

This is the only step that needs package-network access and writes outside the repository (the `hponas` environment under the conda installation). `--yes` makes the operation non-interactive. It downloads the dependencies declared in `setup/environment.yml` from the configured conda channels and PyPI. Channel terms, proxy credentials, and SSH credentials (if any) must already be accepted/configured; those cannot be safely approved in the middle of a run. After creation, install the project and development tools once:

```text
conda run -n hponas python -m pip install --no-input -e ".[dev]"
```

The corresponding project-local entry belongs with the bootstrap approval, not the low-risk test entries:

```text
Bash(conda run -n hponas python -m pip install --no-input -e ".[dev]")
```

The current shell uses a separate `tf-gpu` environment, which explains the missing package and coverage plugin. Do not treat a `PYTHONPATH=.` smoke test as a substitute for the clean environment check.

### 3. Governance file and git operations

Authorize these repository mutations as one bounded batch:

```text
create BUILD_PROGRAM_v2_APPROVAL.md
create tools/update_progress.py
create .github/workflows/governance.yml
mkdir -p archive
git mv BUILD_PROGRAM.md archive/BUILD_PROGRAM_v1_REJECTED.md
git mv BUILD_PROGRAM_RECONCILIATION_COMPLETE.md archive/
git add the files above
git commit with a recorded message
git tag program-v2.0
```

For a project-local allowlist, prefer these exact git entries over a wildcard:

```json
[
  "Bash(git mv BUILD_PROGRAM.md archive/BUILD_PROGRAM_v1_REJECTED.md)",
  "Bash(git mv BUILD_PROGRAM_RECONCILIATION_COMPLETE.md archive/BUILD_PROGRAM_RECONCILIATION_COMPLETE.md)",
  "Bash(git add BUILD_PROGRAM_v2_APPROVAL.md tools/update_progress.py .github/workflows/governance.yml)",
  "Bash(git add archive/BUILD_PROGRAM_v1_REJECTED.md archive/BUILD_PROGRAM_RECONCILIATION_COMPLETE.md)",
  "Bash(git commit -m \"BUILD_PROGRAM v2.0: approved plan for Tier 0-2\")",
  "Bash(git tag program-v2.0)"
]
```

Add `Bash(git push origin main --tags)` only when the remote-push decision is explicitly `YES`.

Archiving uses `git mv`, so the superseded documents remain recoverable in history. I will not delete files, rewrite history, force-push, or use a broad `git add -A` without separate instruction.

### 4. Remote push (separate, explicit)

If the result should be published, add a one-time approval for this exact operation only:

```text
git push origin main --tags
```

This changes shared remote state and should remain a distinct approval even when local commits and tags are pre-approved. The remote credential and host-key setup must already be non-interactive; otherwise a push can still stop for a password or host-key prompt. No push is required to complete local validation or prepare the governance changes.

### 5. Network and accelerator work

No new external network allowlist is needed for the documentation and local gate work. If later work needs literature retrieval, use host-scoped, time-bounded URLs already listed in the project settings rather than adding `curl *`.

Ray/GPU campaigns are a separate resource decision. Before allowing them, specify the runner path, target environment, accelerator budget, maximum wall time, artifact location, and cancellation policy. Do not add a generic `python3 *`, `ray *`, `sudo *`, or unrestricted network rule.

## Upfront approval requested

To run the governance setup without interactive prompts, provide one written authorization covering the following:

```text
APPROVE:
- Create/update files only under /home/ubuntu/workspace/hponas.
- Create the conda environment `hponas` from setup/environment.yml and install `.[dev]`.
- Use the configured package channels/PyPI during that installation.
- Run CPU-only tests, examples, generator verification, and gate checks.
- Create BUILD_PROGRAM_v2_APPROVAL.md, governance tooling, the governance CI workflow,
  and archive superseded planning documents with git mv.
- Commit the local changes and create tag program-v2.0.
- [YES/NO] Push `origin main --tags` after local verification.
- [YES/NO] Permit any GPU/Ray campaign; if yes, state the accelerator/time budget.
```

Two project decisions must be included in that approval; they cannot be inferred from a shell permission:

1. **Statistical reviewer:** recommend formally waiving the overdue verification as non-blocking, with the deferral and pilot requirement documented in the approval record. A human statistician review remains preferable if external scientific sign-off is required.
2. **V12 placement:** approve the generated program's assignment of V12 (warm-start savings) to the Distributed Beta gate, where enough studies exist to measure it.

The project sponsor/tech lead must supply the names and date in `BUILD_PROGRAM_v2_APPROVAL.md`; automation must not fabricate those sign-offs.

For the recommended local-only run, the shortest unambiguous authorization is:

```text
APPROVE GOVERNANCE + ENVIRONMENT; REVIEWER=WAIVE; V12=DISTRIBUTED_BETA; PUSH=NO; GPU=NO
```

Set `PUSH=YES` only when publishing to `origin` is intended, and include a concrete accelerator/time budget before setting `GPU=YES`.

## No-click execution order

Once the authorization above is recorded, the run can be executed as one bounded sequence:

1. Create/verify the `hponas` environment and install the package with development extras.
2. Run import checks, the full test suite, both spike examples, and the R1 gate.
3. Run `tools/generate_build_program.py --verify`.
4. Write the approval record and governance files; archive v1 documents.
5. Run the governance checks and inspect the final diff.
6. Commit and tag locally.
7. Push only if the explicit remote-push checkbox is `YES`.

Any failure stops the sequence with a report; it should not trigger a request to click through an unrelated command. CPU validation does not require GPU approval.

## Guardrails

Do **not** add these broad or destructive rules:

```text
Bash(*)
Bash(curl *)
Bash(sudo *)
Bash(rm -rf *)
Bash(git push --force *)
Bash(python3 *)
```

Use exact paths, exact hosts, bounded timeouts, and the smallest command prefix that covers the approved work.

## Source note

The official OpenAI Docs lookup was unavailable in this sandbox because DNS/network access failed. The operational conclusions above are based on the active tool policy, the repository's `.claude/settings.local.json`, `setup/INSTALL.md`, `GOVERNANCE_IMPLEMENTATION.md`, and the validation commands run on 2026-09-01.
