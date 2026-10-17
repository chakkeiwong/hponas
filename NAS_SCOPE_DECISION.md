# NAS scope decision

**Version:** 1.1, 12 October 2026. Authority: [the master program](CONSOLIDATED_MASTER_AUTHORITY.md) and its accepted bank-product scope clarification. The [original decision](archive/program-2026-10-12/before-bank-product-scope-01/NAS_SCOPE_DECISION.md) remains archived.

## Supported direction

Build HPO and **moderate architecture-coordinate NAS** for the model families used by a universal retail bank. See the [product contract](docs/program/BANK_HPO_NAS_PRODUCT_CONTRACT.md) for evaluation, profile coverage and completion criteria. A caller supplies the model builder and objective; the tool validates declared capabilities, budgets, evaluation roles and recovery.

Architecture coordinates include width, depth, activation and representation size, with conditional training choices such as optimizer, learning rate, batch size and regularization. Every admitted coordinate must change the actual model or training procedure. The model exposes measurable size/work and reloadable artifacts; incompatible checkpoint transfers are refused or use an explicitly charged restart/distillation policy.

The original roughly **2–10 coordinates** define the initial qualified envelope. They are not a mathematical upper limit for universal HPO. Larger spaces require a method-specific capability declaration and bounded verification; the existing accepted evidence does not automatically extend to them.

## Exclusions and measured costs

General cell/topology search, supernets, shared-weight search, differentiable architecture optimization and architecture meta-learning are excluded. No general-NAS research extension is implied by the bank vision.

Ordinary coordinate studies may report or constrain measured training cost, model size and runtime. This is distinct from a hardware-specific latency/energy prediction or device-qualification NAS system, which is not promised. No guaranteed optimization win, production readiness, fixed delivery date or numerical industry-coverage percentage is supported by this scope decision. The old six-month/80-percent estimates are historical assertions, not current evidence.

## Workload contract

Each supported profile must supply a search space and capabilities, actual model builder, objective/constraint declaration, measured budget/fidelity, tuning and final-evaluation roles, resumable artifacts and a maintained configured-study example. Independent mathematical or finite reference checks qualify the stylized workflow; exposed fixtures are not unseen bank data or empirical performance evidence.

Existing finite workloads remain documented in [WORKLOADS](docs/WORKLOADS.md). PRD-01 closes general study contracts and BANK-01 adds the bank-family profiles. Their dependency-ordered stages and evidence live in the master register. Old example sketches, such as a proposed Humanoid holdout, do not override the adopted self-contained validation scope or allocate large RL campaigns.

## Decision continuity

The original choice of moderate coordinate NAS is retained. This revision clarifies reusable banking coverage and distinguishes the initial dimension envelope from a universal support claim. Separate-machine testing stays waived; trusted supervised local research remains the qualified operational scope. Recovery checklist items 1 and 12 retain their scope and template obligations. Program completion requires the registered PRD-01 and BANK-01 final reviews; passing mutation testing alone is insufficient.
