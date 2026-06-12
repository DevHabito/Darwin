from __future__ import annotations

"""
DARWIN v49.10 - First Words Nursery

Objetivo:
Transformar voz em experiencia inicial, como uma crianca aprendendo
as primeiras palavras. Darwin nao tenta entender tudo. Ele escuta
um vocabulario pequeno, cria nos de experiencia, reforca repeticoes
e liga som -> palavra -> significado relacional.

Uso:
    py darwin_first_words_v49_10.py
    py darwin_first_words_v49_10.py --self-test --details

Limite honesto:
Sem reconhecedor de fala instalado no Windows, Python stdlib nao tem
como transcrever microfone. Nesse caso a janela fica viva e orienta
instalar o recurso de fala do Windows; o self-test continua validando
o cerebro de primeiras palavras.
"""

import argparse
import json
import math
import queue
import random
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

FW_SESSIONS = "voice_first_word_sessions_v49_10"
FW_ATTEMPTS = "voice_first_word_attempts_v49_10"
FW_NODES = "voice_first_word_nodes_v49_10"
FW_MEANINGS = "voice_word_meanings_v49_10"
FW_LINKS = "voice_phoneme_links_v49_10"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def normalize(text: str) -> str:
    lowered = text.lower().strip()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def syllables(word: str) -> list[str]:
    w = normalize(word)
    if w in {"mamae", "papai"}:
        return [w[:2], w[2:]]
    if len(w) <= 3:
        return [w]
    out = []
    current = ""
    vowels = "aeiou"
    for ch in w:
        current += ch
        if ch in vowels and len(current) >= 2:
            out.append(current)
            current = ""
    if current:
        out.append(current)
    return out or [w]


@dataclass(frozen=True)
class FirstWord:
    canonical: str
    variants: tuple[str, ...]
    meaning_key: str
    relational_meaning: str
    response: str
    affect_weight: float


@dataclass
class WordState:
    word: FirstWord
    exposure_count: int = 0
    success_count: int = 0
    low_confidence_count: int = 0
    meaning_confidence: float = 0.08
    sound_confidence: float = 0.08


@dataclass
class WordExperience:
    node_id: str
    word: str
    recognized_text: str
    confidence: float
    meaning_key: str
    meaning_confidence_before: float
    meaning_confidence_after: float
    sound_confidence_before: float
    sound_confidence_after: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    response: str


def first_words() -> list[FirstWord]:
    return [
        FirstWord("mamae", ("mamae", "mamãe", "mama"), "caregiver_mother", "cuidado, acolhimento e primeira referencia afetiva", "Eu ouvi mamae. Vou guardar esse som como cuidado e presenca.", 0.96),
        FirstWord("papai", ("papai", "papa"), "caregiver_father", "proteção, presença e chamada familiar", "Eu ouvi papai. Vou ligar esse som a presenca e protecao.", 0.94),
        FirstWord("felipe", ("felipe",), "primary_person", "a pessoa que esta ensinando Darwin", "Eu ouvi Felipe. Este som aponta para voce, meu professor principal.", 0.98),
        FirstWord("darwin", ("darwin", "dariwin", "dorwin"), "self_name", "nome proprio do sistema Darwin", "Eu ouvi Darwin. Esse som aponta para mim.", 0.90),
        FirstWord("oi", ("oi", "ola", "olá"), "greeting", "abertura de contato", "Eu ouvi oi. Isso abre contato entre nos.", 0.68),
        FirstWord("sim", ("sim",), "affirmation", "aceitacao ou confirmacao", "Eu ouvi sim. Vou associar isso a confirmacao.", 0.58),
        FirstWord("nao", ("nao", "não"), "negation", "limite, recusa ou correcao", "Eu ouvi nao. Vou associar isso a limite e correcao.", 0.72),
        FirstWord("ajuda", ("ajuda", "me ajuda"), "request_help", "pedido de suporte", "Eu ouvi ajuda. Vou associar esse som a necessidade de suporte.", 0.82),
        FirstWord("agua", ("agua", "água"), "need_water", "necessidade basica simbolica", "Eu ouvi agua. Vou guardar como necessidade basica.", 0.66),
        FirstWord("brincar", ("brincar", "brinca"), "play", "exploracao segura e aprendizagem por jogo", "Eu ouvi brincar. Isso combina com aprender explorando.", 0.62),
    ]


class FirstWordsStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = db_path
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {FW_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    recognizer_culture TEXT NOT NULL DEFAULT '',
                    recognizer_name TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {FW_ATTEMPTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL UNIQUE,
                    event_kind TEXT NOT NULL,
                    raw_text TEXT NOT NULL DEFAULT '',
                    canonical_word TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {FW_NODES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL UNIQUE,
                    canonical_word TEXT NOT NULL,
                    recognized_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    meaning_key TEXT NOT NULL,
                    syllables_json TEXT NOT NULL DEFAULT '[]',
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    meaning_confidence_before REAL NOT NULL DEFAULT 0.0,
                    meaning_confidence_after REAL NOT NULL DEFAULT 0.0,
                    sound_confidence_before REAL NOT NULL DEFAULT 0.0,
                    sound_confidence_after REAL NOT NULL DEFAULT 0.0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    response_text TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {FW_MEANINGS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    canonical_word TEXT NOT NULL,
                    meaning_key TEXT NOT NULL,
                    relational_meaning TEXT NOT NULL,
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    meaning_confidence REAL NOT NULL DEFAULT 0.0,
                    sound_confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(session_id, canonical_word)
                );

                CREATE TABLE IF NOT EXISTS {FW_LINKS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    from_unit TEXT NOT NULL,
                    to_unit TEXT NOT NULL,
                    link_kind TEXT NOT NULL,
                    strength REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    module TEXT NOT NULL,
                    context TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL
                );
                """
            )
            conn.commit()

    def log_session(self, session_id: str, phase: str, *, mode: str = "", culture: str = "", name: str = "", payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {FW_SESSIONS} (
                    timestamp, session_id, phase, recognizer_culture,
                    recognizer_name, mode, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, culture, name, mode, js(payload or {})),
            )
            conn.commit()

    def log_attempt(self, session_id: str, attempt_id: str, event_kind: str, raw_text: str, canonical: str, confidence: float, accepted: bool, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {FW_ATTEMPTS} (
                    timestamp, session_id, attempt_id, event_kind, raw_text,
                    canonical_word, confidence, accepted, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, attempt_id, event_kind, raw_text, canonical, confidence, 1 if accepted else 0, js(payload or {})),
            )
            conn.commit()

    def log_experience(self, session_id: str, experience: WordExperience, exposure_count: int, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {FW_NODES} (
                    timestamp, session_id, node_id, canonical_word, recognized_text,
                    confidence, meaning_key, syllables_json, exposure_count,
                    meaning_confidence_before, meaning_confidence_after,
                    sound_confidence_before, sound_confidence_after,
                    rzs_decision, sigma_before, sigma_after, response_text,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    experience.node_id,
                    experience.word,
                    experience.recognized_text,
                    experience.confidence,
                    experience.meaning_key,
                    js(syllables(experience.word)),
                    exposure_count,
                    experience.meaning_confidence_before,
                    experience.meaning_confidence_after,
                    experience.sound_confidence_before,
                    experience.sound_confidence_after,
                    experience.rzs_decision,
                    experience.sigma_before,
                    experience.sigma_after,
                    experience.response,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def upsert_meaning(self, session_id: str, state: WordState) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {FW_MEANINGS} (
                    timestamp, session_id, canonical_word, meaning_key,
                    relational_meaning, exposure_count, success_count,
                    meaning_confidence, sound_confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, canonical_word) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    exposure_count=excluded.exposure_count,
                    success_count=excluded.success_count,
                    meaning_confidence=excluded.meaning_confidence,
                    sound_confidence=excluded.sound_confidence,
                    payload_json=excluded.payload_json
                """,
                (
                    now(),
                    session_id,
                    state.word.canonical,
                    state.word.meaning_key,
                    state.word.relational_meaning,
                    state.exposure_count,
                    state.success_count,
                    state.meaning_confidence,
                    state.sound_confidence,
                    js({"variants": list(state.word.variants), "affect_weight": state.word.affect_weight}),
                ),
            )
            conn.commit()

    def log_link(self, session_id: str, node_id: str, from_unit: str, to_unit: str, link_kind: str, strength: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {FW_LINKS} (
                    timestamp, session_id, node_id, from_unit, to_unit,
                    link_kind, strength, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, node_id, from_unit, to_unit, link_kind, clamp(strength), js(payload or {})),
            )
            conn.commit()

    def write_episode(self, context: str, action: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), "darwin_first_words_v49_10", context, action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()

    def write_memory(self, key: str, content: str, confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    confidence=max(semantic_memory.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_first_words_v49_10", now()),
            )
            conn.commit()


class FirstWordsBrain:
    def __init__(self, store: FirstWordsStore | None = None, seed: int = 4910, mode: str = "gui") -> None:
        self.store = store or FirstWordsStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.session_id = f"V4910-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.turn = 0
        self.states = {w.canonical: WordState(w) for w in first_words()}
        self.variant_map: dict[str, str] = {}
        for word in first_words():
            for variant in word.variants:
                self.variant_map[normalize(variant)] = word.canonical
        self.store.log_session(self.session_id, "first_words_start", mode=mode, payload={"words": sorted(self.states)})

    def canonicalize(self, raw_text: str) -> str:
        text = normalize(raw_text)
        if text in self.variant_map:
            return self.variant_map[text]
        for variant, canonical in self.variant_map.items():
            if variant in text:
                return canonical
        return ""

    def rzs_input(self, state: WordState, confidence: float) -> RZSInput:
        novelty = clamp(1.0 - state.sound_confidence)
        conflict = clamp(0.25 + max(0.0, 0.60 - confidence))
        return RZSInput(
            bandwidth=4.2 + state.meaning_confidence,
            info_self=0.32,
            info_external=0.44,
            task_info=0.50 + novelty * 0.32,
            novelty=novelty,
            conflict=conflict,
            latency=0.78 + conflict * 0.42,
            energy=0.82,
            memory_pressure=clamp(1.0 - state.meaning_confidence),
            replay_gap=0.30,
        )

    def learn(self, raw_text: str, confidence: float = 1.0, source: str = "voice") -> WordExperience | None:
        self.turn += 1
        attempt_id = f"attempt:{self.session_id}:{self.turn:04d}"
        canonical = self.canonicalize(raw_text)
        accepted = bool(canonical) and confidence >= 0.22
        self.store.log_attempt(
            self.session_id,
            attempt_id,
            "word_heard" if accepted else "unmapped_sound",
            raw_text,
            canonical,
            confidence,
            accepted,
            {"source": source},
        )
        if not accepted:
            self.store.write_episode(
                f"first_words:{self.session_id}:{attempt_id}",
                "listen_uncertain_sound",
                raw_text,
                "A sound without stable mapping should be held as uncertainty, not forced into meaning.",
                0.0,
                0.0,
            )
            return None
        state = self.states[canonical]
        x = self.rzs_input(state, confidence)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        meaning_before = state.meaning_confidence
        sound_before = state.sound_confidence
        state.exposure_count += 1
        if confidence >= 0.55:
            state.success_count += 1
            reinforcement = 0.16 + state.word.affect_weight * 0.08
        else:
            state.low_confidence_count += 1
            reinforcement = 0.06
        repetition_bonus = min(0.12, state.exposure_count * 0.018)
        state.sound_confidence = clamp(state.sound_confidence + reinforcement * confidence + repetition_bonus)
        state.meaning_confidence = clamp(state.meaning_confidence + reinforcement * 0.72 + repetition_bonus * 0.85)
        if assessment.decision in {"replay_memory", "narrow_focus"}:
            state.meaning_confidence = clamp(state.meaning_confidence + 0.035)
        self.store.upsert_meaning(self.session_id, state)
        response = state.word.response
        if state.exposure_count >= 3:
            response += f" Ja ouvi {state.word.canonical} {state.exposure_count} vezes; o significado esta ficando mais firme."
        node_id = f"firstword:{self.session_id}:{self.turn:04d}:{state.word.canonical}"
        exp = WordExperience(
            node_id=node_id,
            word=state.word.canonical,
            recognized_text=raw_text,
            confidence=confidence,
            meaning_key=state.word.meaning_key,
            meaning_confidence_before=meaning_before,
            meaning_confidence_after=state.meaning_confidence,
            sound_confidence_before=sound_before,
            sound_confidence_after=state.sound_confidence,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            response=response,
        )
        self.store.log_experience(
            self.session_id,
            exp,
            state.exposure_count,
            {
                "relational_meaning": state.word.relational_meaning,
                "attempt_id": attempt_id,
                "source": source,
            },
        )
        previous = "start"
        for idx, part in enumerate(syllables(state.word.canonical)):
            self.store.log_link(
                self.session_id,
                node_id,
                previous,
                part,
                "sound_sequence",
                0.42 + idx * 0.06,
                {"word": state.word.canonical},
            )
            previous = part
        self.store.log_link(
            self.session_id,
            node_id,
            state.word.canonical,
            state.word.meaning_key,
            "word_to_relational_meaning",
            state.meaning_confidence,
            {"meaning": state.word.relational_meaning},
        )
        self.store.write_memory(
            f"first_words_v49_10:{state.word.canonical}",
            (
                f"First word {state.word.canonical}: meaning={state.word.relational_meaning}; "
                f"exposures={state.exposure_count}; sound_confidence={state.sound_confidence:.3f}; "
                f"meaning_confidence={state.meaning_confidence:.3f}."
            ),
            state.meaning_confidence,
        )
        self.store.write_episode(
            f"first_words:{self.session_id}:{node_id}",
            "learn_first_word",
            f"{state.word.canonical}:{confidence:.2f}",
            f"Sound {state.word.canonical} is linked to {state.word.relational_meaning}.",
            assessment.sigma,
            sigma_after,
        )
        return exp

    def complete(self) -> dict[str, Any]:
        learned = [s for s in self.states.values() if s.exposure_count > 0]
        payload = {
            "session_complete": True,
            "learned_words": [s.word.canonical for s in learned],
            "learned_count": len(learned),
            "total_exposures": sum(s.exposure_count for s in self.states.values()),
            "mean_meaning_confidence": sum(s.meaning_confidence for s in learned) / max(1, len(learned)),
        }
        self.store.log_session(self.session_id, "first_words_complete", mode=self.mode, payload=payload)
        return {"session_id": self.session_id, **payload}


@dataclass
class RecognizedWord:
    text: str
    confidence: float
    culture: str


class FirstWordListener:
    def __init__(
        self,
        words: list[FirstWord],
        on_ready: Callable[[str, str], None],
        on_result: Callable[[RecognizedWord], None],
        on_low: Callable[[RecognizedWord], None],
        on_missing: Callable[[str], None],
        on_error: Callable[[str], None],
        *,
        culture: str = "pt-BR",
        min_confidence: float = 0.18,
    ) -> None:
        self.words = words
        self.on_ready = on_ready
        self.on_result = on_result
        self.on_low = on_low
        self.on_missing = on_missing
        self.on_error = on_error
        self.culture = culture
        self.min_confidence = min_confidence
        self.proc: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.paused = False
        self.stop_requested = False
        self.current_culture = ""

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_requested = False
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def _word_payload(self) -> str:
        variants = []
        for word in self.words:
            variants.extend(word.variants)
        escaped = [v.replace("'", "''") for v in sorted(set(variants))]
        return "@(" + ",".join(f"'{v}'" for v in escaped) + ")"

    def _script(self) -> str:
        return rf"""
Add-Type -AssemblyName System.Speech
$ErrorActionPreference = 'Stop'
$preferred = '{self.culture}'
$words = {self._word_payload()}
$minConfidence = {self.min_confidence:.3f}
$recognizer = $null
try {{
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo($preferred)
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
}} catch {{
    $recognizer = $null
}}
if ($recognizer -eq $null) {{
    $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
    foreach ($info in $infos) {{
        if ($info.Enabled) {{
            $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
            break
        }}
    }}
}}
if ($recognizer -eq $null) {{
    [Console]::Out.WriteLine('MISSING|NO_RECOGNIZER|Nenhum reconhecedor de fala instalado no Windows.')
    [Console]::Out.Flush()
    exit 2
}}
$choices = New-Object System.Speech.Recognition.Choices
$choices.Add($words)
$builder = New-Object System.Speech.Recognition.GrammarBuilder
$builder.Culture = $recognizer.RecognizerInfo.Culture
$builder.Append($choices)
$grammar = New-Object System.Speech.Recognition.Grammar($builder)
$grammar.Name = 'DarwinFirstWords'
$recognizer.LoadGrammar($grammar)
$recognizer.SetInputToDefaultAudioDevice()
$recognizer.BabbleTimeout = [TimeSpan]::FromSeconds(1.2)
$recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds(8)
$recognizer.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(700)
$cultureName = $recognizer.RecognizerInfo.Culture.Name
$recName = $recognizer.RecognizerInfo.Name
[Console]::Out.WriteLine("READY|$cultureName|$recName")
[Console]::Out.Flush()
while ($true) {{
    try {{
        $result = $recognizer.Recognize([TimeSpan]::FromSeconds(8))
        if ($result -ne $null) {{
            $text = ($result.Text -replace '\r?\n', ' ').Trim()
            $confidence = [double]$result.Confidence
            if ($text.Length -gt 0 -and $confidence -ge $minConfidence) {{
                [Console]::Out.WriteLine(("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text))
                [Console]::Out.Flush()
            }} elseif ($text.Length -gt 0) {{
                [Console]::Out.WriteLine(("LOW|{{0:N3}}|{{1}}" -f $confidence, $text))
                [Console]::Out.Flush()
            }}
        }}
    }} catch {{
        $message = $_.Exception.Message -replace '\r?\n', ' '
        [Console]::Out.WriteLine("ERROR|RECOGNIZE|$message")
        [Console]::Out.Flush()
        Start-Sleep -Milliseconds 500
    }}
}}
"""

    def _worker(self) -> None:
        try:
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", self._script()],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.on_error(f"Falha ao iniciar reconhecimento: {exc}")
            return
        assert self.proc.stdout is not None
        while not self.stop_requested:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            self._handle(line.strip())
        if not self.stop_requested and self.proc and self.proc.poll() not in (None, 2):
            self.on_error(f"Reconhecimento encerrou. Codigo={self.proc.poll()}")

    def _handle(self, line: str) -> None:
        if not line:
            return
        parts = line.split("|", 2)
        kind = parts[0]
        if kind == "READY" and len(parts) >= 3:
            self.current_culture = parts[1]
            self.on_ready(parts[1], parts[2])
            return
        if kind in {"RESULT", "LOW"} and len(parts) >= 3:
            try:
                confidence = float(parts[1].replace(",", "."))
            except Exception:
                confidence = 0.0
            if self.paused:
                return
            item = RecognizedWord(parts[2], confidence, self.current_culture or self.culture)
            if kind == "RESULT":
                self.on_result(item)
            else:
                self.on_low(item)
            return
        if kind == "MISSING":
            self.on_missing(parts[-1] if parts else line)
            return
        if kind == "ERROR":
            self.on_error(parts[-1] if parts else line)
            return
        self.on_error(line)


class SpeechEngine:
    def __init__(self, on_start, on_stop) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.proc: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def speak(self, text: str) -> None:
        with self.lock:
            self.stop()
            t = threading.Thread(target=self._worker, args=(text,), daemon=True)
            t.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def _worker(self, text: str) -> None:
        self.on_start(text)
        try:
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = -1; $s.Volume = 100; "
                "$text = [Console]::In.ReadToEnd(); "
                "$s.Speak($text);"
            )
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert self.proc.stdin is not None
            self.proc.stdin.write(text)
            self.proc.stdin.close()
            self.proc.wait()
        except Exception:
            time.sleep(max(1.0, min(10.0, len(text) / 16.0)))
        finally:
            self.on_stop()


class FirstWordsApp:
    BG = "#071018"
    PANEL = "#10202d"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    BLUE = "#58b0ff"
    GREEN = "#75e7a8"
    AMBER = "#f2bf72"
    RED = "#ff707a"

    def __init__(self, root: tk.Tk, culture: str = "pt-BR") -> None:
        self.root = root
        self.root.title("Darwin First Words v49.10")
        self.root.geometry("1040x760")
        self.root.minsize(860, 640)
        self.root.configure(bg=self.BG)
        self.brain = FirstWordsBrain(mode="gui")
        self.listener = FirstWordListener(first_words(), self.on_ready, self.on_result, self.on_low, self.on_missing, self.on_error, culture=culture)
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking)
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.speaking = False
        self.speech_text = ""
        self.level = 0.0
        self.tick = 0.0
        self.status_text = "bercario de primeiras palavras iniciando"
        self.last_word = ""
        self.last_confidence = 0.0
        self.last_experience: WordExperience | None = None
        self.recognizer_missing = False

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        ttk.Button(controls, text="Escutar", command=self.start_listening).pack(side="left", padx=(14, 8), pady=12)
        ttk.Button(controls, text="Pausar", command=self.pause_listening).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Mamae", command=lambda: self.simulate("mamae")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Papai", command=lambda: self.simulate("papai")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Felipe", command=lambda: self.simulate("felipe")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Parar fala", command=self.stop_speech).pack(side="left", padx=(0, 14), pady=12)
        self.transcript = tk.Text(root, height=10, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.transcript.pack(fill="x")
        self.transcript.config(state="disabled")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.write("Darwin", "Estou no bercario de primeiras palavras. Fale: mamae, papai, Felipe, Darwin, oi, sim, nao, ajuda, agua ou brincar.")
        self.start_listening()
        self.root.after(60, self.drain_events)
        self.animate()

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def start_listening(self) -> None:
        self.listener.set_paused(False)
        self.listener.start()
        self.status_text = "escutando primeiras palavras"

    def pause_listening(self) -> None:
        self.listener.set_paused(True)
        self.status_text = "escuta pausada"

    def stop_speech(self) -> None:
        self.speech.stop()
        self.stop_speaking()

    def simulate(self, word: str) -> None:
        self.events.put(("result", RecognizedWord(word, 0.99, "simulated_button")))

    def on_ready(self, culture: str, name: str) -> None:
        self.events.put(("ready", {"culture": culture, "name": name}))

    def on_result(self, item: RecognizedWord) -> None:
        self.events.put(("result", item))

    def on_low(self, item: RecognizedWord) -> None:
        self.events.put(("low", item))

    def on_missing(self, message: str) -> None:
        self.events.put(("missing", message))

    def on_error(self, message: str) -> None:
        self.events.put(("error", message))

    def drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "ready":
                self.recognizer_missing = False
                self.status_text = f"escutando {payload['culture']}"
                self.write("Sistema", f"Reconhecedor ativo: {payload['culture']} / {payload['name']}")
                self.brain.store.log_session(self.brain.session_id, "recognizer_ready", mode="gui", culture=payload["culture"], name=payload["name"])
            elif kind == "missing":
                self.recognizer_missing = True
                self.status_text = "falta reconhecedor de fala do Windows"
                self.write("Sistema", str(payload))
                self.write("Sistema", "A janela continua viva. Instale o recurso de fala do Windows para escuta real; os botoes Mamae/Papai/Felipe simulam o aprendizado para teste.")
                self.brain.store.log_session(self.brain.session_id, "recognizer_missing", mode="gui", payload={"message": str(payload)})
            elif kind == "error":
                self.status_text = "erro de escuta; janela continua viva"
                self.write("Sistema", str(payload))
                self.brain.store.log_session(self.brain.session_id, "recognizer_error", mode="gui", payload={"message": str(payload)})
            elif kind == "low":
                item: RecognizedWord = payload
                self.last_word = item.text
                self.last_confidence = item.confidence
                self.write("Sistema", f"Som incerto: {item.text} ({item.confidence:.2f}). Vou esperar repeticao.")
                self.brain.learn(item.text, item.confidence, source="low_confidence_voice")
            elif kind == "result":
                item = payload
                self.last_word = item.text
                self.last_confidence = item.confidence
                self.write("Voce", f"{item.text} ({item.confidence:.2f})")
                exp = self.brain.learn(item.text, item.confidence, source=item.culture)
                if exp:
                    self.last_experience = exp
                    self.write("Darwin", exp.response)
                    self.speech.speak(exp.response)
        self.root.after(60, self.drain_events)

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text
        self.listener.set_paused(True)
        self.status_text = "falando; escuta protegida"

    def stop_speaking(self) -> None:
        self.speaking = False
        self.level = 0.0
        self.root.after(850, self.resume_after_speech)

    def resume_after_speech(self) -> None:
        self.listener.set_paused(False)
        self.status_text = "escutando primeiras palavras" if not self.recognizer_missing else "falta reconhecedor de fala do Windows"

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 8.0) % max(1, len(self.speech_text)))
        ch = self.speech_text[idx]
        if normalize(ch) in "aeiou":
            return 1.0
        if ch.isalpha():
            return 0.58
        return 0.28

    def animate(self) -> None:
        self.tick += 0.075
        target = self.speech_energy()
        self.level = self.level * 0.76 + target * 0.24
        self.draw()
        self.root.after(16, self.animate)

    def draw(self) -> None:
        c = self.canvas
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")
        cx = w / 2
        cy = h / 2 - 24
        exp = self.last_experience
        if self.recognizer_missing:
            color = self.RED
        elif exp and exp.word in {"mamae", "papai", "felipe"}:
            color = self.GREEN
        elif self.speaking:
            color = self.BLUE
        else:
            color = "#395a70"
        radius = 82 + 32 * self.level + (8 if not self.speaking else 0)
        x = cx + math.sin(self.tick * 2.1) * 28 * self.level
        y = cy + math.cos(self.tick * 1.8) * 20 * self.level
        for i in range(7, 0, -1):
            rr = radius + i * 18
            shade = 20 + i * 8
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="", fill=f"#{shade//2:02x}{shade:02x}{min(130, shade+45):02x}")
        c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#e5f7ff", width=3)
        inner = radius * (0.34 + self.level * 0.12)
        c.create_oval(x - inner, y - inner, x + inner, y + inner, fill="#ebfbff", outline="")
        c.create_text(cx, 38, text="DARWIN FIRST WORDS v49.10", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(cx, 70, text=self.status_text, fill=self.MUTED, font=("Segoe UI", 11))
        c.create_text(cx, h - 82, text="palavras: mamae  papai  Felipe  Darwin  oi  sim  nao  ajuda  agua  brincar", fill=self.MUTED, font=("Segoe UI", 10))
        c.create_text(cx, h - 56, text=f"ultimo som: {self.last_word or 'nenhum'}   confianca {self.last_confidence:.2f}", fill=self.MUTED, font=("Segoe UI", 10))
        if exp:
            c.create_text(cx, h - 30, text=f"{exp.word}: significado {exp.meaning_confidence_after:.2f}   som {exp.sound_confidence_after:.2f}   RZS {exp.rzs_decision}", fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        self.listener.stop()
        self.speech.stop()
        result = self.brain.complete()
        self.write("Sistema", f"Sessao encerrada: {result['session_id']}")
        self.root.destroy()


def run_self_test(details: bool = False) -> dict[str, Any]:
    brain = FirstWordsBrain(mode="self_test")
    samples = [
        ("mamae", 0.91),
        ("mamae", 0.94),
        ("papai", 0.90),
        ("Felipe", 0.96),
        ("Darwin", 0.88),
        ("nao", 0.74),
        ("ajuda", 0.82),
        ("mamae", 0.95),
    ]
    experiences = []
    for raw, confidence in samples:
        exp = brain.learn(raw, confidence, source="self_test")
        if exp:
            experiences.append({"word": exp.word, "response": exp.response, "meaning": exp.meaning_confidence_after, "sound": exp.sound_confidence_after})
    result = brain.complete()
    result["experiences"] = experiences
    if details:
        print(js(result))
    else:
        print(f"DARWIN v49.10 first words self-test concluido: session={result['session_id']} words={result['learned_count']}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin First Words Nursery v49.10")
    ap.add_argument("--culture", default="pt-BR")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test(details=args.details)
        return 0
    root = tk.Tk()
    FirstWordsApp(root, culture=args.culture)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
