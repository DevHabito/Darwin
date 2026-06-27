from __future__ import annotations

"""
DARWIN v49.37 - Contextual Language Learning

Aprende palavras durante a conversa, pede significado quando nao conhece,
aceita exemplos e correcoes e recupera o aprendizado apos reinicio.

Uso:
    py darwin_contextual_language_learning_v49_37.py --self-test --details
"""

import argparse
import json
import random
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_contextual_language_learning_v49_37"

CTX_SESSIONS = "context_language_sessions_v49_37"
CTX_STATE = "context_language_state_v49_37"
LEARNED_WORDS = "learned_words_v49_37"
WORD_EXAMPLES = "learned_word_examples_v49_37"
WORD_ALIASES = "learned_word_aliases_v49_37"
WORD_CORRECTIONS = "learned_word_corrections_v49_37"
CTX_TURNS = "context_language_turns_v49_37"

COMMON_WORDS = {
    "agora", "ainda", "alguma", "algum", "aqui", "assim", "bem", "bom",
    "como", "comigo", "conversa", "darwin", "depois", "disse", "dizer",
    "essa", "esse", "esta", "estou", "exemplo", "felipe", "frase", "hoje",
    "isso", "mais", "meu", "minha", "muito", "nao", "nome", "nosso", "nova",
    "novo", "onde", "outra", "palavra", "para", "porque", "qual", "quando",
    "quer", "significa", "significado", "sobre", "tambem", "tenho", "voce",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").lower())
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in plain).split())


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return {} if fallback is None else fallback


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def short(text: str, limit: int = 300) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


@dataclass
class ContextualMatch:
    action: str
    intent: str
    word: str
    meaning: str
    example: str
    alias: str
    score: float
    source: str


@dataclass
class ContextualReply:
    text: str
    asked_back: str
    action: str
    word: str
    meaning: str
    confidence: float
    evidence_count: int
    persistent_sources: list[str]


