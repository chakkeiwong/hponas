# HPO-NAS: Hyperparameter and Neural Architecture Search

**Version:** 0.1.0  
**Status:** Development (Tier 0)  
**License:** MIT  

---

## Overview

HPO-NAS is a system for **moderate architecture-coordinate Neural Architecture Search** supporting:
- Hyperparameter optimization with 2-10 parameters per search space
- Architectural choices: width, depth, layers, activation
- Training hyperparameters: optimizer, learning rate, dropout, batch size
- Multi-fidelity optimization (ASHA, MO-ASHA)
- Multi-objective optimization (qLogNEHVI, NSGA-II)

**Out of scope:** Cell search, weight sharing, supernets, differentiable NAS

---

## Installation

### Requirements
- Python 3.9+
- pip 21.0+

### Basic Installation
```bash
pip install -e .
```

### With Development Dependencies
```bash
pip install -e ".[dev]"
```

### With All Optional Dependencies
```bash
pip install -e ".[all]"
```

---

## Quick Start

```python
from hponas import Study, GPSearcher, LocalExecutor
from hponas.workloads import rl_routine

# Define search space
search_space = {
    "width": [32, 64, 128, 256],
    "depth": [2, 3, 4],
    "learning_rate": (1e-5, 1e-2, "log"),
}

# Create study
study = Study(
    searcher=GPSearcher(),
    executor=LocalExecutor(),
    workload=rl_routine,
    search_space=search_space,
    objective="maximize",
    budget=100,
)

# Run optimization
result = study.run()
print(f"Best config: {result.best_config}")
print(f"Best value: {result.best_value}")
```

---

## Features

### Tier 0 (Current)
- ✅ GP+qLogEI Bayesian optimization baseline
- ✅ Random and Sobol baselines
- ✅ Local and distributed (Ray) executors
- ✅ RL policy search workload

### Tier 1 (Planned)
- ASHA multi-fidelity optimization
- MO-ASHA multi-objective multi-fidelity
- qLogNEHVI multi-objective acquisition
- Chebyshev scalarization and NSGA-II baselines

### Tier 2 (Research)
- TuRBO trust region optimization (conditional)
- Transfer learning and warm-start
- Prior-weighted methods (πBO, PriorBand)

---

## Project Structure

```
hponas/
├── hponas/              # Core library
│   ├── searchers/       # Optimization algorithms
│   ├── schedulers/      # Multi-fidelity schedulers
│   ├── executors/       # Trial execution backends
│   ├── workloads/       # Benchmark workloads
│   └── study.py         # Main Study API
├── tests/               # Test suite
│   ├── unit/            # Layer 1: Fast unit tests
│   ├── conformance/     # Layer 2: Contract tests
│   └── integration/     # Layer 2: Integration tests
├── validation/          # Layer 3: Statistical validation
│   ├── protocols/       # Preregistered protocols
│   └── results/         # Validation results
└── docs/                # Documentation
```

---

## Development

### Running Tests
```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/unit/

# Conformance tests
pytest tests/conformance/

# With coverage
pytest --cov=hponas --cov-report=html
```

### Code Quality
```bash
# Linting
ruff check hponas/

# Formatting
black hponas/ tests/

# Type checking
mypy hponas/
```

### Mutation Testing
```bash
# Run mutation tests (Layer 1 quality check)
mutmut run
mutmut results
```

---

## Validation

All methods undergo statistical validation per preregistered protocols in `validation/protocols/`.

**Tier 0 Gate Criteria:**
- V01: Vendor Parity (GP vs BoTorch, TPE vs Optuna)
- V02: State Replay (deterministic trajectories)
- V03: Mutation Testing (≥0.9 kill score)
- V04-T0: Sobol vs Random equivalence
- V05: Workload Correctness (rl_routine)
- V14: Budget Adherence
- V16: Validator Audit (all validators pass)

---

## Documentation

- [Build Program](BUILD_PROGRAM_v3.md) - Project roadmap and timeline
- [Traceability Matrix](TRACEABILITY_MATRIX_v1.md) - LaTeX spec → implementation mapping
- [Test Pyramid](TEST_PYRAMID_v1.md) - Test organization and coverage
- [Contract Semantics](CONTRACT_SEMANTICS_v1.md) - Control-plane behavior
- [NAS Scope](NAS_SCOPE_DECISION.md) - Scope definition

---

## Contributing

This project is under active development. Contributions welcome after Tier 0 gate passes.

### Development Setup
```bash
# Clone repository
git clone <repo-url>
cd hponas

# Install in development mode with all dependencies
pip install -e ".[dev,test]"

# Run pre-commit checks
pre-commit install
```

---

## Citation

```bibtex
@software{hponas2026,
  title={HPO-NAS: Hyperparameter and Neural Architecture Search},
  author={},
  year={2026},
  url={}
}
```

---

## License

MIT License - see LICENSE file for details

---

## Status

**Current Phase:** Tier 0 Execution (Day 1/25)  
**Gate Status:** Not yet run  
**Last Updated:** 2026-09-10

---

**Project Authority:** BUILD_PROGRAM_v3.md, HPO_NAS_RECOVERY_MASTER_PROGRAM.md
