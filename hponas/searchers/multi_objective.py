"""Vector-aware baseline for the durable multi-objective Study contract."""
from copy import deepcopy
from importlib.metadata import version

import numpy as np

from hponas.encoding import as_knob_space, SpaceEncoder
from hponas.multi_objective import ObjectiveSpec
from hponas.searchers.base import BaseSearcher
from hponas.searchers.random_searcher import RandomSearcher
from hponas.types import Config
from hponas.capabilities import SearcherCapabilities, MIXED


class MultiObjectiveRandomSearcher(BaseSearcher):
    """Random baseline retaining complete named vectors and constraint outcomes."""

    support = SearcherCapabilities(MIXED, conditionals=True, objectives='vector', constraints=True, partial_fidelity=True)

    def __init__(self, search_space, *, objectives, constraints=None, work_unit="integer_operations", seed=0):
        super().__init__(search_space, seed)
        self.multi_objective_spec = ObjectiveSpec(objectives, constraints=constraints, work_unit=work_unit)
        self._sampler = RandomSearcher(search_space, seed)

    def suggest(self):
        return self._sampler.suggest()

    def observe(self, result):
        if result.trial_id not in self.trials:
            raise ValueError("Vector result needs a registered trial configuration")
        if any(r.trial_id == result.trial_id for r in self.history):
            raise ValueError("An observed vector cannot be revised")
        self.multi_objective_spec.validate_result(result)
        super().observe(result)

    def get_best(self, maximize=True):
        raise ValueError("Vector observations require Pareto reporting")

    def get_state(self):
        return deepcopy({**super().get_state(), "kind": "multi_objective_random_v1",
                         "space": as_knob_space(self.search_space).to_dict(),
                         "metric": self.multi_objective_spec.contract,
                         "sampler": self._sampler.get_state()})

    def set_state(self, state):
        if (state.get("kind") != "multi_objective_random_v1"
                or state.get("space") != as_knob_space(self.search_space).to_dict()
                or state.get("metric") != self.multi_objective_spec.contract):
            raise ValueError("Vector searcher checkpoint identity differs")
        restored = type(self)(self.search_space, **self.multi_objective_spec.contract, seed=state["seed"])
        restored._sampler.set_state(deepcopy(state["sampler"]))
        BaseSearcher.set_state(restored, deepcopy(state))
        for config in restored.trials.values():
            as_knob_space(self.search_space).validate_config(config.values)
        history, restored.history = restored.history, []
        for result in history:
            restored.observe(result)
        self.__dict__.update(restored.__dict__)

    @property
    def capabilities(self):
        return self.support.report()


