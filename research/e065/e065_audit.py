"""E065 preregistered out-of-model audit for E064 reliability inversion."""
from __future__ import annotations

import argparse
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

H, Q, RHO = .08, .78, .60
TRAIN = range(65000, 65024)
SCORE = range(65100, 65124)
CONTROL = range(65200, 65224)


@dataclass(frozen=True)
class Trace:
    cues: tuple[int, ...]
    hidden: tuple[int, ...]  # evaluator only


def generate_trace(seed: int, size: int, rho: float) -> Trace:
    if not isinstance(seed, int) or size < 4 or not 0 <= rho < 1:
        raise ValueError('invalid generator parameters')
    rng = random.Random(seed)
    rotation = rng.randrange(3)
    offset = None
    cues, hidden = [], []
    for t in range(size):
        if t and rng.random() < H:
            rotation = (rotation + rng.choice((1,2))) % 3
        if offset is None or rng.random() >= rho:
            u = rng.random()
            offset = 0 if u < Q else (1 if u < (1+Q)/2 else 2)
        cues.append((rotation+offset) % 3)
        hidden.append(rotation)
    return Trace(tuple(cues), tuple(hidden))


def brier(p, hidden):
    return sum((v - float(j == hidden))**2 for j,v in enumerate(p))


def score_trace(seed: int, trace: Trace, fitted_h: float, fitted_q: float) -> dict[str,float]:
    settings={'fitted':(fitted_h,fitted_q),'iid_oracle_parameters':(H,Q)}
    trackers={k:NoisyAlignmentBelief(hazard=h,sensor_correct=q) for k,(h,q) in settings.items()}
    sums={k:0.0 for k in (*trackers,'last_cue')}
    for index, (cue, truth) in enumerate(zip(trace.cues,trace.hidden),1):
        for name, tracker in trackers.items():
            action_id=f'e065:{seed}:{index}:{name}'
            tracker.register_dispatch(action_id)
            p=tracker.observe(NoisyCue(index,action_id,cue))
            if any(not math.isfinite(x) or x < 0 or x > 1 for x in p) or abs(sum(p)-1)>1e-12:
                raise AssertionError('E063 invalid posterior')
            sums[name]+=brier(p,truth)
        last=tuple(Q if mode==cue else (1-Q)/2 for mode in range(3))
        sums['last_cue']+=brier(last,truth)
    return {name:value/len(trace.cues) for name,value in sums.items()}


def audit() -> dict:
    correlated_cues=[generate_trace(seed,4096,RHO).cues for seed in TRAIN]
    independent_cues=[generate_trace(seed,4096,0.0).cues for seed in CONTROL]
    correlated=estimate_symmetric_sensor(correlated_cues)
    control=estimate_symmetric_sensor(independent_cues)
    fitted=correlated.status=='FITTED'
    scores=[score_trace(seed,generate_trace(seed,256,RHO),
             correlated.hazard if fitted else .25,
             correlated.sensor_correct if fitted else .55) for seed in SCORE]
    means={name:sum(world[name] for world in scores)/len(scores) for name in scores[0]}
    risk=(fitted and correlated.sensor_correct>=.93 and
          correlated.lag3_absolute_gap is not None and correlated.lag3_absolute_gap<=.018)
    return {
        'experiment':'E065','status':'adversarial_development_audit_only',
        'evidence_level':'E1_LOCAL_ADVERSARIAL_DEVELOPMENT',
        'synthetic_assumptions':{'h':H,'marginal_sensor_correct':Q,'offset_persistence':RHO},
        'training_seeds':list(TRAIN),'scoring_seeds':list(SCORE),
        'independent_control_seeds':list(CONTROL),
        'training_steps_per_world':4096,'scoring_steps_per_world':256,
        'correlated_fit':asdict(correlated),'independent_control_fit':asdict(control),
        'mean_brier':means,
        'registered_counterexample_observed':bool(risk),
        'counterexample_conditions':{
            'correlated_fit_exists':fitted,
            'estimated_q_at_least_0_93':bool(fitted and correlated.sensor_correct>=.93),
            'lag3_gap_at_most_0_018':bool(fitted and correlated.lag3_absolute_gap<=.018),
        },
        'constraints':{
            'estimator_changed':False,'e063_changed':False,'kernel_changed':False,
            'hidden_state_used_for_fit':False,'real_sensor_tested':False,
        },
        'interpretation':'Deliberately chosen model misspecification; not independent confirmation or a new Darwin H50-L capability.',
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    env=dict(os.environ)
    env['PYTHONPATH']=str(root/'src')
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(root/'tests'),
         '-p','test_e065_audit.py','-q'],capture_output=True,text=True,env=env)
    if result.returncode:
        raise RuntimeError('E065 tests failed; registered seeds not evaluated:\n'+result.stderr)
    report=audit()
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('E065 registered counterexample:',report['registered_counterexample_observed'])
    print('E065 estimated parameters:',report['correlated_fit']['hazard'],report['correlated_fit']['sensor_correct'])
    print('E065 lag3 gap:',report['correlated_fit']['equality_rates'][2],report['correlated_fit']['predicted_lag3'])
    print('E065 Brier:',report['mean_brier'])
    print('Evidence:',path)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
