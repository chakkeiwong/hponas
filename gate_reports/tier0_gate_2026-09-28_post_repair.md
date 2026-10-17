# Tier 0 recomputation after packaging and prior repairs

Source fingerprint: `f6410155a35289286544fc8d53d8fc008ac0c3ef4a56b81832ccc75c3299f0bb`. Release remains **BLOCKED**.

This preserves a read-only recomputation without overwriting the earlier dated gate report or campaign artifacts. Old V02 GP suggestions diverge under the repaired model; current same-source replay is covered by the passing suite. No old receipt was relabeled fresh.

```text

================================================================================
GATE CHECK: TIER0
Timestamp: 2026-09-28T18:38:00.871048
Mode: dry-run
================================================================================

❌ BLOCKED (6):
   • V01: Campaign: PASS; Source/protocol fingerprint is stale or results changed
   • V02: Campaign: PASS; Recomputed verdict: FAIL; Source/protocol fingerprint is stale or results changed
   • V03: Campaign: INCONCLUSIVE; Source/protocol fingerprint is stale or results changed
   • V04-T0: Campaign: INCONCLUSIVE; Source/protocol fingerprint is stale or results changed
   • V05: Campaign: INCONCLUSIVE; Source/protocol fingerprint is stale or results changed
   • V14: Campaign: PASS; Source/protocol fingerprint is stale or results changed

================================================================================
VERDICT: BLOCKED
================================================================================

❌ Blockers present. Must resolve before phase close.

(dry-run mode: no gate report written)
```
