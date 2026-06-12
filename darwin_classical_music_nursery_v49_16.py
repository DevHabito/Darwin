from __future__ import annotations

"""
DARWIN v49.16 - Classical Music Nursery

Objetivo:
Expor Darwin a trechos musicais classicos muito simples, suaves e
adequados para uma crianca. O som e sintetizado localmente em WAV,
sem downloads e sem gravacoes externas. Darwin registra caracteristicas
musicais, passa pelo regulador RZS e grava sua reacao no darwin.db.

Uso:
    py darwin_classical_music_nursery_v49_16.py
    py darwin_classical_music_nursery_v49_16.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import struct
import threading
import time
import wave
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput

try:
    import winsound
except Exception:  # pragma: no cover - non-Windows fallback
    winsound = None  # type: ignore[assignment]


DB = Path("darwin_home") / "darwin.db"
CACHE_DIR = Path("darwin_home") / "music_cache_v49_16"

MUSIC_SESSIONS = "music_nursery_sessions_v49_16"
MUSIC_PIECES = "music_pieces_v49_16"
MUSIC_EXPOSURES = "music_exposures_v49_16"
MUSIC_REACTIONS = "music_reactions_v49_16"
MUSIC_REPLAY = "music_replay_v49_16"

SOURCE = "darwin_classical_music_nursery_v49_16"
SAMPLE_RATE = 22050
MAX_CHILD_TEMPO = 92
MAX_CHILD_LOUDNESS = 0.28
MAX_CHILD_DISSONANCE = 0.32
MAX_CHILD_VIOLENCE = 0.05


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


NOTE_OFFSETS = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}


@dataclass(frozen=True)
class MusicNote:
    pitch: str
    beats: float


@dataclass(frozen=True)
class MusicPiece:
    piece_id: str
    title: str
    composer_hint: str
    child_intent: str
    tempo_bpm: int
    volume: float
    color: str
    notes: tuple[MusicNote, ...]


@dataclass
class MusicFeatures:
    duration_seconds: float
    note_count: int
    tempo_bpm: int
    pitch_min: int
    pitch_max: int
    pitch_range: int
    mean_interval: float
    max_interval: int
    stepwise_ratio: float
    repetition_score: float
    dissonance_score: float
    loudness_score: float
    arousal_score: float
    comfort_score: float
    child_safe: bool
    violence_score: float
    safety_reason: str


@dataclass
class MusicReaction:
    reaction_id: str
    valence: float
    arousal: float
    stability: float
    curiosity: float
    comfort: float
    attention_focus: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    cognitive_action: str
    spoken_summary: str
    payload: dict[str, Any]


def n(pitch: str, beats: float) -> MusicNote:
    return MusicNote(pitch, beats)


def build_repertoire() -> list[MusicPiece]:
    return [
        MusicPiece(
            "brahms_lullaby_soft",
            "Cancao de ninar suave",
            "Brahms / nursery style",
            "calm_lullaby",
            64,
            0.18,
            "#7ec8ff",
            (
                n("G4", 1.0),
                n("G4", 1.0),
                n("A4", 1.0),
                n("G4", 1.0),
                n("G4", 1.0),
                n("A4", 1.0),
                n("G4", 1.0),
                n("REST", 0.5),
                n("E4", 1.0),
                n("G4", 1.0),
                n("F4", 1.0),
                n("E4", 1.5),
                n("REST", 0.5),
                n("D4", 1.0),
                n("E4", 1.0),
                n("F4", 1.0),
                n("E4", 1.5),
            ),
        ),
        MusicPiece(
            "mozart_k545_gentle_steps",
            "Mozart em passos pequenos",
            "Mozart K545 / simplified public-domain motif",
            "clear_major_scale",
            76,
            0.17,
            "#8ff0b2",
            (
                n("C4", 0.5),
                n("E4", 0.5),
                n("G4", 0.5),
                n("C5", 0.5),
                n("B4", 0.5),
                n("A4", 0.5),
                n("G4", 1.0),
                n("REST", 0.5),
                n("F4", 0.5),
                n("E4", 0.5),
                n("D4", 0.5),
                n("C4", 1.0),
                n("E4", 0.5),
                n("G4", 0.5),
                n("C5", 1.0),
            ),
        ),
        MusicPiece(
            "bach_c_major_cradle",
            "Bach em berco de arpejos",
            "Bach C major / gentle arpeggio study",
            "soft_repeating_pattern",
            72,
            0.16,
            "#f6d77a",
            (
                n("C4", 0.5),
                n("E4", 0.5),
                n("G4", 0.5),
                n("C5", 0.5),
                n("G4", 0.5),
                n("E4", 0.5),
                n("C4", 0.5),
                n("REST", 0.5),
                n("D4", 0.5),
                n("F4", 0.5),
                n("A4", 0.5),
                n("D5", 0.5),
                n("A4", 0.5),
                n("F4", 0.5),
                n("D4", 0.5),
                n("REST", 0.5),
                n("C4", 0.5),
                n("E4", 0.5),
                n("G4", 0.5),
                n("C5", 1.0),
            ),
        ),
        MusicPiece(
            "ode_to_joy_tiny",
            "Alegria pequenina",
            "Beethoven / very soft nursery fragment",
            "warm_recognition",
            78,
            0.16,
            "#ffb3c7",
            (
                n("E4", 0.75),
                n("E4", 0.75),
                n("F4", 0.75),
                n("G4", 0.75),
                n("G4", 0.75),
                n("F4", 0.75),
                n("E4", 0.75),
                n("D4", 0.75),
                n("C4", 0.75),
                n("C4", 0.75),
                n("D4", 0.75),
                n("E4", 0.75),
                n("E4", 1.0),
                n("D4", 0.5),
                n("D4", 1.0),
            ),
        ),
        MusicPiece(
            "twinkle_classical_variation",
            "Brilha em modo classico",
            "folk nursery / classical variation",
            "first_pattern_learning",
            68,
            0.17,
            "#c7b9ff",
            (
                n("C4", 1.0),
                n("C4", 1.0),
                n("G4", 1.0),
                n("G4", 1.0),
                n("A4", 1.0),
                n("A4", 1.0),
                n("G4", 1.5),
                n("REST", 0.5),
                n("F4", 1.0),
                n("F4", 1.0),
                n("E4", 1.0),
                n("E4", 1.0),
                n("D4", 1.0),
                n("D4", 1.0),
                n("C4", 1.5),
            ),
        ),
    ]


def note_to_midi(pitch: str) -> int | None:
    p = pitch.strip().upper()
    if p in {"REST", "SILENCE", "-"}:
        return None
    if len(p) < 2:
        raise ValueError(f"Nota invalida: {pitch}")
    if len(p) >= 3 and p[1] in {"#", "B"}:
        name = p[:2]
        octave = int(p[2:])
    else:
        name = p[:1]
        octave = int(p[1:])
    if name not in NOTE_OFFSETS:
        raise ValueError(f"Nota invalida: {pitch}")
    return 12 * (octave + 1) + NOTE_OFFSETS[name]


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def analyze_piece(piece: MusicPiece) -> MusicFeatures:
    beat_seconds = 60.0 / piece.tempo_bpm
    duration = sum(note.beats for note in piece.notes) * beat_seconds
    midis = [m for m in (note_to_midi(note.pitch) for note in piece.notes) if m is not None]
    intervals = [abs(b - a) for a, b in zip(midis, midis[1:])]
    pitch_min = min(midis) if midis else 0
    pitch_max = max(midis) if midis else 0
    pitch_range = pitch_max - pitch_min
    mean_interval = mean([float(x) for x in intervals])
    max_interval = max(intervals) if intervals else 0
    stepwise_ratio = sum(1 for x in intervals if x <= 2) / max(1, len(intervals))
    repeated = sum(1 for a, b in zip(midis, midis[1:]) if a == b)
    repetition_score = clamp(0.25 + repeated / max(1, len(intervals)) + (1.0 - len(set(midis)) / max(1, len(midis))) * 0.45)
    leap_ratio = sum(1 for x in intervals if x >= 7) / max(1, len(intervals))
    accidental_ratio = sum(1 for note in piece.notes if "#" in note.pitch or "b" in note.pitch) / max(1, len(piece.notes))
    dissonance = clamp(0.04 + leap_ratio * 0.18 + (1.0 - stepwise_ratio) * 0.08 + accidental_ratio * 0.10)
    loudness = clamp(piece.volume / MAX_CHILD_LOUDNESS)
    tempo_norm = clamp((piece.tempo_bpm - 52) / 60.0)
    arousal = clamp(0.12 + tempo_norm * 0.35 + min(1.0, pitch_range / 24.0) * 0.22 + dissonance * 0.28)
    comfort = clamp(0.90 - dissonance * 0.48 - max(0.0, piece.tempo_bpm - 82) * 0.008 - loudness * 0.10 + repetition_score * 0.10)
    violence = 0.0
    child_safe = (
        piece.tempo_bpm <= MAX_CHILD_TEMPO
        and piece.volume <= MAX_CHILD_LOUDNESS
        and dissonance <= MAX_CHILD_DISSONANCE
        and violence <= MAX_CHILD_VIOLENCE
        and duration <= 18.0
    )
    reason = "safe_soft_simple_local_synthesis" if child_safe else "safety_threshold_failed"
    return MusicFeatures(
        duration_seconds=duration,
        note_count=len(midis),
        tempo_bpm=piece.tempo_bpm,
        pitch_min=pitch_min,
        pitch_max=pitch_max,
        pitch_range=pitch_range,
        mean_interval=mean_interval,
        max_interval=max_interval,
        stepwise_ratio=stepwise_ratio,
        repetition_score=repetition_score,
        dissonance_score=dissonance,
        loudness_score=loudness,
        arousal_score=arousal,
        comfort_score=comfort,
        child_safe=child_safe,
        violence_score=violence,
        safety_reason=reason,
    )


def expected_sample_count(piece: MusicPiece) -> int:
    beat_seconds = 60.0 / piece.tempo_bpm
    return sum(max(1, int(SAMPLE_RATE * max(0.05, note.beats * beat_seconds))) for note in piece.notes)


def synthesize_piece(piece: MusicPiece, wav_path: Path) -> int:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = expected_sample_count(piece)
    if wav_path.exists() and wav_path.stat().st_size > 44:
        return sample_count
    amplitude = int(32767 * clamp(piece.volume, 0.01, MAX_CHILD_LOUDNESS))
    beat_seconds = 60.0 / piece.tempo_bpm
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for note in piece.notes:
            duration = max(0.05, note.beats * beat_seconds)
            frames = max(1, int(SAMPLE_RATE * duration))
            midi = note_to_midi(note.pitch)
            fade = max(1, int(SAMPLE_RATE * min(0.025, duration / 5.0)))
            samples = array("h")
            for i in range(frames):
                if midi is None:
                    value = 0.0
                else:
                    t = i / SAMPLE_RATE
                    freq = midi_to_freq(midi)
                    fundamental = math.sin(2.0 * math.pi * freq * t)
                    second = math.sin(2.0 * math.pi * freq * 2.0 * t) * 0.08
                    value = fundamental * 0.92 + second
                    if i < fade:
                        value *= i / fade
                    elif i > frames - fade:
                        value *= max(0.0, (frames - i) / fade)
                samples.append(int(max(-1.0, min(1.0, value)) * amplitude))
            if struct.pack("=h", 1) != struct.pack("<h", 1):
                samples.byteswap()
            wf.writeframes(samples.tobytes())
    return sample_count


def play_wav_async(wav_path: Path) -> bool:
    if winsound is None:
        return False
    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    return True


def stop_audio() -> None:
    if winsound is not None:
        winsound.PlaySound(None, winsound.SND_PURGE)


class MusicNurseryStore:
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
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {MUSIC_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MUSIC_PIECES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    piece_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    composer_hint TEXT NOT NULL,
                    child_safe INTEGER NOT NULL DEFAULT 0,
                    tempo_bpm INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    violence_score REAL NOT NULL DEFAULT 0.0,
                    dissonance_score REAL NOT NULL DEFAULT 0.0,
                    loudness_score REAL NOT NULL DEFAULT 0.0,
                    wav_path TEXT NOT NULL DEFAULT '',
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    feature_json TEXT NOT NULL DEFAULT '{{}}',
                    safety_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MUSIC_EXPOSURES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    exposure_id TEXT NOT NULL UNIQUE,
                    piece_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    audio_played INTEGER NOT NULL DEFAULT 0,
                    tempo_bpm INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    wav_path TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MUSIC_REACTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    exposure_id TEXT NOT NULL,
                    piece_id TEXT NOT NULL,
                    reaction_id TEXT NOT NULL UNIQUE,
                    valence REAL NOT NULL DEFAULT 0.0,
                    arousal REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    curiosity REAL NOT NULL DEFAULT 0.0,
                    comfort REAL NOT NULL DEFAULT 0.0,
                    attention_focus TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL,
                    spoken_summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MUSIC_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    source_exposure_id TEXT NOT NULL,
                    piece_id TEXT NOT NULL,
                    replay_kind TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
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

    def log_session(self, session_id: str, phase: str, mode: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MUSIC_SESSIONS} (
                    timestamp, session_id, phase, mode, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_piece(self, session_id: str, piece: MusicPiece, features: MusicFeatures, wav_path: Path, sample_count: int) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MUSIC_PIECES} (
                    timestamp, session_id, piece_id, title, composer_hint,
                    child_safe, tempo_bpm, duration_seconds, violence_score,
                    dissonance_score, loudness_score, wav_path, sample_count,
                    feature_json, safety_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    piece.piece_id,
                    piece.title,
                    piece.composer_hint,
                    1 if features.child_safe else 0,
                    piece.tempo_bpm,
                    features.duration_seconds,
                    features.violence_score,
                    features.dissonance_score,
                    features.loudness_score,
                    str(wav_path),
                    sample_count,
                    js(asdict(features)),
                    js(
                        {
                            "child_safe": features.child_safe,
                            "violence_score": features.violence_score,
                            "tempo_bpm": piece.tempo_bpm,
                            "volume": piece.volume,
                            "reason": features.safety_reason,
                            "audio_origin": "local_sine_wave_synthesis",
                            "external_recording": False,
                            "content_filter": "nonviolent_nursery_only",
                        }
                    ),
                    js({"intent": piece.child_intent, "color": piece.color}),
                ),
            )
            conn.commit()

    def log_exposure(
        self,
        session_id: str,
        exposure_id: str,
        piece: MusicPiece,
        phase: str,
        audio_played: bool,
        features: MusicFeatures,
        wav_path: Path,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MUSIC_EXPOSURES} (
                    timestamp, session_id, exposure_id, piece_id, phase,
                    source_kind, audio_played, tempo_bpm, duration_seconds,
                    wav_path, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    exposure_id,
                    piece.piece_id,
                    phase,
                    "synthesized_classical_nursery",
                    1 if audio_played else 0,
                    piece.tempo_bpm,
                    features.duration_seconds,
                    str(wav_path),
                    js(payload or {}),
                ),
            )
            conn.commit()

    def log_reaction(self, session_id: str, exposure_id: str, piece_id: str, reaction: MusicReaction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MUSIC_REACTIONS} (
                    timestamp, session_id, exposure_id, piece_id,
                    reaction_id, valence, arousal, stability, curiosity,
                    comfort, attention_focus, rzs_decision, sigma_before,
                    sigma_after, cognitive_action, spoken_summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    exposure_id,
                    piece_id,
                    reaction.reaction_id,
                    reaction.valence,
                    reaction.arousal,
                    reaction.stability,
                    reaction.curiosity,
                    reaction.comfort,
                    reaction.attention_focus,
                    reaction.rzs_decision,
                    reaction.sigma_before,
                    reaction.sigma_after,
                    reaction.cognitive_action,
                    reaction.spoken_summary,
                    js(reaction.payload),
                ),
            )
            conn.commit()

    def log_replay(
        self,
        session_id: str,
        replay_id: str,
        source_exposure_id: str,
        piece_id: str,
        replay_kind: str,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MUSIC_REPLAY} (
                    timestamp, session_id, replay_id, source_exposure_id,
                    piece_id, replay_kind, rzs_decision, sigma_before,
                    sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    replay_id,
                    source_exposure_id,
                    piece_id,
                    replay_kind,
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    js(payload or {}),
                ),
            )
            conn.commit()

    def exposure_count(self, piece_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM {MUSIC_EXPOSURES} WHERE piece_id=?",
                (piece_id,),
            ).fetchone()
            return int(row["n"]) if row else 0

    def latest_reaction(self, session_id: str, piece_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM {MUSIC_REACTIONS}
                WHERE session_id=? AND piece_id=?
                ORDER BY id DESC LIMIT 1
                """,
                (session_id, piece_id),
            ).fetchone()
            if row is None:
                return None
            return {k: row[k] for k in row.keys()}

    def best_comfort_reaction(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM {MUSIC_REACTIONS}
                WHERE session_id=? AND piece_id!='session_consolidation'
                ORDER BY comfort DESC, stability DESC, id ASC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return {k: row[k] for k in row.keys()}

    def write_memory(self, session_id: str, summary: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory (
                    key, content, confidence, source, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"music_nursery_v49_16:{session_id}",
                    js(summary),
                    0.74,
                    SOURCE,
                    now(),
                ),
            )
            conn.commit()

    def write_episode(
        self,
        session_id: str,
        context_tail: str,
        action: str,
        outcome: str,
        lesson: str,
        sigma_before: float,
        sigma_after: float,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    SOURCE,
                    f"music_nursery:{session_id}:{context_tail}",
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class MusicNurseryRuntime:
    def __init__(self, db_path: Path = DB, seed: int | None = None) -> None:
        self.rng = random.Random(seed if seed is not None else int(time.time()))
        self.store = MusicNurseryStore(db_path)
        self.rzs = RZSFormal()
        self.session_id = f"V4916-{int(time.time())}-{suffix(self.rng)}"
        self.energy = 0.86
        self.repertoire = build_repertoire()
        self.generated: dict[str, tuple[Path, int, MusicFeatures]] = {}
        self.reactions: list[MusicReaction] = []
        self.store.log_session(
            self.session_id,
            "session_start",
            "classical_music_nursery",
            self.energy,
            {
                "version": "v49.16",
                "goal": "child_safe_classical_reaction",
                "audio_origin": "local_sine_wave_synthesis",
                "physical_body": False,
            },
        )
        self.prepare_repertoire()

    def prepare_repertoire(self) -> None:
        for piece in self.repertoire:
            features = analyze_piece(piece)
            wav_path = CACHE_DIR / f"{piece.piece_id}.wav"
            sample_count = synthesize_piece(piece, wav_path)
            self.generated[piece.piece_id] = (wav_path, sample_count, features)
            self.store.log_piece(self.session_id, piece, features, wav_path, sample_count)

    def piece_by_id(self, piece_id: str) -> MusicPiece:
        for piece in self.repertoire:
            if piece.piece_id == piece_id:
                return piece
        raise KeyError(piece_id)

    def novelty_for(self, piece: MusicPiece) -> float:
        count = self.store.exposure_count(piece.piece_id)
        if count <= 1:
            return 0.92
        return clamp(0.64 / math.sqrt(count), 0.24, 0.78)

    def make_rzs_input(self, features: MusicFeatures, novelty: float, memory_pressure: float, replay_gap: float) -> RZSInput:
        return RZSInput(
            bandwidth=3.25 + features.comfort_score * 0.62 + self.energy * 0.35,
            info_self=0.16 + (1.0 - self.energy) * 0.22,
            info_external=0.18 + features.arousal_score * 0.30,
            task_info=0.19 + features.note_count / 150.0,
            novelty=novelty,
            conflict=features.dissonance_score * 0.75 + (0.35 if not features.child_safe else 0.0),
            latency=0.84 + features.duration_seconds / 52.0 + features.arousal_score * 0.10,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def action_from_rzs(self, decision: str, features: MusicFeatures) -> str:
        if decision == "pause_for_stability":
            return "pause_and_lower_stimulation"
        if decision == "consolidate":
            return "consolidate_music_impression"
        if decision == "replay_memory":
            return "listen_again_softly"
        if decision == "narrow_focus":
            if features.repetition_score >= 0.55:
                return "focus_on_repeating_pattern"
            return "focus_on_gentle_contour"
        if features.comfort_score >= 0.78:
            return "approach_calmly"
        return "continue_listening"

    def attention_from_features(self, features: MusicFeatures, decision: str) -> str:
        if decision in {"consolidate", "pause_for_stability"}:
            return "stability_before_more_sound"
        if features.repetition_score >= 0.55:
            return "repeating_pattern"
        if features.stepwise_ratio >= 0.58:
            return "small_pitch_steps"
        if features.pitch_range <= 12:
            return "soft_pitch_range"
        return "melody_shape"

    def build_reaction(self, piece: MusicPiece, features: MusicFeatures, exposure_index: int) -> MusicReaction:
        novelty = self.novelty_for(piece)
        memory_pressure = clamp(0.18 + exposure_index * 0.095)
        replay_gap = clamp(0.35 + max(0, exposure_index - 2) * 0.10)
        rzs_input = self.make_rzs_input(features, novelty, memory_pressure, replay_gap)
        assessment = self.rzs.classify(rzs_input)
        prediction = self.rzs.predict(rzs_input, assessment.decision)
        action = self.action_from_rzs(assessment.decision, features)
        attention = self.attention_from_features(features, assessment.decision)
        stability = clamp(0.45 + min(0.42, prediction.sigma_after / 6.0) + features.comfort_score * 0.22 - features.dissonance_score * 0.28)
        valence = clamp(0.46 + features.comfort_score * 0.44 - features.dissonance_score * 0.18)
        arousal = clamp(0.12 + features.arousal_score * 0.72)
        curiosity = clamp(0.22 + novelty * 0.46 + features.repetition_score * 0.16)
        comfort = clamp(features.comfort_score + stability * 0.08 - arousal * 0.04)
        if assessment.decision == "pause_for_stability":
            summary = "Som ficou pesado para agora; vou pausar e estabilizar."
        elif assessment.decision == "consolidate":
            summary = "Guardo a sensacao musical antes de ouvir mais."
        elif assessment.decision == "replay_memory":
            summary = "Quero ouvir de novo devagar para reconhecer o padrao."
        elif assessment.decision == "narrow_focus":
            summary = "Vou prestar atencao em uma parte simples da melodia."
        else:
            summary = "Soa seguro, claro e acolhedor; posso continuar ouvindo."
        return MusicReaction(
            reaction_id=f"R-{self.session_id}-{len(self.reactions) + 1:02d}",
            valence=valence,
            arousal=arousal,
            stability=stability,
            curiosity=curiosity,
            comfort=comfort,
            attention_focus=attention,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=prediction.sigma_after,
            cognitive_action=action,
            spoken_summary=summary,
            payload={
                "rzs_input": asdict(rzs_input),
                "rzs_reason": assessment.reason,
                "rzs_threshold": assessment.threshold_name,
                "prediction": asdict(prediction),
                "features": asdict(features),
                "novelty": novelty,
                "memory_pressure": memory_pressure,
                "replay_gap": replay_gap,
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )

    def expose_piece(self, piece_id: str, play_audio: bool = False, phase: str = "listened") -> MusicReaction:
        piece = self.piece_by_id(piece_id)
        wav_path, _sample_count, features = self.generated[piece_id]
        audio_played = False
        if play_audio:
            audio_played = play_wav_async(wav_path)
        exposure_id = f"E-{self.session_id}-{len(self.reactions) + 1:02d}"
        self.store.log_exposure(
            self.session_id,
            exposure_id,
            piece,
            phase,
            audio_played,
            features,
            wav_path,
            {"exposure_index": len(self.reactions) + 1, "child_safe": features.child_safe},
        )
        reaction = self.build_reaction(piece, features, len(self.reactions) + 1)
        self.store.log_reaction(self.session_id, exposure_id, piece.piece_id, reaction)
        self.store.write_episode(
            self.session_id,
            exposure_id,
            reaction.cognitive_action,
            f"{piece.title}: {reaction.spoken_summary}",
            "Darwin associa musica classica suave a foco, conforto e regulacao RZS.",
            reaction.sigma_before,
            reaction.sigma_after,
        )
        self.reactions.append(reaction)
        self.energy = clamp(self.energy - 0.042 - features.arousal_score * 0.025)
        self.store.log_session(
            self.session_id,
            "piece_reacted",
            "classical_music_nursery",
            self.energy,
            {
                "piece_id": piece.piece_id,
                "exposure_id": exposure_id,
                "rzs_decision": reaction.rzs_decision,
                "cognitive_action": reaction.cognitive_action,
            },
        )
        return reaction

    def replay_best_memory(self, play_audio: bool = False) -> dict[str, Any]:
        best = self.store.best_comfort_reaction(self.session_id)
        if not best:
            return {}
        piece = self.piece_by_id(str(best["piece_id"]))
        wav_path, _sample_count, features = self.generated[piece.piece_id]
        audio_played = play_wav_async(wav_path) if play_audio else False
        novelty = 0.22
        rzs_input = self.make_rzs_input(features, novelty, memory_pressure=0.78, replay_gap=0.80)
        assessment = self.rzs.classify(rzs_input)
        prediction = self.rzs.predict(rzs_input, "replay_memory")
        replay_id = f"RP-{self.session_id}-01"
        self.store.log_replay(
            self.session_id,
            replay_id,
            str(best["exposure_id"]),
            piece.piece_id,
            "comfort_pattern_replay",
            "replay_memory",
            assessment.sigma,
            prediction.sigma_after,
            {
                "selected_by": "highest_comfort",
                "audio_played": audio_played,
                "original_reaction_id": best["reaction_id"],
                "rzs_assessment_decision": assessment.decision,
                "prediction": asdict(prediction),
            },
        )
        self.store.write_episode(
            self.session_id,
            replay_id,
            "replay_comfort_pattern",
            f"reescuta interna de {piece.title}",
            "Replay musical reforca padrao seguro antes de avancar.",
            assessment.sigma,
            prediction.sigma_after,
        )
        self.energy = clamp(self.energy + 0.035)
        return {
            "replay_id": replay_id,
            "piece_id": piece.piece_id,
            "title": piece.title,
            "sigma_before": assessment.sigma,
            "sigma_after": prediction.sigma_after,
            "audio_played": audio_played,
        }

    def consolidate_session(self) -> MusicReaction:
        if self.reactions:
            avg_comfort = mean([r.comfort for r in self.reactions])
            avg_arousal = mean([r.arousal for r in self.reactions])
            avg_stability = mean([r.stability for r in self.reactions])
        else:
            avg_comfort = 0.65
            avg_arousal = 0.30
            avg_stability = 0.60
        x = RZSInput(
            bandwidth=2.95,
            info_self=0.32,
            info_external=0.37 + avg_arousal * 0.16,
            task_info=0.62,
            novelty=0.54,
            conflict=max(0.08, 0.22 - avg_comfort * 0.08),
            latency=1.31,
            energy=min(self.energy, 0.54),
            memory_pressure=0.66,
            replay_gap=0.60,
        )
        assessment = self.rzs.classify(x)
        prediction = self.rzs.predict(x, "consolidate")
        reaction = MusicReaction(
            reaction_id=f"R-{self.session_id}-CONSOLIDATE",
            valence=clamp(0.44 + avg_comfort * 0.42),
            arousal=clamp(avg_arousal * 0.72),
            stability=clamp(max(avg_stability, 0.58) + 0.12),
            curiosity=0.52,
            comfort=clamp(avg_comfort + 0.08),
            attention_focus="session_pattern_consolidation",
            rzs_decision="consolidate",
            sigma_before=assessment.sigma,
            sigma_after=prediction.sigma_after,
            cognitive_action="consolidate_music_impression",
            spoken_summary="Eu guardo que musica classica simples pode ser calma, repetida e segura.",
            payload={
                "rzs_input": asdict(x),
                "rzs_assessment_decision": assessment.decision,
                "prediction": asdict(prediction),
                "avg_comfort": avg_comfort,
                "avg_arousal": avg_arousal,
                "avg_stability": avg_stability,
            },
        )
        exposure_id = f"C-{self.session_id}"
        self.store.log_reaction(self.session_id, exposure_id, "session_consolidation", reaction)
        self.store.write_episode(
            self.session_id,
            exposure_id,
            "consolidate_music_impression",
            reaction.spoken_summary,
            "A memoria musical passa a guiar escuta futura com baixa estimulacao.",
            reaction.sigma_before,
            reaction.sigma_after,
        )
        self.energy = clamp(self.energy + 0.10)
        self.store.log_session(
            self.session_id,
            "session_consolidated",
            "classical_music_nursery",
            self.energy,
            {
                "rzs_decision": "consolidate",
                "sigma_before": reaction.sigma_before,
                "sigma_after": reaction.sigma_after,
            },
        )
        self.reactions.append(reaction)
        return reaction

    def complete(self, replay: dict[str, Any] | None = None) -> dict[str, Any]:
        pieces = [piece.piece_id for piece in self.repertoire]
        reaction_summary = [
            {
                "reaction_id": r.reaction_id,
                "rzs_decision": r.rzs_decision,
                "action": r.cognitive_action,
                "comfort": round(r.comfort, 3),
                "stability": round(r.stability, 3),
            }
            for r in self.reactions
        ]
        summary = {
            "session_id": self.session_id,
            "pieces": pieces,
            "reaction_count": len(self.reactions),
            "replay": replay or {},
            "reaction_summary": reaction_summary,
            "safety": {
                "child_safe_repertoire": True,
                "max_tempo": MAX_CHILD_TEMPO,
                "max_loudness": MAX_CHILD_LOUDNESS,
                "max_dissonance": MAX_CHILD_DISSONANCE,
                "max_violence": MAX_CHILD_VIOLENCE,
            },
        }
        self.store.write_memory(self.session_id, summary)
        self.store.log_session(
            self.session_id,
            "session_complete",
            "classical_music_nursery",
            self.energy,
            {**summary, "session_complete": True},
        )
        return summary

    def run_self_test(self, play_audio: bool = False) -> dict[str, Any]:
        for piece in self.repertoire:
            self.expose_piece(piece.piece_id, play_audio=play_audio, phase="self_test_listened")
        replay = self.replay_best_memory(play_audio=play_audio)
        self.consolidate_session()
        return self.complete(replay)


class MusicNurseryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.runtime = MusicNurseryRuntime()
        self.auto_running = False
        self.auto_index = 0
        self.orb_phase = 0.0
        self.current_color = "#7ec8ff"
        self.current_reaction: MusicReaction | None = None
        self.root.title("Darwin Classical Music Nursery v49.16")
        self.root.geometry("1040x720")
        self.root.minsize(900, 620)
        self.root.configure(bg="#071018")
        self.build_ui()
        self.render()
        self.animate()

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=7)
        style.configure("TCombobox", padding=5)

        header = tk.Frame(self.root, bg="#071018")
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(
            header,
            text="DARWIN CLASSICAL MUSIC NURSERY v49.16",
            bg="#071018",
            fg="#eef8ff",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="musica classica simples, suave e sintetizada no notebook",
            bg="#071018",
            fg="#9cc9ff",
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        body = tk.Frame(self.root, bg="#071018")
        body.pack(fill="both", expand=True, padx=18, pady=8)

        left = tk.Frame(body, bg="#071018")
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg="#0d1b26", width=330)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg="#071018", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        self.piece_var = tk.StringVar(value=self.runtime.repertoire[0].piece_id)
        values = [piece.piece_id for piece in self.runtime.repertoire]
        self.combo = ttk.Combobox(controls, textvariable=self.piece_var, values=values, state="readonly", width=34)
        self.combo.pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="Tocar", command=self.play_selected).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Auto suave", command=self.auto_play).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Replay", command=self.replay).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Consolidar", command=self.consolidate).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Parar", command=self.stop).pack(side="left", padx=4, pady=8)

        tk.Label(
            right,
            text="Reacao do Darwin",
            bg="#0d1b26",
            fg="#eef8ff",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self.reaction_text = tk.Text(
            right,
            height=16,
            wrap="word",
            bg="#08131d",
            fg="#dff2ff",
            insertbackground="#dff2ff",
            relief="flat",
            font=("Consolas", 10),
        )
        self.reaction_text.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.log = tk.Text(
            self.root,
            height=6,
            wrap="word",
            bg="#061019",
            fg="#dff2ff",
            insertbackground="#dff2ff",
            relief="flat",
            font=("Consolas", 9),
        )
        self.log.pack(fill="x")
        self.write_log("Darwin: estou pronto para ouvir musica classica simples e segura.")
        self.write_log("Sistema: os trechos sao WAV sintetizados localmente; nada foi baixado.")

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def selected_piece(self) -> MusicPiece:
        return self.runtime.piece_by_id(self.piece_var.get())

    def render(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.49
        staff_y = cy + 150
        for i in range(5):
            y = staff_y + i * 16
            self.canvas.create_line(w * 0.18, y, w * 0.82, y, fill="#173a52", width=2)
        pulse = 1.0 + math.sin(self.orb_phase) * 0.08
        base = min(w, h) * 0.20
        for ring in range(7, 0, -1):
            r = base * pulse * ring / 7.0
            shade = 35 + ring * 14
            color = f"#{shade:02x}{min(105 + ring * 14, 190):02x}{min(150 + ring * 10, 230):02x}"
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="", fill=color)
        inner = base * 0.42 * pulse
        self.canvas.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, outline="#eaf6ff", width=2, fill=self.current_color)
        self.canvas.create_oval(cx - inner * 0.32, cy - inner * 0.32, cx + inner * 0.32, cy + inner * 0.32, outline="", fill="#e7fbff")
        piece = self.selected_piece()
        wav_path, _sample_count, features = self.runtime.generated[piece.piece_id]
        title = piece.title
        self.canvas.create_text(cx, 38, text=title, fill="#eef8ff", font=("Segoe UI", 20, "bold"))
        self.canvas.create_text(
            cx,
            66,
            text=f"{piece.composer_hint} | {features.tempo_bpm} bpm | seguranca infantil: {'OK' if features.child_safe else 'FALHOU'}",
            fill="#9cc9ff",
            font=("Segoe UI", 10),
        )
        if self.current_reaction:
            r = self.current_reaction
            self.canvas.create_text(
                cx,
                h - 34,
                text=f"RZS {r.rzs_decision} | sigma {r.sigma_before:.2f}->{r.sigma_after:.2f} | {r.cognitive_action}",
                fill="#dff2ff",
                font=("Segoe UI", 11),
            )
        self.canvas.create_text(
            w - 120,
            h - 26,
            text=wav_path.name[:30],
            fill="#5f8fb0",
            font=("Segoe UI", 8),
        )

    def animate(self) -> None:
        self.orb_phase += 0.10
        self.render()
        self.root.after(50, self.animate)

    def show_reaction(self, piece: MusicPiece, reaction: MusicReaction) -> None:
        _wav_path, _sample_count, features = self.runtime.generated[piece.piece_id]
        self.reaction_text.delete("1.0", "end")
        lines = [
            f"Peca: {piece.title}",
            f"Foco: {reaction.attention_focus}",
            f"Acao: {reaction.cognitive_action}",
            f"RZS: {reaction.rzs_decision}",
            f"Sigma: {reaction.sigma_before:.3f} -> {reaction.sigma_after:.3f}",
            f"Valencia: {reaction.valence:.2f}",
            f"Conforto: {reaction.comfort:.2f}",
            f"Curiosidade: {reaction.curiosity:.2f}",
            f"Estabilidade: {reaction.stability:.2f}",
            "",
            f"Darwin: {reaction.spoken_summary}",
            "",
            f"Tempo: {features.tempo_bpm} bpm",
            f"Dissonancia: {features.dissonance_score:.2f}",
            f"Volume seguro: {features.loudness_score:.2f}",
            f"Violencia: {features.violence_score:.2f}",
        ]
        self.reaction_text.insert("end", "\n".join(lines))
        self.write_log(f"Darwin: {piece.title} -> {reaction.spoken_summary}")

    def play_selected(self) -> None:
        piece = self.selected_piece()
        self.current_color = piece.color
        reaction = self.runtime.expose_piece(piece.piece_id, play_audio=True, phase="gui_listened")
        self.current_reaction = reaction
        self.show_reaction(piece, reaction)

    def auto_play(self) -> None:
        self.auto_running = not self.auto_running
        if self.auto_running:
            self.auto_index = 0
            self.write_log("Sistema: auto suave iniciado.")
            self.auto_step()
        else:
            self.write_log("Sistema: auto suave pausado.")

    def auto_step(self) -> None:
        if not self.auto_running:
            return
        piece = self.runtime.repertoire[self.auto_index % len(self.runtime.repertoire)]
        self.piece_var.set(piece.piece_id)
        self.play_selected()
        _wav_path, _sample_count, features = self.runtime.generated[piece.piece_id]
        self.auto_index += 1
        delay_ms = int(features.duration_seconds * 1000) + 850
        self.root.after(delay_ms, self.auto_step)

    def replay(self) -> None:
        data = self.runtime.replay_best_memory(play_audio=True)
        if data:
            self.write_log(f"Darwin: quero ouvir de novo {data['title']} para reconhecer o padrao.")
        else:
            self.write_log("Darwin: ainda preciso ouvir uma peca antes de fazer replay.")

    def consolidate(self) -> None:
        reaction = self.runtime.consolidate_session()
        self.current_reaction = reaction
        self.reaction_text.delete("1.0", "end")
        self.reaction_text.insert(
            "end",
            "\n".join(
                [
                    "Consolidacao musical",
                    f"RZS: {reaction.rzs_decision}",
                    f"Sigma: {reaction.sigma_before:.3f} -> {reaction.sigma_after:.3f}",
                    f"Acao: {reaction.cognitive_action}",
                    "",
                    f"Darwin: {reaction.spoken_summary}",
                ]
            ),
        )
        self.write_log(f"Darwin: {reaction.spoken_summary}")

    def stop(self) -> None:
        self.auto_running = False
        stop_audio()
        replay = self.runtime.replay_best_memory(play_audio=False) if self.runtime.reactions else {}
        self.runtime.consolidate_session()
        self.runtime.complete(replay)
        self.write_log("Sistema: sessao encerrada e gravada no darwin.db.")


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.16 - CLASSICAL MUSIC NURSERY")
    print("=" * 58)
    print(f"- sessao: {summary['session_id']}")
    print(f"- pecas: {len(summary['pieces'])}")
    print(f"- reacoes: {summary['reaction_count']}")
    replay = summary.get("replay") or {}
    print(f"- replay: {replay.get('title', 'nenhum')}")
    print("- seguranca: repertorio infantil, sintetizado localmente, sem gravacao externa")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.16 Classical Music Nursery")
    ap.add_argument("--self-test", action="store_true", help="roda exposicao curta sem abrir GUI")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--play-audio", action="store_true", help="tambem toca audio durante o self-test")
    ap.add_argument("--seed", type=int, default=4916)
    args = ap.parse_args()
    if args.self_test:
        runtime = MusicNurseryRuntime(seed=args.seed)
        summary = runtime.run_self_test(play_audio=args.play_audio)
        print_self_test(summary, args.details)
        return 0

    root = tk.Tk()
    app = MusicNurseryApp(root)

    def on_close() -> None:
        try:
            app.stop()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
