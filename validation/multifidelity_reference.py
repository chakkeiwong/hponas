"""Independent rational reference for retained quadratic streaming traces."""
from collections import Counter
from fractions import Fraction as Q
import math


def close(actual, expected):
    if not math.isfinite(actual) or not math.isclose(actual, float(expected), rel_tol=1e-10, abs_tol=1e-13):
        raise ValueError(f"Independent value differs: {actual} != {expected}")


def value(index, step):
    eta = Q(index, 40)
    return (1-eta)**(2*step)/100 + (1-3*eta)**(2*step)


def checkpoint(state, index, step):
    if state["iterations"] != step or state["gradient_steps"] != step or state["eta"] != index/40:
        raise ValueError("Checkpoint identity/accounting differs")
    eta = Q(index,40)
    a, b = (1-eta)**step/10, (1-3*eta)**step
    close(state["state"][0], Q(3,5)*a-Q(4,5)*b)
    close(state["state"][1], Q(4,5)*a+Q(3,5)*b)


def median(values):
    values = sorted(values)
    n = len(values)
    return values[n//2] if n % 2 else (values[n//2-1]+values[n//2])/2


def verify(raw):
    summary = raw["summary"]
    trials = {row["trial"]["trial_id"]: row["trial"] for row in raw["endpoints"]}
    costs = Counter()
    for update in raw["updates"]:
        ident, index, step = update["trial_id"], update["eta_index"], update["step"]
        if trials[ident]["config"]["values"]["eta_index"] != index:
            raise ValueError("Physical update has changed configuration")
        close(update["value"], value(index,step))
        checkpoint(update["checkpoint"], index,step)
        costs[ident] += 1
    for row in raw["endpoints"]:
        trial, result = row["trial"], row["result"]
        close(result["cost"], costs[trial["trial_id"]])
    close(summary["physical_updates"], sum(costs.values()))
    close(summary["accounted_cost"], sum(costs.values()))
    if summary["evaluations"] != len(trials):
        raise ValueError("Evaluation count differs")

    roots, active, terminal, histories, seen_steps = {}, {}, {}, {}, {}
    populations = {r: {} for r in ([8] if summary["full_reference"] else [1,2,4,8])}
    count = Counter()

    def report(root, step):
        if root in terminal:
            return "stop"
        if step in populations:
            populations[step][root] = value(roots[root], step)
            if step == 8:
                active[root] = (step, "stopped")
                return "stop"
            active[root] = (step, "paused")
            return "pause"
        return "continue"

    for event in raw["events"]:
        kind, ident, data = event["kind"], event["trial_id"], event["data"]
        count[kind] += 1
        if kind == "suggest":
            if ident in roots:
                raise ValueError("Root suggestion was repeated")
            roots[ident] = data["config"]["eta_index"]
            histories[ident] = {}
        elif kind == "promotion_round":
            expected = []
            for rung in sorted(populations, reverse=True):
                pop = populations[rung]
                if rung == 8 or len(pop) < 2:
                    continue
                # eta=2 gives the exact linear median quantile. Previously
                # promoted rows remain in the population defining its cutoff.
                cutoff = median(list(pop.values()))
                eligible = [root for root in sorted(pop, key=pop.get)
                            if pop[root] <= cutoff and active.get(root) == (rung,"paused") and root not in terminal]
                if eligible:
                    root = eligible[0]
                    expected = [[root, 2*rung]]
                    active[root] = (2*rung,"active")
                    break
            if data["promotions"] != expected:
                raise ValueError("Promotion trace differs from exact population/median rule")
        elif kind == "promote":
            trial = trials[ident]
            root, previous = data["root"], int(data["from_fidelity"])
            if data["to_fidelity"] != 2*previous or active[root] != (2*previous,"active"):
                raise ValueError("Promotion target differs")
            if data["continuation"] == "resume":
                if data["resume_from"] != previous or trial["resume_from"] != previous:
                    raise ValueError("Promotion did not resume from previous rung")
                checkpoint(data["checkpoint"], roots[root], previous)
            elif data["resume_from"] != 0 or data["checkpoint"] is not None:
                raise ValueError("Restart reused a parent checkpoint")
        elif kind == "progress":
            root, step = data["root"], int(data["step"])
            index = roots[root]
            close(data["value"], value(index, step))
            close(data["normalized_value"], value(index, step))
            checkpoint(data["checkpoint"], index, step)
            trial = trials[ident]
            close(data["cost"], step-trial["resume_from"])
            evidence_key = (ident, step)
            repeat = evidence_key in seen_steps
            parent = trial["parent_trial_id"]
            prefix = parent is not None and step <= trials[parent]["fidelity"]
            if repeat or prefix:
                if data["scheduler_applied"] or data["scheduler_decision"] is not None:
                    raise ValueError("Repeated physical work counted as fresh scheduler evidence")
                expected_control = seen_steps[evidence_key] if repeat else "continue"
            else:
                histories[root][step] = value(index,step)
                references = [sum(histories[r][s] for s in range(1,step+1))/step
                              for r in terminal if terminal[r] == "completed" and r != root
                              and all(s in histories[r] for s in range(1,step+1))]
                current = sum(histories[root][s] for s in range(1,step+1))/step
                should_stop = summary["median"] and len(references)>=5 and current>median(references)
                if should_stop:
                    expected = "stop"
                    terminal[root] = "pruned"
                    active[root] = (-1,"stopped")
                else:
                    expected = report(root,step)
                if not data["scheduler_applied"] or data["scheduler_decision"] != expected:
                    raise ValueError("Progress decision differs from exact streamed reference")
                expected_control = "continue" if expected == "stop" and step == trial["fidelity"] and terminal.get(root) != "pruned" else expected
            if data["control"]["action"] != expected_control:
                raise ValueError("Executor control differs from declared scheduler decision")
            seen_steps.setdefault(evidence_key, expected_control)
        elif kind == "report":
            root, step = data["root"], int(data["fidelity"])
            close(data["value"], value(roots[root], step))
            expected = "stop" if step == 8 else "pause"
            if data["decision"] != expected:
                raise ValueError("Endpoint duplicate report changed its rung decision")
        elif kind == "finish":
            root, status = data["root"], data["status"]
            if status not in ("completed", "pruned"):
                raise ValueError("Unexpected terminal status")
            if status == "completed" and 8 not in histories[root]:
                raise ValueError("Completed label lacks full-fidelity evidence")
            if root in terminal and terminal[root] != status:
                raise ValueError("Terminal status differs")
            terminal[root] = status
        elif kind in ("observe", "interrupted", "resume_pending"):
            pass
        else:
            raise ValueError("Unrecognized event kind: " + kind)
    full = sorted(roots[r] for r, status in terminal.items() if status == "completed")
    if full != summary["full_fidelity_indices"]:
        raise ValueError("Retained full-fidelity summary differs from trace")
    top3 = sorted(range(1,26), key=lambda i:value(i,8))[:3]
    if (summary["exact_top3_indices"] != top3 or summary["exact_optimal_index"] != top3[0]
            or summary["optimal_reached_full_fidelity"] != (top3[0] in full)):
        raise ValueError("Known optimum/cull summary differs")
    return {"name": summary["name"], "events": dict(count), "physical_updates": sum(costs.values()),
            "accounting_verified": True, "reference_decisions_verified": True}