class MultiObjectiveBayesSearcher(MultiObjectiveRandomSearcher):
    """BoTorch qLogNEHVI or random-weight augmented Chebyshev/qLogEI.

    Acquisition is maximized over a bounded sampled candidate set. GP fitting
    and posterior integration are numerical approximations, not finite-answer
    certificates. Failed and partial-fidelity results never train these models.
    Constraints are modeled separately as measured excess above frozen bounds.
    """

    support = SearcherCapabilities(('continuous', 'ordinal'), objectives='vector', constraints=True, partial_fidelity=True)

    def __init__(self, search_space, *, objectives, constraints=None, work_unit="integer_operations", seed=0,
                 method="qlognehvi", n_initial=4, candidate_count=64, mc_samples=64,
                 fit_maxiter=40, model_fidelity=1.):
        super().__init__(search_space, objectives=objectives, constraints=constraints, work_unit=work_unit, seed=seed)
        self._encoder = SpaceEncoder(search_space)
        if not self._encoder.space.knobs or any(k.kind not in {"continuous", "ordinal"} or k.condition is not None
                                                for k in self._encoder.space.knobs):
            raise ValueError("Bayesian MO currently requires unconditional continuous/ordinal coordinates")
        if method not in {"qlognehvi", "chebyshev"}:
            raise ValueError("Unknown Bayesian multi-objective method")
        for label, value in [("n_initial", n_initial), ("candidate_count", candidate_count),
                             ("mc_samples", mc_samples), ("fit_maxiter", fit_maxiter)]:
            if type(value) is not int or not 2 <= value <= 1024:
                raise ValueError(f"{label} must be an integer in [2,1024]")
        if isinstance(model_fidelity, bool) or not np.isfinite(model_fidelity) or model_fidelity <= 0:
            raise ValueError("Positive finite model fidelity required")
        self.model_fidelity = model_fidelity
        self._options = dict(method=method, n_initial=n_initial, candidate_count=candidate_count,
                             mc_samples=mc_samples, fit_maxiter=fit_maxiter, model_fidelity=model_fidelity)
        self._versions = {name: version(name) for name in ["numpy", "torch", "botorch", "gpytorch"]}
        self.acquisition_trace = []

    def suggest(self):
        spec = self.multi_objective_spec
        valid = [r for r in self.history if r.status == "completed" and r.fidelity == self.model_fidelity]
        if len(valid) < self._options["n_initial"]:
            return super().suggest()
        import torch
        from botorch.models import SingleTaskGP, ModelListGP
        from botorch.fit import fit_gpytorch_mll
        from botorch.acquisition.logei import qLogExpectedImprovement
        from botorch.acquisition.objective import GenericMCObjective
        from botorch.acquisition.multi_objective.logei import qLogNoisyExpectedHypervolumeImprovement
        from botorch.acquisition.multi_objective.objective import IdentityMCMultiOutputObjective
        from botorch.optim import optimize_acqf_discrete
        from botorch.sampling.normal import SobolQMCNormalSampler
        from gpytorch.mlls import ExactMarginalLogLikelihood

        seed = int(self._sampler.rng.randint(0, 2**31-1))
        candidates = [super(MultiObjectiveBayesSearcher, self).suggest() for _ in range(self._options["candidate_count"])]
        x = np.array([self._encoder.encode(self.trials[r.trial_id]) for r in valid])
        observations = [spec.validate_result(r) for r in valid]
        y = -np.array([spec.normalize(row["objectives"]) for row in observations])
        bounds = spec.contract["constraints"]
        excess = np.array([[row["constraints"][k]-bound for k, bound in bounds.items()] for row in observations])
        weights = None
        if self._options["method"] == "chebyshev":
            weights = self._sampler.rng.dirichlet(np.ones(len(spec.names)))
            # Recompute every scalar observation under this proposal's weights.
            y = -(((-y)*weights).max(axis=1)+.05*((-y)*weights).sum(axis=1))[:, None]
        num_outputs = y.shape[1]
        training = np.column_stack([y, excess])
        observed_ids = {r.trial_id for r in self.history}
        pending = [self._encoder.encode(config) for tid, config in self.trials.items() if tid not in observed_ids]
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            train_x = torch.tensor(x, dtype=torch.double)
            models = []
            for column in training.T:
                model = SingleTaskGP(train_x, torch.tensor(column[:, None], dtype=torch.double))
                fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model),
                                optimizer_kwargs={"options": {"maxiter": self._options["fit_maxiter"]}})
                models.append(model)
            model = ModelListGP(*models)
            sampler = SobolQMCNormalSampler(torch.Size([self._options["mc_samples"]]), seed=seed)
            constraint_fns = [lambda samples, j=j: samples[..., num_outputs+j] for j in range(len(bounds))]
            options = dict(model=model, sampler=sampler, constraints=constraint_fns or None,
                           X_pending=torch.tensor(np.array(pending), dtype=torch.double) if pending else None)
            if self._options["method"] == "qlognehvi":
                acq = qLogNoisyExpectedHypervolumeImprovement(
                    **options, ref_point=[-1.]*num_outputs, X_baseline=train_x,
                    objective=IdentityMCMultiOutputObjective(list(range(num_outputs))), prune_baseline=True)
            else:
                feasible = [bool(row["feasible"]) for row in observations]
                # The declared domain bounds give -1.05 as the worst augmented
                # scalar score if no feasible observation has been seen yet.
                best = float(y[feasible].max()) if any(feasible) else -1.05
                acq = qLogExpectedImprovement(**options, best_f=best,
                                              objective=GenericMCObjective(lambda samples, X=None: samples[..., 0]))
            choices = torch.tensor(np.unique(np.array([self._encoder.encode(c) for c in candidates]), axis=0), dtype=torch.double)
            selected, value = optimize_acqf_discrete(acq, q=1, choices=choices, max_batch_size=64)
            config = Config(self._encoder.decode(selected[0].detach().numpy()))
        self.acquisition_trace.append({"method": self._options["method"], "seed": seed,
                                       "training_trial_ids": [r.trial_id for r in valid],
                                       "weights": weights.tolist() if weights is not None else None,
                                       "config": deepcopy(config.values), "log_acquisition": float(value.item())})
        return config

    def get_state(self):
        return {**super().get_state(), "kind": "botorch_multi_objective_v1", "options": deepcopy(self._options),
                "versions": deepcopy(self._versions), "acquisition_trace": deepcopy(self.acquisition_trace)}

    def set_state(self, state):
        if (state.get("kind") != "botorch_multi_objective_v1" or state.get("versions") != self._versions
                or state.get("options") != self._options or state.get("metric") != self.multi_objective_spec.contract
                or state.get("space") != as_knob_space(self.search_space).to_dict()):
            raise ValueError("Bayesian vector checkpoint identity differs")
        restored = type(self)(self.search_space, **self.multi_objective_spec.contract, seed=state["seed"], **self._options)
        restored._sampler.set_state(deepcopy(state["sampler"]))
        BaseSearcher.set_state(restored, deepcopy(state))
        for config in restored.trials.values():
            self._encoder.space.validate_config(config.values)
        history, restored.history = restored.history, []
        for row in history:
            restored.observe(row)
        restored.acquisition_trace = deepcopy(state["acquisition_trace"])
        self.__dict__.update(restored.__dict__)


