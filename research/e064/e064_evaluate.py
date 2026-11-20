"""Frozen E064 synthetic development evaluator: observation-only HMM fit.

The generator has hidden-mode information for scoring, but the estimator
receives only three-symbol observed cue sequences. This is NOT an independent
world, a real sensor, or a Darwin kernel integration test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from darwin_v50.noisy_alignment_lab import NoisyAlignmentBelief, NoisyCue
from darwin_v50.reliability_identifiability_lab import estimate_symmetric_sensor

TRUE_H = .08
TRUE_Q = .78
TRAIN_SEEDS = tuple(range(64000,64024))
SCORE_SEEDS = tuple(range(64100,64124))
UNINFORMATIVE_SEEDS = tuple(range(64200,64224))
MEMORYLESS_SEEDS = tuple(range(64300,64324))
TRAIN_STEPS = 4096
SCORE_STEPS = 256


@dataclass(frozen=True)
class GeneratedTrace:
    cues: tuple[int, ...]
    hidden_modes: tuple[int, ...]  # EVALUATOR ONLY; never pass to estimator.


def generate_trace(seed: int, length: int, hazard: float, sensor_correct: float) -> GeneratedTrace:
    rng = random.Random(seed)
    mode = rng.randrange(3)
    cues, hidden = [], []
    for time_step in range(length):
        if time_step and rng.random() < hazard:
            mode = (mode + rng.choice((1,2))) % 3
        if rng.random() < sensor_correct:
            cue = mode
        else:
            cue = (mode + rng.choice((1,2))) % 3
        hidden.append(mode)
        cues.append(cue)
    return GeneratedTrace(tuple(cues),tuple(hidden))


def brier(posterior: tuple[float,float,float], hidden: int) -> float:
    return sum((p - (1.0 if i == hidden else 0.0))**2 for i,p in enumerate(posterior))


def score_trace(seed: int, trace: GeneratedTrace, settings: dict[str,tuple[float,float]]):
    trackers = {
        name: NoisyAlignmentBelief(hazard=h, sensor_correct=q)
        for name,(h,q) in settings.items()
    }
    totals={name:0.0 for name in trackers}
    for time_step,(cue,truth) in enumerate(zip(trace.cues, trace.hidden_modes),1):
        # The posterior is computed before any access to truth for scoring.
        for name,tracker in trackers.items():
            action_id=f'e064:{seed}:action:{time_step}:{name}'
            tracker.register_dispatch(action_id)
            posterior=tracker.observe(NoisyCue(time_step,action_id,cue))
            if not math.isfinite(sum(posterior)) or abs(sum(posterior)-1.0)>1e-12:
                raise AssertionError('invalid E063 posterior')
            if any(not math.isfinite(p) or p < 0 or p > 1 for p in posterior):
                raise AssertionError('invalid E063 posterior component')
            totals[name]+=brier(posterior,truth)
    return {name:totals[name]/len(trace.cues) for name in totals}


def paired_world_ci(world_scores:list[dict[str,float]], left: str,right: str):
    differences=[score[left]-score[right] for score in world_scores]
    rng=random.Random(64990)
    samples=[]
    for _ in range(2000):
        samples.append(sum(rng.choice(differences) for _ in differences)/len(differences))
    samples.sort()
    return {'point':sum(differences)/len(differences),'bootstrap_95':[samples[50],samples[1949]]}


def evaluate(tests_passed: bool):
    positive_train=[generate_trace(seed,TRAIN_STEPS,TRUE_H,TRUE_Q).cues for seed in TRAIN_SEEDS]
    # Estimator input contains ONLY the observed cues, no hidden truth.
    fitted=estimate_symmetric_sensor(positive_train)
    null_sensor=estimate_symmetric_sensor([
        generate_trace(seed,TRAIN_STEPS,TRUE_H,1/3).cues for seed in UNINFORMATIVE_SEEDS
    ])
    null_transition=estimate_symmetric_sensor([
        generate_trace(seed,TRAIN_STEPS,2/3,TRUE_Q).cues for seed in MEMORYLESS_SEEDS
    ])
    permute=(2,0,1)
    permuted=estimate_symmetric_sensor([tuple(permute[c] for c in seq) for seq in positive_train])
    fits=fitted.status=='FITTED' and fitted.hazard is not None and fitted.sensor_correct is not None
    settings={
        'fitted':(fitted.hazard,fitted.sensor_correct) if fits else (0.25,0.55),
        'oracle':(TRUE_H,TRUE_Q),
        'misspecified':(.25,.55),
    }
    # The frozen development protocol requires a complete measurement report;
    # if fitting fails, the fallback *only* makes a score report possible and
    # must NOT be interpreted as an admitted fitted estimate.
    eval_worlds=[score_trace(seed,generate_trace(seed,SCORE_STEPS,TRUE_H,TRUE_Q),settings) for seed in SCORE_SEEDS]
    means={name:sum(world[name] for world in eval_worlds)/len(eval_worlds) for name in settings}
    perm_invariant=(
        fits and permuted.status=='FITTED'
        and abs(fitted.hazard-permuted.hazard)<=1e-12
        and abs(fitted.sensor_correct-permuted.sensor_correct)<=1e-12
    )
    criterion={
        'engineering_tests_pass':tests_passed,
        'cue_only_estimator':True,
        'estimated_parameters_within_registered_tolerance': (
            fits and abs(fitted.hazard-TRUE_H)<=.035 and abs(fitted.sensor_correct-TRUE_Q)<=.035
        ),
        'lag3_residual_below_registered_limit': (
            fits and fitted.lag3_absolute_gap is not None and fitted.lag3_absolute_gap<=.018
        ),
        'both_negative_controls_abstain': (
            null_sensor.status=='UNIDENTIFIABLE' and null_transition.status=='UNIDENTIFIABLE'
        ),
        'permutation_invariance':perm_invariant,
        'fitted_brier_beats_misspecified_by_at_least_0_010': (
            fits and means['misspecified']-means['fitted']>=.010
        ),
        'fitted_brier_within_0_010_of_oracle': (
            fits and means['fitted']-means['oracle']<=.010
        ),
        'all_scored_e063_posteriors_valid_and_causal':True,
        'no_runtime_or_database_side_effects':True,
    }
    output={
        'experiment':'E064',
        'evidence_ceiling':'E1_LOCAL_SYNTHETIC_DEVELOPMENT_ONLY',
        'conclusion':'development_gate_pass' if all(criterion.values()) else 'development_gate_fail',
        'research_claim_registered':False,
        'model_assumptions':'stationary 3-mode symmetric Markov chain; iid emissions conditional on latent mode',
        'registered_parameters':{'hazard':TRUE_H,'sensor_correct':TRUE_Q},
        'train_seeds':list(TRAIN_SEEDS),'score_seeds':list(SCORE_SEEDS),
        'null_sensor_seeds':list(UNINFORMATIVE_SEEDS),
        'memoryless_seeds':list(MEMORYLESS_SEEDS),
        'train_steps_per_world':TRAIN_STEPS,'score_steps_per_world':SCORE_STEPS,
        'held_out_observation_count':len(SCORE_SEEDS)*SCORE_STEPS,
        'fitted':asdict(fitted),
        'null_sensor':asdict(null_sensor),
        'null_transition':asdict(null_transition),
        'permuted':asdict(permuted),
        'mean_brier':means,
        'paired_world_brier_delta':{
            'fitted_minus_oracle':paired_world_ci(eval_worlds,'fitted','oracle'),
            'misspecified_minus_fitted':paired_world_ci(eval_worlds,'misspecified','fitted'),
        },
        'criteria':criterion,
        'limitations':[
            'No external or independent evaluator; all worlds are synthetic.',
            'Fit uses pooled historical cues and fixed stationary symmetric assumptions.',
            'A failed fit is not replaced by a learned model; fallback used only to report non-admitted scores.',
            'No H50-L registration, memory, kernel, action-authority or real sensor.',
        ],
    }
    return output


def main():
    parser=argparse.ArgumentParser(description='Darwin E064 frozen label-free development evaluator')
    parser.add_argument('--output',required=True,help='local JSON evidence path')
    args=parser.parse_args()
    # Test admission before any registered synthetic samples are generated.
    env=dict(os.environ)
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[2]/'src')
    test=subprocess.run([
        sys.executable,'-m','unittest','discover',
        '-s',str(Path(__file__).resolve().parents[2]/'tests'),
        '-p','test_v50_reliability_identifiability_lab.py','-q',
    ],capture_output=True,text=True,env=env)
    if test.returncode!=0:
        raise SystemExit('E064 engineering tests failed before evaluation:\n'+test.stderr)
    report=evaluate(tests_passed=True)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print('E064 result:',report['conclusion'])
    print('criteria:',sum(report['criteria'].values()),'/',len(report['criteria']))
    print('h,q:',report['fitted']['hazard'],report['fitted']['sensor_correct'])
    print('Brier:',report['mean_brier'])
    print('evidence:',path)
    return 0 if all(report['criteria'].values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
