"""Repository checks for Darwin's maintained public surface."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "LEGACY.md",
)
PORTUGUESE_MARKERS = re.compile(
    r"\b(?:não|nao|hipótese|hipotese|experimento|resultado|aprendizagem|"
    r"memória|memoria|recompensa|mundo|semente|verdadeira|falhou|passou|"
    r"protocolo|objetivo|avaliação|evidência|refutada|aprovada)\b",
    re.IGNORECASE,
)
MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "ðŸ")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def maintained_documents() -> tuple[Path, ...]:
    research = tuple(sorted((ROOT / "docs" / "v50").glob("*.md")))
    return MAINTAINED_DOCUMENTS + research


def check_english_and_encoding(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if PORTUGUESE_MARKERS.search(line):
            errors.append(
                f"{path.relative_to(ROOT)}:{line_number}: "
                "Portuguese marker on maintained English surface"
            )
        if any(marker in line for marker in MOJIBAKE_MARKERS):
            errors.append(
                f"{path.relative_to(ROOT)}:{line_number}: "
                "possible mojibake"
            )
    return errors


def check_local_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw_target in MARKDOWN_LINK.findall(text):
        target = raw_target.strip().strip("<>")
        if (
            not target
            or target.startswith(("http://", "https://", "mailto:", "#"))
        ):
            continue
        target = unquote(target.split("#", 1)[0])
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(
                f"{path.relative_to(ROOT)}: local link escapes repository: "
                f"{raw_target}"
            )
            continue
        if not resolved.exists():
            errors.append(
                f"{path.relative_to(ROOT)}: missing local link: {raw_target}"
            )
    return errors


def check_runtime_state_not_tracked() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--", "darwin_home"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = {
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    }
    allowed = {"darwin_home/config.example.json"}
    unexpected = sorted(tracked - allowed)
    return [f"runtime state is tracked: {item}" for item in unexpected]


def main() -> int:
    errors: list[str] = []
    for path in maintained_documents():
        text = path.read_text(encoding="utf-8")
        errors.extend(check_english_and_encoding(path, text))
        errors.extend(check_local_links(path, text))
    errors.extend(check_runtime_state_not_tracked())
    if errors:
        print("Maintained-surface checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Maintained-surface checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