def _optuna_constraints(trial):
    return trial.user_attrs["constraint_excess"]


class WrappedNSGAIISearcher(MultiObjectiveRandomSearcher):
    """Actual Optuna NSGA-II with a replayable ask/tell and pending-root ledger.

    The pinned vendor owns generations, constrained dominance and variation.
    Partial rungs do not become full-fidelity population observations.
    """

    support = SearcherCapabilities(MIXED, objectives='vector', constraints=True, partial_fidelity=True)

    def __init__(self, search_space, *, objectives, constraints=None, work_unit="integer_operations", seed=0,
                 population_size=16, model_fidelity=1.):
        import optuna
        super().__init__(search_space, objectives=objectives, constraints=constraints, work_unit=work_unit, seed=seed)
        self._space = as_knob_space(search_space)
        if not self._space.knobs or any(k.condition is not None or k.kind == "ordinal" and k.transform == "logit"
                                        for k in self._space.knobs):
            raise ValueError("Wrapped NSGA-II requires unconditional knobs and no logit ordinal axis")
        if type(population_size) is not int or population_size < 2:
            raise ValueError("NSGA-II population_size must be an integer >=2")
        if isinstance(model_fidelity, bool) or not np.isfinite(model_fidelity) or model_fidelity <= 0:
            raise ValueError("Positive finite model fidelity required")
        self.model_fidelity, self.population_size = model_fidelity, population_size
        self._version = version("optuna")
        self._study = optuna.create_study(directions=["minimize"]*len(objectives),
            sampler=optuna.samplers.NSGAIISampler(seed=seed, population_size=population_size,
                constraints_func=_optuna_constraints if self.multi_objective_spec.contract["constraints"] else None))
        self._pending, self._roots, self._events = {}, {}, []

    def suggest(self):
        trial, config = self._study.ask(), {}
        for knob in self._space.knobs:
            if knob.kind == "categorical":
                value = trial.suggest_categorical(knob.name, knob.bounds)
            elif knob.kind == "ordinal":
                value = trial.suggest_int(knob.name, *knob.bounds, log=knob.transform == "log")
            else:
                u = trial.suggest_float(knob.name, 0., 1.)
                lower, upper = (SpaceEncoder._warp(v, knob.transform) for v in knob.bounds)
                value = lower+u*(upper-lower)
                if knob.transform == "log":
                    value = np.exp(value)
                elif knob.transform == "logit":
                    value = 1/(1+np.exp(-value))
                value = float(np.clip(value, *knob.bounds))
            config[knob.name] = value
        self._space.validate_config(config)
        self._pending[trial.number] = {"trial": trial, "config": deepcopy(config)}
        self._events.append({"action": "suggest", "number": trial.number, "config": deepcopy(config)})
        return Config(config)

    def _tell(self, number, values, excess, status):
        import optuna
        if number not in self._pending or status not in {"COMPLETE", "FAIL"}:
            raise ValueError("NSGA-II tell has no pending vendor trial")
        if status == "COMPLETE":
            if (not isinstance(values, list) or len(values) != len(self.multi_objective_spec.names)
                    or not all(type(v) in (float, int) and np.isfinite(v) and 0 <= v <= 1 for v in values)
                    or not isinstance(excess, list) or len(excess) != len(self.multi_objective_spec.contract["constraints"])
                    or not all(type(v) in (float, int) and np.isfinite(v) for v in excess)):
                raise ValueError("Invalid NSGA-II complete observation")
        elif values is not None or excess is not None:
            raise ValueError("Failed NSGA-II trial cannot carry values")
        trial = self._pending[number]["trial"]
        if status == "COMPLETE":
            trial.set_user_attr("constraint_excess", excess)
        self._study.tell(trial, values, state=getattr(optuna.trial.TrialState, status))
        del self._pending[number]
        self._events.append({"action": "tell", "number": number, "values": values, "excess": excess, "status": status})

    def observe(self, result):
        if result.trial_id not in self.trials or any(r.trial_id == result.trial_id for r in self.history):
            raise ValueError("NSGA-II result must belong to a new registered observation")
        row = self.multi_objective_spec.validate_result(result)
        context = result.metadata.get("multi_objective_context", {})
        root = context.get("root_trial_id") or result.trial_id
        if context.get("endpoint_fidelity", self.model_fidelity) != self.model_fidelity:
            raise ValueError("NSGA-II result endpoint differs")
        if root not in self._roots:
            occupied = set(self._roots.values())
            number = next((i for i, p in self._pending.items() if i not in occupied and p["config"] == self.trials[result.trial_id].values), None)
            if number is None:
                raise ValueError("NSGA-II result has no matching pending suggestion")
            self._roots[root] = number
        number = self._roots[root]
        complete = result.is_valid() and row is not None and row["status"] == "completed"
        terminal = not complete or not row["feasible"] or result.fidelity == self.model_fidelity
        if terminal:
            full = complete and result.fidelity == self.model_fidelity
            values = self.multi_objective_spec.normalize(row["objectives"]) if full else None
            bounds = self.multi_objective_spec.contract["constraints"]
            excess = [row["constraints"][k]-v for k, v in bounds.items()] if full else None
            self._tell(number, values, excess, "COMPLETE" if full else "FAIL")
        super().observe(result)

    def finalize_pending(self):
        for number in list(self._pending):
            self._tell(number, None, None, "FAIL")

    def get_state(self):
        return deepcopy({**BaseSearcher.get_state(self), "kind": "wrapped_optuna_nsgaii_v1",
                         "space": self._space.to_dict(), "metric": self.multi_objective_spec.contract,
                         "optuna_version": self._version, "population_size": self.population_size,
                         "model_fidelity": self.model_fidelity, "events": self._events, "roots": self._roots})

    def set_state(self, state):
        for key, expected in [("kind", "wrapped_optuna_nsgaii_v1"), ("space", self._space.to_dict()),
                              ("metric", self.multi_objective_spec.contract), ("optuna_version", self._version),
                              ("population_size", self.population_size), ("model_fidelity", self.model_fidelity)]:
            if state.get(key) != expected:
                raise ValueError("NSGA-II checkpoint identity differs: " + key)
        restored = type(self)(self.search_space, **self.multi_objective_spec.contract, seed=state["seed"],
                              population_size=self.population_size, model_fidelity=self.model_fidelity)
        for event in state["events"]:
            if event["action"] == "suggest":
                restored.suggest()
            elif event["action"] == "tell":
                restored._tell(**{k: event[k] for k in ["number", "values", "excess", "status"]})
            else:
                raise ValueError("Unknown NSGA-II checkpoint action")
            if event != restored._events[-1]:
                raise ValueError("NSGA-II ask/tell ledger does not replay exactly")
        BaseSearcher.set_state(restored, deepcopy(state))
        seen = set()
        for row in restored.history:
            if row.trial_id not in restored.trials or row.trial_id in seen:
                raise ValueError("NSGA-II history has missing or duplicate trials")
            restored.multi_objective_spec.validate_result(row)
            seen.add(row.trial_id)
        for config in restored.trials.values():
            self._space.validate_config(config.values)
        numbers = {e["number"] for e in restored._events if e["action"] == "suggest"}
        if not set(state["roots"].values()) <= numbers or len(set(state["roots"].values())) != len(state["roots"]):
            raise ValueError("NSGA-II root assignment differs")
        restored._roots = deepcopy(state["roots"])
        suggestions = {e["number"]: e["config"] for e in restored._events if e["action"] == "suggest"}
        tells = {e["number"]: e for e in restored._events if e["action"] == "tell"}
        observed_full = set()
        for result in restored.history:
            root = result.metadata.get("multi_objective_context", {}).get("root_trial_id") or result.trial_id
            number = restored._roots.get(root)
            if number not in suggestions or suggestions[number] != restored.trials[result.trial_id].values:
                raise ValueError("NSGA-II root/configuration differs from the ask ledger")
            row = restored.multi_objective_spec.validate_result(result)
            if result.is_valid() and result.fidelity == self.model_fidelity:
                bounds = restored.multi_objective_spec.contract["constraints"]
                expected = {"action": "tell", "number": number,
                            "values": restored.multi_objective_spec.normalize(row["objectives"]),
                            "excess": [row["constraints"][k]-v for k, v in bounds.items()], "status": "COMPLETE"}
                if tells.get(number) != expected or number in observed_full:
                    raise ValueError("NSGA-II vendor observations differ from the vector history")
                observed_full.add(number)
        if {number for number, event in tells.items() if event["status"] == "COMPLETE"} != observed_full:
            raise ValueError("NSGA-II vendor observation has no full-fidelity result")
        self.__dict__.update(restored.__dict__)

    def __deepcopy__(self, memo):
        restored = type(self)(self.search_space, **self.multi_objective_spec.contract, seed=self.seed,
                              population_size=self.population_size, model_fidelity=self.model_fidelity)
        restored.set_state(self.get_state())
        memo[id(self)] = restored
        return restored