class ContextualLanguageLearner:
    def __init__(self, db_path: Path = DB, seed: int = 4937) -> None:
        self.db_path = Path(db_path)
        self.rng = random.Random(seed)
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {CTX_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {CTX_STATE} (
                    session_id TEXT PRIMARY KEY,
                    pending_word TEXT NOT NULL DEFAULT '',
                    pending_question TEXT NOT NULL DEFAULT '',
                    last_word TEXT NOT NULL DEFAULT '',
                    last_action TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {LEARNED_WORDS} (
                    normalized_word TEXT PRIMARY KEY,
                    display_word TEXT NOT NULL,
                    meaning TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    correction_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'learning',
                    learned_session_id TEXT NOT NULL,
                    learned_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WORD_EXAMPLES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    normalized_word TEXT NOT NULL,
                    example_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WORD_ALIASES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    normalized_word TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_session_id TEXT NOT NULL,
                    UNIQUE(normalized_word, alias)
                );

                CREATE TABLE IF NOT EXISTS {WORD_CORRECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    normalized_word TEXT NOT NULL,
                    old_meaning TEXT NOT NULL,
                    corrected_meaning TEXT NOT NULL,
                    confidence_before REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {CTX_TURNS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL UNIQUE,
                    user_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    action TEXT NOT NULL,
                    normalized_word TEXT NOT NULL DEFAULT '',
                    meaning TEXT NOT NULL DEFAULT '',
                    response_text TEXT NOT NULL,
                    asked_back TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    persistent_sources_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def start_session(self, session_id: str, mode: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO {CTX_SESSIONS} (timestamp, session_id, phase, mode, payload_json) VALUES (?, ?, ?, ?, ?)",
                (now(), session_id, "session_start", mode, js({"source": SOURCE})),
            )
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {CTX_STATE}
                (session_id, pending_word, pending_question, last_word, last_action, updated_at, payload_json)
                VALUES (?, '', '', '', '', ?, '{{}}')
                """,
                (session_id, now()),
            )
            conn.commit()

    def complete_session(self, session_id: str, mode: str) -> None:
        with self.connect() as conn:
            count = conn.execute(f"SELECT COUNT(*) FROM {CTX_TURNS} WHERE session_id=?", (session_id,)).fetchone()[0]
            if count == 0:
                return
            words = [
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT normalized_word FROM {CTX_TURNS} WHERE session_id=? AND normalized_word<>''",
                    (session_id,),
                ).fetchall()
            ]
            actions = [
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT action FROM {CTX_TURNS} WHERE session_id=? ORDER BY action",
                    (session_id,),
                ).fetchall()
            ]
            conn.execute(
                f"""
                INSERT INTO {CTX_SESSIONS}
                (timestamp, session_id, phase, mode, turn_count, payload_json)
                VALUES (?, ?, 'session_complete', ?, ?, ?)
                """,
                (now(), session_id, mode, count, js({"session_complete": True, "words": words, "actions": actions})),
            )
            conn.commit()

    def get_context(self, session_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {CTX_STATE} WHERE session_id=?", (session_id,)).fetchone()
            return dict(row) if row else {}

    def set_context(self, session_id: str, *, pending_word: str = "", pending_question: str = "", last_word: str = "", last_action: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CTX_STATE}
                (session_id, pending_word, pending_question, last_word, last_action, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, '{{}}')
                ON CONFLICT(session_id) DO UPDATE SET
                    pending_word=excluded.pending_word,
                    pending_question=excluded.pending_question,
                    last_word=excluded.last_word,
                    last_action=excluded.last_action,
                    updated_at=excluded.updated_at
                """,
                (session_id, pending_word, pending_question, last_word, last_action, now()),
            )
            conn.commit()

    def learned(self, word: str) -> dict[str, Any] | None:
        key = normalize(word)
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {LEARNED_WORDS} WHERE normalized_word=?", (key,)).fetchone()
            if row:
                return dict(row)
            alias = conn.execute(f"SELECT normalized_word FROM {WORD_ALIASES} WHERE alias=?", (key,)).fetchone()
            if alias:
                row = conn.execute(
                    f"SELECT * FROM {LEARNED_WORDS} WHERE normalized_word=?",
                    (alias["normalized_word"],),
                ).fetchone()
                return dict(row) if row else None
        return None

    def known_base_words(self) -> set[str]:
        known = set(COMMON_WORDS)
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='basic_language_lexicon_v49_36'").fetchone():
                for row in conn.execute("SELECT canonical_term, synonyms_json FROM basic_language_lexicon_v49_36").fetchall():
                    for text in [row["canonical_term"], *pj(row["synonyms_json"], [])]:
                        known.update(normalize(text).split())
            for row in conn.execute(f"SELECT normalized_word, display_word FROM {LEARNED_WORDS}").fetchall():
                known.add(str(row["normalized_word"]))
                known.update(normalize(row["display_word"]).split())
            for row in conn.execute(f"SELECT alias FROM {WORD_ALIASES}").fetchall():
                known.update(normalize(row["alias"]).split())
        return known

    def explicit_match(self, text: str, session_id: str) -> ContextualMatch | None:
        n = normalize(text)
        context = self.get_context(session_id)
        pending = normalize(context.get("pending_word", ""))

        patterns = [
            (r"^o que significa ([a-z0-9]+)$", "query_word"),
            (r"^o que quer dizer ([a-z0-9]+)$", "query_word"),
            (r"^qual o significado de ([a-z0-9]+)$", "query_word"),
            (r"^voce sabe o que e ([a-z0-9]+)$", "query_word"),
            (r"^use ([a-z0-9]+) (?:em|numa|em uma) frase$", "use_word"),
            (r"^faca uma frase com ([a-z0-9]+)$", "use_word"),
        ]
        for pattern, action in patterns:
            found = re.match(pattern, n)
            if found:
                word = found.group(1)
                return ContextualMatch(action, f"context_{action}", word, "", "", "", 1.0, "explicit")

        found = re.match(r"^(?:nao darwin |nao |correcao )?([a-z0-9]+) (?:significa|quer dizer) (.+)$", n)
        if found:
            correction = n.startswith(("nao ", "nao darwin ", "correcao "))
            action = "correct_word" if correction and self.learned(found.group(1)) else "teach_word"
            return ContextualMatch(action, f"context_{action}", found.group(1), short(found.group(2)), "", "", 1.0, "explicit")

        found = re.match(r"^([a-z0-9]+) e sinonimo de ([a-z0-9]+)$", n)
        if found:
            return ContextualMatch("teach_alias", "context_teach_alias", found.group(1), "", "", found.group(2), 1.0, "explicit")

        found = re.match(r"^exemplo de ([a-z0-9]+) (.+)$", n)
        if found:
            return ContextualMatch("add_example", "context_add_example", found.group(1), "", short(found.group(2)), "", 1.0, "explicit")

        if pending:
            found = re.match(r"^(?:isso )?(?:significa|quer dizer|e) (.+)$", n)
            if found:
                return ContextualMatch("teach_word", "context_teach_word", pending, short(found.group(1)), "", "", 0.96, "pending_context")
        return None

    def unknown_match(self, text: str, session_id: str) -> ContextualMatch | None:
        n = normalize(text)
        known = self.known_base_words()
        candidates = [
            token
            for token in n.split()
            if len(token) >= 5
            and token not in known
            and not token.isdigit()
            and not token.endswith(("mente", "ando", "endo", "indo"))
        ]
        if not candidates:
            return None
        word = candidates[-1]
        return ContextualMatch("ask_unknown", "context_ask_unknown", word, "", "", "", 0.68, "unknown_token")

    def match(self, text: str, session_id: str, *, allow_unknown: bool = False) -> ContextualMatch | None:
        explicit = self.explicit_match(text, session_id)
        if explicit:
            return explicit
        return self.unknown_match(text, session_id) if allow_unknown else None

    def teach_word(self, word: str, meaning: str, session_id: str, correction: bool) -> dict[str, Any]:
        key = normalize(word)
        meaning = short(meaning)
        existing = self.learned(key)
        old_meaning = str(existing.get("meaning") or "") if existing else ""
        before = float(existing.get("confidence") or 0.0) if existing else 0.0
        if correction:
            confidence = clamp(max(0.72, before * 0.82 + 0.16))
            correction_count = int(existing.get("correction_count") or 0) + 1 if existing else 1
        elif existing and normalize(old_meaning) == normalize(meaning):
            confidence = clamp(before + 0.10)
            correction_count = int(existing.get("correction_count") or 0)
        else:
            confidence = 0.62 if not existing else clamp(before * 0.75 + 0.18)
            correction_count = int(existing.get("correction_count") or 0) if existing else 0
        evidence = int(existing.get("evidence_count") or 0) + 1 if existing else 1
        exposures = int(existing.get("exposure_count") or 0) + 1 if existing else 1
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {LEARNED_WORDS}
                (normalized_word, display_word, meaning, confidence, evidence_count,
                 exposure_count, correction_count, status, learned_session_id,
                 learned_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'learning', ?, ?, ?, ?)
                ON CONFLICT(normalized_word) DO UPDATE SET
                    meaning=excluded.meaning,
                    confidence=excluded.confidence,
                    evidence_count=excluded.evidence_count,
                    exposure_count=excluded.exposure_count,
                    correction_count=excluded.correction_count,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (key, word, meaning, confidence, evidence, exposures, correction_count, session_id, now(), now(), js({"last_source": "correction" if correction else "teaching"})),
            )
            if correction:
                conn.execute(
                    f"""
                    INSERT INTO {WORD_CORRECTIONS}
                    (timestamp, session_id, normalized_word, old_meaning,
                     corrected_meaning, confidence_before, confidence_after, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now(), session_id, key, old_meaning, meaning, before, confidence, js({"source": SOURCE})),
                )
            conn.commit()
        self.maybe_promote(key)
        return self.learned(key) or {}

    def add_example(self, word: str, example: str, session_id: str) -> dict[str, Any] | None:
        item = self.learned(word)
        if not item:
            return None
        key = str(item["normalized_word"])
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WORD_EXAMPLES}
                (timestamp, session_id, normalized_word, example_text, confidence, source, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, key, short(example), 0.78, "user_example", js({"source": SOURCE})),
            )
            conn.execute(
                f"""
                UPDATE {LEARNED_WORDS}
                SET evidence_count=evidence_count+1,
                    exposure_count=exposure_count+1,
                    confidence=MIN(0.95, confidence+0.10),
                    updated_at=?
                WHERE normalized_word=?
                """,
                (now(), key),
            )
            conn.commit()
        self.maybe_promote(key)
        return self.learned(key)

    def add_alias(self, word: str, alias: str, session_id: str) -> dict[str, Any] | None:
        item = self.learned(word)
        if not item:
            return None
        key = str(item["normalized_word"])
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WORD_ALIASES}
                (timestamp, normalized_word, alias, confidence, source_session_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(normalized_word, alias) DO UPDATE SET confidence=MAX(confidence, excluded.confidence)
                """,
                (now(), key, normalize(alias), 0.72, session_id),
            )
            conn.execute(
                f"UPDATE {LEARNED_WORDS} SET evidence_count=evidence_count+1, confidence=MIN(0.95, confidence+0.07), updated_at=? WHERE normalized_word=?",
                (now(), key),
            )
            conn.commit()
        self.maybe_promote(key)
        return self.learned(key)

    def maybe_promote(self, word: str) -> None:
        item = self.learned(word)
        if not item:
            return
        evidence = int(item.get("evidence_count") or 0)
        confidence = float(item.get("confidence") or 0.0)
        if evidence < 2 or confidence < 0.68:
            return
        key = str(item["normalized_word"])
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {LEARNED_WORDS} SET status='consolidated', updated_at=? WHERE normalized_word=?",
                (now(), key),
            )
            conn.execute(
                """
                INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    confidence=MAX(semantic_memory.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    f"learned_word_v49_37:{key}",
                    f"Darwin aprendeu que '{item['display_word']}' significa: {item['meaning']}",
                    confidence,
                    SOURCE,
                    now(),
                ),
            )
            conn.commit()

    def latest_example(self, word: str) -> str:
        item = self.learned(word)
        if not item:
            return ""
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT example_text FROM {WORD_EXAMPLES} WHERE normalized_word=? ORDER BY id DESC LIMIT 1",
                (item["normalized_word"],),
            ).fetchone()
            return str(row["example_text"]) if row else ""

    def respond(self, match: ContextualMatch, session_id: str, rzs_decision: str) -> ContextualReply:
        action = match.action
        word = normalize(match.word)
        sources: list[str] = []
        asked = ""
        item = self.learned(word) if word else None

        if action in {"query_word", "ask_unknown"} and not item:
            text = f"Ainda nao conheco a palavra '{word}'."
            asked = f"O que '{word}' significa?"
            self.set_context(session_id, pending_word=word, pending_question=asked, last_word=word, last_action=action)
            confidence, evidence, meaning = 0.0, 0, ""
        elif action == "query_word" and item:
            meaning = str(item["meaning"])
            confidence = float(item["confidence"])
            evidence = int(item["evidence_count"])
            text = f"Eu aprendi que '{item['display_word']}' significa {meaning}."
            asked = "Esse significado continua correto?"
            sources = [f"{LEARNED_WORDS}:{item['normalized_word']}"]
            self.set_context(session_id, last_word=word, last_action=action)
        elif action in {"teach_word", "correct_word"}:
            item = self.teach_word(word, match.meaning, session_id, action == "correct_word")
            meaning = str(item.get("meaning") or match.meaning)
            confidence = float(item.get("confidence") or 0.0)
            evidence = int(item.get("evidence_count") or 0)
            verb = "Corrigi" if action == "correct_word" else "Aprendi"
            text = f"{verb}: '{word}' significa {meaning}."
            asked = f"Voce pode me dar um exemplo usando '{word}'?"
            sources = [f"{LEARNED_WORDS}:{word}"]
            self.set_context(session_id, last_word=word, last_action=action)
        elif action == "add_example":
            item = self.add_example(word, match.example, session_id)
            if item:
                meaning = str(item["meaning"])
                confidence = float(item["confidence"])
                evidence = int(item["evidence_count"])
                text = f"Guardei o exemplo de '{word}': {match.example}."
                asked = "Quer que eu tente usar a palavra em outra frase?"
                sources = [f"{LEARNED_WORDS}:{word}", f"{WORD_EXAMPLES}:{word}"]
            else:
                meaning, confidence, evidence = "", 0.0, 0
                text = f"Ainda nao sei o significado de '{word}'."
                asked = f"O que '{word}' significa?"
                self.set_context(session_id, pending_word=word, pending_question=asked, last_word=word, last_action=action)
        elif action == "teach_alias":
            item = self.add_alias(word, match.alias, session_id)
            if item:
                meaning = str(item["meaning"])
                confidence = float(item["confidence"])
                evidence = int(item["evidence_count"])
                text = f"Aprendi que '{match.alias}' pode apontar para o conceito de '{word}'."
                sources = [f"{LEARNED_WORDS}:{word}", f"{WORD_ALIASES}:{match.alias}"]
            else:
                meaning, confidence, evidence = "", 0.0, 0
                text = f"Antes do sinonimo, preciso aprender o que '{word}' significa."
                asked = f"O que '{word}' significa?"
        elif action == "use_word" and item:
            meaning = str(item["meaning"])
            confidence = float(item["confidence"])
            evidence = int(item["evidence_count"])
            example = self.latest_example(word)
            if example:
                text = f"Uma frase que aprendi foi: {example}. Em outro contexto: quando encontro {meaning}, posso chamar isso de {word}."
            else:
                text = f"Minha frase e: quando encontro {meaning}, posso chamar isso de {word}."
            sources = [f"{LEARNED_WORDS}:{word}"]
            self.set_context(session_id, last_word=word, last_action=action)
        elif action == "use_word":
            meaning, confidence, evidence = "", 0.0, 0
            text = f"Ainda nao consigo usar '{word}' corretamente."
            asked = f"O que '{word}' significa?"
            self.set_context(session_id, pending_word=word, pending_question=asked, last_word=word, last_action=action)
        else:
            meaning, confidence, evidence = "", 0.0, 0
            text = "Ainda nao sei como aprender com essa frase."

        if rzs_decision == "pause_for_stability":
            text = "Vou aprender devagar para manter estabilidade. " + text
        return ContextualReply(text, asked, action, word, meaning, confidence, evidence, sources)

    def record_turn(
        self,
        session_id: str,
        dialogue_id: str,
        user_text: str,
        match: ContextualMatch,
        reply: ContextualReply,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CTX_TURNS}
                (timestamp, session_id, dialogue_id, user_text, normalized_text,
                 intent, action, normalized_word, meaning, response_text,
                 asked_back, confidence, evidence_count, rzs_decision,
                 sigma_before, sigma_after, persistent_sources_json, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, dialogue_id, user_text, normalize(user_text),
                    match.intent, match.action, reply.word, reply.meaning, reply.text,
                    reply.asked_back, reply.confidence, reply.evidence_count,
                    rzs_decision, sigma_before, sigma_after, js(reply.persistent_sources),
                    js({"match_score": match.score, "match_source": match.source, "alias": match.alias, "example": match.example}),
                ),
            )
            conn.commit()


def invented_word() -> str:
    rng = random.SystemRandom()
    starts = ["lu", "na", "ve", "zi", "ko", "ra", "mi", "te"]
    middles = ["fi", "lo", "ra", "ne", "vi", "so", "ca", "mu"]
    ends = ["ta", "no", "li", "va", "re", "mi", "zu", "co"]
    return rng.choice(starts) + rng.choice(middles) + rng.choice(ends) + str(time.time_ns())[-3:]


def run_self_test(details: bool = False) -> dict[str, Any]:
    from darwin_companion_shell_v49_8 import CompanionCore

    word = invented_word()
    meaning_first = "uma ideia pequena que cresce quando e compartilhada"
    meaning_corrected = "uma ideia cuidadosa que cresce quando e compartilhada"

    first = CompanionCore(seed=4937, mode="context_language_learning_test")
    prompts = [
        f"Hoje encontrei {word}",
        f"Significa {meaning_first}",
        f"O que quer dizer {word}?",
        f"Nao Darwin, {word} significa {meaning_corrected}",
        f"Exemplo de {word}: nossa conversa virou {word} quando aprendemos juntos",
        f"Use {word} em uma frase",
    ]
    first_replies = [first.reply(prompt) for prompt in prompts]
    first.complete()

    second = CompanionCore(seed=4938, mode="context_language_restart_test")
    recall = second.reply(f"O que significa {word}?")
    use = second.reply(f"Use {word} em uma frase")
    second.complete()

    result = {
        "word": word,
        "first_session_id": first.session_id,
        "restart_session_id": second.session_id,
        "first_turns": len(first_replies),
        "unknown_question_asked": "O que" in first_replies[0].reply_text,
        "correction_used": meaning_corrected in recall.reply_text,
        "restart_recalled": word in recall.reply_text and meaning_corrected in recall.reply_text,
        "used_in_new_context": word in use.reply_text and "outro contexto" in use.reply_text,
    }
    result["ok"] = all(
        result[key]
        for key in ("unknown_question_asked", "correction_used", "restart_recalled", "used_in_new_context")
    )
    print("DARWIN v49.37 - CONTEXTUAL LANGUAGE LEARNING")
    print("=" * 68)
    print(f"- palavra inventada em runtime: {word}")
    print(f"- sessao ensino: {first.session_id}")
    print(f"- sessao reinicio: {second.session_id}")
    print(f"- recordou apos reinicio: {result['restart_recalled']}")
    print(f"Resultado self-test: {'OK' if result['ok'] else 'REVISAR'}")
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin Contextual Language Learning v49.37")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
