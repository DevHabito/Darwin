"""Exact E066 reference: indistinguishable latent world/sensor changes.

Mathematical laboratory only. No Darwin kernel, database, effects or model
authority is imported. All transition probabilities are exact Fractions.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Mapping

MODES = (0, 1, 2)
A = (Fraction(1, 8), Fraction(0))
B = (Fraction(0), Fraction(1, 8))
C = (Fraction(1, 10), Fraction(1, 6))
D = (Fraction(29, 120), Fraction(0))
WORLDS = {"A_world_only": A, "B_sensor_only": B,
          "C_mixed": C, "D_world_only": D}


def _hazard(value: Fraction | int) -> Fraction:
    if type(value) not in (Fraction, int):
        raise ValueError("hazard must be an exact rational number")
    number = Fraction(value)
    if not 0 <= number <= 1:
        raise ValueError("hazard outside [0, 1]")
    return number


def _history(values: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if type(values) not in (tuple, list) or not values:
        raise ValueError("nonempty cue sequence required")
    if any(type(v) is not int or v not in MODES for v in values):
        raise ValueError("cue must be an exact integer in {0,1,2}")
    return tuple(values)


def _anchors(values: Mapping[int, int] | None, length: int) -> dict[int, int]:
    if values is None:
        return {}
    if type(values) is not dict:
        raise ValueError("anchor map must be a plain dictionary")
    if any(type(index) is not int or not 0 <= index < length
           or type(mode) is not int or mode not in MODES
           for index, mode in values.items()):
        raise ValueError("anchor index or mode is invalid")
    return dict(values)


def kernel(hazard: Fraction | int) -> tuple[Fraction, Fraction, Fraction]:
    h = _hazard(hazard)
    return 1 - h, h / 2, h / 2


def effective_hazard(world_h: Fraction | int,
                     sensor_h: Fraction | int) -> Fraction:
    h, s = _hazard(world_h), _hazard(sensor_h)
    return h + s - Fraction(3, 2) * h * s


def convolution(world_h: Fraction | int,
                sensor_h: Fraction | int) -> tuple[Fraction, Fraction, Fraction]:
    """Independent convolution of the two random-walk increment kernels."""
    world, sensor = kernel(world_h), kernel(sensor_h)
    return tuple(sum((world[u] * sensor[(mode - u) % 3] for u in MODES),
                     Fraction(0)) for mode in MODES)


def observable_likelihood(cues: tuple[int, ...] | list[int],
                          world_h: Fraction | int,
                          sensor_h: Fraction | int) -> Fraction:
    """Probability of exactly this observed trace; never inspect latent state."""
    history = _history(cues)
    steps = kernel(effective_hazard(world_h, sensor_h))
    probability = Fraction(1, 3)
    for before, after in zip(history, history[1:]):
        probability *= steps[(after - before) % 3]
    return probability


def joint_likelihood(cues: tuple[int, ...] | list[int],
                     world_h: Fraction | int,
                     sensor_h: Fraction | int,
                     *, anchors: Mapping[int, int] | None = None) -> Fraction:
    """Independent 9-state forward recursion; optional trusted R_t readings.

    This is an evaluator reference, not an observation-only inference API.
    """
    history = _history(cues)
    constraints = _anchors(anchors, len(history))
    world_step, sensor_step = kernel(world_h), kernel(sensor_h)
    distribution = {(mode, 0): Fraction(1, 3)
                    for mode in MODES
                    if mode == history[0] and
                    (0 not in constraints or constraints[0] == mode)}
    for time, observed in enumerate(history[1:], start=1):
        updated: dict[tuple[int, int], Fraction] = {}
        for (world, sensor), mass in distribution.items():
            for world_delta in MODES:
                new_world = (world + world_delta) % 3
                if time in constraints and constraints[time] != new_world:
                    continue
                for sensor_delta in MODES:
                    new_sensor = (sensor + sensor_delta) % 3
                    if (new_world + new_sensor) % 3 != observed:
                        continue
                    state = (new_world, new_sensor)
                    updated[state] = (updated.get(state, Fraction(0))
                                      + mass * world_step[world_delta]
                                      * sensor_step[sensor_delta])
        distribution = updated
    return sum(distribution.values(), Fraction(0))


def paired_witness(cues: tuple[int, ...] | list[int]) -> dict[str, object]:
    """Two incompatible hidden histories with the *same* visible readings."""
    history = _history(cues)
    initial = history[0]
    world_only = {"R": history, "O": (0,) * len(history)}
    sensor_only = {"R": (initial,) * len(history),
                   "O": tuple((cue - initial) % 3 for cue in history)}
    for hidden in (world_only, sensor_only):
        assert tuple((r + o) % 3 for r, o in zip(hidden["R"], hidden["O"])) == history
    changes = sum(a != b for a, b in zip(history, history[1:]))
    return {"observed": history, "world_only": world_only,
            "sensor_only": sensor_only, "observed_changes": changes}


def exact_audit() -> dict[str, object]:
    """Frozen 243-trace audit; call only after implementation is committed."""
    traces = list(product(MODES, repeat=5))
    likelihoods: dict[str, list[Fraction]] = {name: [] for name in WORLDS}
    all_joint_match = True
    for trace in traces:
        for name, (h, s) in WORLDS.items():
            marginal = observable_likelihood(trace, h, s)
            joint = joint_likelihood(trace, h, s)
            all_joint_match = all_joint_match and marginal == joint
            likelihoods[name].append(marginal)
    pairs = []
    for a, b in (("A_world_only", "B_sensor_only"),
                 ("C_mixed", "D_world_only")):
        left, right = likelihoods[a], likelihoods[b]
        tv = sum((abs(x-y) for x, y in zip(left, right)), Fraction(0)) / 2
        bayes_accuracy = sum((max(x, y) for x, y in zip(left, right)),
                             Fraction(0)) / 2
        pairs.append({"pair": f"{a} vs {b}",
                      "effective_hazard": str(effective_hazard(*WORLDS[a])),
                      "exact_total_variation": str(tv),
                      "equal_prior_best_accuracy": str(bayes_accuracy),
                      "trace_likelihoods_equal": all(x == y for x, y in zip(left, right))})
    totals = {name: str(sum(values, Fraction(0)))
              for name, values in likelihoods.items()}
    anchor_trace = (0, 1, 1, 2)
    a_anchor = joint_likelihood(anchor_trace, *A, anchors={2: 0})
    b_anchor = joint_likelihood(anchor_trace, *B, anchors={2: 0})
    witness = paired_witness((0, 1, 2, 1, 1, 0))
    checks = {
        "243_traces_enumerated": len(traces) == 243,
        "all_independent_joint_references_match": all_joint_match,
        "all_world_likelihoods_normalized_exactly": all(v == "1" for v in totals.values()),
        "both_pairs_have_exactly_zero_total_variation": all(p["exact_total_variation"] == "0" for p in pairs),
        "both_pairs_equal_likelihood_on_every_trace": all(p["trace_likelihoods_equal"] for p in pairs),
        "both_pairs_equal_prior_ceiling_is_half": all(p["equal_prior_best_accuracy"] == "1/2" for p in pairs),
        "independent_increment_convolution_exact": all(
            convolution(h, s) == kernel(effective_hazard(h, s))
            for h, s in WORLDS.values()),
        "different_hidden_causes_share_visible_trace": (
            witness["observed_changes"] > 0
            and witness["world_only"]["R"] != witness["sensor_only"]["R"]),
        "trusted_world_anchor_separates_pair": a_anchor == 0 and b_anchor > 0,
    }
    return {
        "experiment": "E066",
        "status": "PASS_NONIDENTIFIABILITY_BOUNDARY_EXACT" if all(checks.values())
                  else "FAIL_REGISTERED_EXACT_AUDIT",
        "evidence": "exact finite mathematical audit; not a Darwin learning capability",
        "history_length": 5,
        "enumerated_histories": len(traces),
        "checks": checks,
        "pairs": pairs,
        "total_probability": totals,
        "anchor": {"history": anchor_trace, "trusted_R2": 0,
                   "A_joint_probability": str(a_anchor),
                   "B_joint_probability": str(b_anchor)},
        "paired_witness": witness,
        "limitations": ("model-class nonidentifiability under hidden additive "
                        "sensor random walk; no real sensor, kernel, or inference"),
    }
