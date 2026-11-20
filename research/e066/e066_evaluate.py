"""One-shot registered exact E066 mathematical audit; no stateful Darwin code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from darwin_v50.causal_source_identifiability_lab import exact_audit


def audit(output: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join((str(root / 'src'), env.get('PYTHONPATH', '')))
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(root / 'tests'),
               '-p', 'test_v50_causal_source_identifiability_lab.py', '-v']
    testing = subprocess.run(command, text=True, capture_output=True,
                             env=env, check=False)
    test_count_match = re.search(r'Ran\s+(\d+)\s+tests?', testing.stderr)
    tests = {'passed': testing.returncode == 0,
             'executed': int(test_count_match.group(1)) if test_count_match else None,
             'exit_code': testing.returncode,
             'summary': testing.stderr.splitlines()[-1] if testing.stderr else ''}
    if not tests['passed']:
        return {'experiment': 'E066', 'status': 'FAIL_ENGINEERING_TEST_GATE',
                'checks': {'focused_tests_pass': False}, 'focused_tests': tests,
                'registered_enumeration_started': False}
    report = exact_audit()
    source_paths = (root / 'src/darwin_v50/causal_source_identifiability_lab.py',
                    root / 'tests/test_v50_causal_source_identifiability_lab.py',
                    root / 'research/e066/e066_evaluate.py')
    report['focused_tests'] = tests
    report['source_sha256'] = {
        str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }
    report['registered_enumeration_started'] = True
    report['environment'] = 'standard-library only, no Darwin runtime or database'
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='E066 exact source-identifiability audit')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.output)
    result = audit(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=2,
                               ensure_ascii=True, allow_nan=False) + '\n', encoding='utf-8')
    print('E066:', result['status'])
    print('Report:', path)
    return 0 if result['status'] == 'PASS_NONIDENTIFIABILITY_BOUNDARY_EXACT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
