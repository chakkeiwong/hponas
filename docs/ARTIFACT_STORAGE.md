# Source, summaries and local evidence

GitHub carries source code, tests and small deterministic fixtures, buildable LaTeX, plans, guides and concise result summaries. Raw campaigns, checkpoints, model weights, logs, databases, copied runtimes, mutation populations and generated PDFs belong in local archives. Git LFS is not used for experiment storage.

## Preserved record

The cleanup on 28 October 2026 preserves the former published commit 1e9a311bac5a3b0cd68bf6068d5e777cb6855f67 and its complete Git lineage in a verified local bundle. Raw working-tree evidence is separately archived with original relative paths; original LFS objects are retained locally. Existing evidence files remain available in the original research checkout and are ignored by Git.

Local archive location: /home/ubuntu/workspace/hponas/.local-archives/publication-cleanup-2026-10-28/. Its manifest records archive sizes, SHA-256 values, verification and the rewritten-history mapping. Do not add this directory or archive files to Git. This is a local preservation copy; it is not an independent off-machine backup.

Public summaries live in [docs/results](results/README.md) and the extension RESULTS.md/FINDINGS.md files. The [structured master register](program/program.json) retains historical evidence identities and paths for traceability. Those raw paths are archive-relative references; they are intentionally absent from a normal clone. Missing raw evidence must never be treated as fresh scientific verification.

## Verification modes

Ordinary clones run the bounded archive-independent regression roster and publication guard. The guard refuses raw evidence directories, LFS pointers, large individual files and an excessive tracked tree. CI no longer downloads LFS objects or runs whole-campaign reconstruction from absent evidence.

Full scientific reconstruction remains available after restoring the local archive into a separate trusted checkout of the original source. First verify the archive SHA-256 recorded in the manifest, inspect its entries, then extract preserving relative paths. Keep that restored directory out of Git. Only use the original source-bound commands with their original manifests and runtime. Existing rules still prohibit repeating consumed scientific allocations.

The published history was rewritten to remove raw artifacts from reachable branches and tags. Existing collaborators should re-clone, or preserve local work before explicitly realigning to the new history; do not merge the old artifact-bearing history back. The original refs and old-to-new commit mapping remain in the local archive.

GitHub may retain unreachable cached objects and already-uploaded LFS objects after a history rewrite. Removing them from branch history prevents normal clones and synchronization from downloading them. Physical deletion of server-retained objects is separate from rewriting repository refs.
