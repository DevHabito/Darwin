from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


GUARDIAN = Path("darwin_wake_word_guardian_v49_34.py")
VOICE = Path("darwin_voice_presence_v49_9.py")
REPAIR = Path("darwin_real_voice_repair_wizard_v49_25.py")


def diagnose(details: bool = False) -> dict[str, Any]:
    guardian = GUARDIAN.read_text(encoding="utf-8") if GUARDIAN.exists() else ""
    voice = VOICE.read_text(encoding="utf-8") if VOICE.exists() else ""
    repair = REPAIR.read_text(encoding="utf-8") if REPAIR.exists() else ""
    checks = {
        "files_exist": all(path.exists() for path in (GUARDIAN, VOICE, REPAIR)),
        "continuous_listener_has_no_console": (
            "creationflags=getattr(subprocess, \"CREATE_NO_WINDOW\", 0)" in voice
        ),
        "voice_probes_have_no_console": (
            repair.count("creationflags=getattr(subprocess, \"CREATE_NO_WINDOW\", 0)") >= 2
        ),
        "idle_presence_exists": "def show_idle_presence" in guardian,
        "sleep_uses_idle_presence": (
            "def sleep_window" in guardian
            and "self.show_idle_presence()" in guardian
        ),
        "idle_window_is_compact": (
            "width, height = 460, 220" in guardian
            and "self.root.resizable(False, False)" in guardian
        ),
        "idle_shows_real_state": (
            "self.core.companion.store.current_state()" in guardian
            and "Microfone ativo" in guardian
            and "RZS" in guardian
        ),
        "awake_restores_full_interface": (
            "self.idle_canvas.place_forget()" in guardian
            and "self.root.geometry(\"940x700\")" in guardian
        ),
        "closing_idle_only_minimizes": (
            "def on_window_close" in guardian
            and "self.root.iconify()" in guardian
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "files": [str(path) for path in (GUARDIAN, VOICE, REPAIR)] if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.44 Professional Idle Presence")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.44 - CHECK PRESENCA OCIOSA PROFISSIONAL")
    print("=" * 68)
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
