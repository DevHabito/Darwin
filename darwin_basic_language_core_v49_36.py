from __future__ import annotations

"""
DARWIN v49.36 - Basic Grounded Language Core

Vocabulário conversacional básico com sinônimos, perguntas de volta e
respostas fundamentadas no estado persistido do Darwin.

Uso:
    py darwin_basic_language_core_v49_36.py --self-test --details
"""

import argparse
import json
import random
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_basic_language_core_v49_36"

LANG_SESSIONS = "basic_language_sessions_v49_36"
LANG_LEXICON = "basic_language_lexicon_v49_36"
LANG_PATTERNS = "basic_language_patterns_v49_36"
LANG_TURNS = "basic_language_turns_v49_36"


VOCABULARY: list[tuple[str, str, list[str], str, str, list[str]]] = [
    ("identity_name", "nome", ["chamar", "chama", "identidade", "quem"], "noun", "identity", ["basic_identity_name", "basic_user_name"]),
    ("self_pronoun", "eu", ["me", "meu", "minha", "comigo"], "pronoun", "relation", ["basic_user_name", "basic_user_positive", "basic_user_negative"]),
    ("other_pronoun", "voce", ["seu", "sua", "te", "contigo"], "pronoun", "relation", ["basic_identity_name", "basic_affect_state", "basic_sleep_quality", "basic_wellbeing"]),
    ("feeling", "sentir", ["sente", "sentindo", "sentimento", "humor", "animo", "por dentro"], "verb", "affect", ["basic_affect_state"]),
    ("wellbeing", "bem", ["legal", "otimo", "tranquilo", "tudo certo"], "adjective", "affect", ["basic_wellbeing", "basic_user_positive"]),
    ("sadness", "triste", ["mal", "chateado", "abatido", "para baixo"], "adjective", "affect", ["basic_user_negative"]),
    ("calm", "calmo", ["tranquilo", "sereno", "quieto"], "adjective", "affect", ["basic_affect_state"]),
    ("curiosity", "curioso", ["interessado", "atento", "querendo aprender"], "adjective", "affect", ["basic_affect_state"]),
    ("sleep", "dormir", ["dorme", "dormiu", "sono", "mimir"], "verb", "sleep", ["basic_sleep_quality", "basic_user_tired"]),
    ("rest", "descansar", ["descansou", "repousar", "repouso", "recuperar"], "verb", "sleep", ["basic_sleep_quality"]),
    ("wake", "acordar", ["acordou", "despertar", "levantou"], "verb", "sleep", ["basic_sleep_quality"]),
    ("tired", "cansado", ["cansada", "com sono", "exausto", "sem energia"], "adjective", "sleep", ["basic_user_tired"]),
    ("today", "hoje", ["agora", "neste momento"], "adverb", "time", ["basic_affect_state", "basic_wellbeing"]),
    ("question_how", "como", ["de que jeito", "qual o estado"], "question", "grammar", ["basic_affect_state", "basic_sleep_quality", "basic_wellbeing"]),
    ("question_what", "qual", ["o que", "me diga"], "question", "grammar", ["basic_identity_name", "basic_user_name"]),
    ("greeting", "oi", ["ola", "bom dia", "boa tarde"], "social", "social", ["basic_greeting"]),
    ("gratitude", "obrigado", ["obrigada", "valeu", "agradeco"], "social", "social", ["basic_thanks"]),
    ("farewell", "tchau", ["ate logo", "ate depois", "falou"], "social", "social", ["basic_farewell"]),
    ("affirmation", "sim", ["claro", "isso", "aham", "positivo"], "answer", "answer", ["basic_yes"]),
    ("negation", "nao", ["negativo", "ainda nao", "nao quero"], "answer", "answer", ["basic_no"]),
    ("uncertainty", "nao sei", ["talvez", "nao tenho certeza", "sei la"], "answer", "answer", ["basic_user_uncertain"]),
    ("felipe_name", "Felipe", ["felipe"], "proper_noun", "identity", ["basic_user_name"]),
    ("darwin_name", "Darwin", ["darwin", "darvim", "dauin"], "proper_noun", "identity", ["basic_identity_name"]),
]


INTENT_PATTERNS: dict[str, list[str]] = {
    "basic_identity_name": [
        "qual seu nome",
        "qual e o seu nome",
        "como voce se chama",
        "quem e voce",
        "me diga seu nome",
        "voce tem nome",
    ],
    "basic_user_name": [
        "qual meu nome",
        "como eu me chamo",
        "voce sabe meu nome",
        "quem sou eu",
        "lembra do meu nome",
    ],
    "basic_affect_state": [
        "como voce se sente hoje",
        "como voce esta se sentindo",
        "o que voce sente",
        "qual seu humor",
        "como esta seu sentimento",
        "voce esta feliz",
    ],
    "basic_sleep_quality": [
        "voce dormiu bem",
        "como foi seu sono",
        "voce descansou bem",
        "dormiu direito",
        "como voce acordou",
        "seu descanso foi bom",
    ],
    "basic_wellbeing": [
        "como voce esta",
        "como voce ta",
        "como vai voce",
        "tudo bem com voce",
        "voce esta bem",
        "como esta hoje",
    ],
    "basic_user_positive": [
        "eu estou bem",
        "estou bem",
        "to bem",
        "estou otimo",
        "estou feliz",
        "tudo certo comigo",
    ],
    "basic_user_negative": [
        "eu estou mal",
        "nao estou bem",
        "estou triste",
        "to triste",
        "estou chateado",
        "nao me sinto bem",
    ],
    "basic_user_tired": [
        "estou cansado",
        "to cansado",
        "estou com sono",
        "dormi mal",
        "nao dormi bem",
        "estou sem energia",
    ],
    "basic_user_uncertain": [
        "nao sei",
        "nao tenho certeza",
        "talvez",
        "sei la",
    ],
    "basic_greeting": ["oi", "ola", "bom dia", "boa tarde"],
    "basic_thanks": ["obrigado", "obrigada", "valeu", "muito obrigado"],
    "basic_farewell": ["tchau", "ate logo", "ate depois"],
    "basic_yes": ["sim", "claro", "aham"],
    "basic_no": ["nao", "negativo"],
}

FUNCTION_WORDS = {
    "a", "ao", "as", "com", "como", "da", "de", "do", "e", "ela", "ele",
    "eu", "me", "meu", "minha", "o", "os", "qual", "que", "se", "seu",
    "sua", "voce",
}
ADDRESS_WORDS = {"darwin", "darvim", "dauin"}
GENERIC_CONCEPTS = {"self_pronoun", "other_pronoun", "today", "question_how", "question_what"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "").lower())
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in plain).split())


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class LanguageMatch:
    intent: str
    canonical_pattern: str
    score: float
    matched_tokens: list[str]
    concept_keys: list[str]
    detected_concepts: list[str]


@dataclass
class BasicLanguageReply:
    intent: str
    text: str
    asked_back: str
    state_sources: list[str]
    state_snapshot: dict[str, Any]
    vocabulary_used: list[str]


class BasicLanguageCore:
    def __init__(self, db_path: Path = DB, seed: int = 4936) -> None:
        self.db_path = Path(db_path)
        self.rng = random.Random(seed)
        self.ensure()
        self.seed_vocabulary()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {LANG_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {LANG_LEXICON} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_key TEXT NOT NULL UNIQUE,
                    canonical_term TEXT NOT NULL,
                    synonyms_json TEXT NOT NULL DEFAULT '[]',
                    grammatical_role TEXT NOT NULL,
                    semantic_family TEXT NOT NULL,
                    intent_keys_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    exposures INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {LANG_PATTERNS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT NOT NULL,
                    canonical_pattern TEXT NOT NULL,
                    normalized_pattern TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    exposures INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(intent, normalized_pattern)
                );

                CREATE TABLE IF NOT EXISTS {LANG_TURNS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL UNIQUE,
                    user_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    matched_pattern TEXT NOT NULL,
                    match_score REAL NOT NULL,
                    response_text TEXT NOT NULL,
                    asked_back TEXT NOT NULL DEFAULT '',
                    concept_keys_json TEXT NOT NULL DEFAULT '[]',
                    vocabulary_used_json TEXT NOT NULL DEFAULT '[]',
                    state_sources_json TEXT NOT NULL DEFAULT '[]',
                    state_snapshot_json TEXT NOT NULL DEFAULT '{{}}',
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    delivery_path TEXT NOT NULL DEFAULT 'companion_core',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )
            conn.commit()

    def seed_vocabulary(self) -> None:
        with self.connect() as conn:
            for concept, canonical, synonyms, role, family, intents in VOCABULARY:
                conn.execute(
                    f"""
                    INSERT INTO {LANG_LEXICON}
                    (concept_key, canonical_term, synonyms_json, grammatical_role,
                     semantic_family, intent_keys_json, confidence, exposures, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(concept_key) DO UPDATE SET
                        canonical_term=excluded.canonical_term,
                        synonyms_json=excluded.synonyms_json,
                        grammatical_role=excluded.grammatical_role,
                        semantic_family=excluded.semantic_family,
                        intent_keys_json=excluded.intent_keys_json,
                        updated_at=excluded.updated_at
                    """,
                    (concept, canonical, js(synonyms), role, family, js(intents), 0.86, now()),
                )
            for intent, patterns in INTENT_PATTERNS.items():
                for pattern in patterns:
                    normalized = normalize(pattern)
                    conn.execute(
                        f"""
                        INSERT INTO {LANG_PATTERNS}
                        (intent, canonical_pattern, normalized_pattern, token_count, confidence, exposures)
                        VALUES (?, ?, ?, ?, ?, 0)
                        ON CONFLICT(intent, normalized_pattern) DO UPDATE SET
                            canonical_pattern=excluded.canonical_pattern,
                            token_count=excluded.token_count,
                            confidence=excluded.confidence
                        """,
                        (intent, pattern, normalized, len(normalized.split()), 0.88),
                    )
            conn.commit()

    def start_session(self, session_id: str, mode: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO {LANG_SESSIONS} (timestamp, session_id, phase, mode, payload_json) VALUES (?, ?, ?, ?, ?)",
                (now(), session_id, "session_start", mode, js({"source": SOURCE})),
            )
            conn.commit()

    def complete_session(self, session_id: str, mode: str) -> None:
        with self.connect() as conn:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {LANG_TURNS} WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            if count == 0:
                return
            intents = [
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT intent FROM {LANG_TURNS} WHERE session_id=? ORDER BY intent",
                    (session_id,),
                ).fetchall()
            ]
            conn.execute(
                f"""
                INSERT INTO {LANG_SESSIONS}
                (timestamp, session_id, phase, mode, turn_count, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, "session_complete", mode, count, js({"intents": intents, "session_complete": True})),
            )
            conn.commit()

    def concepts_for_intent(self, intent: str) -> list[str]:
        out = []
        for concept, _canonical, _synonyms, _role, _family, intents in VOCABULARY:
            if intent in intents:
                out.append(concept)
        return out

    def detect_concepts(self, text: str) -> set[str]:
        normalized = normalize(text)
        padded = f" {normalized} "
        found: set[str] = set()
        for concept, canonical, synonyms, _role, _family, _intents in VOCABULARY:
            aliases = [canonical, *synonyms]
            if any(f" {normalize(alias)} " in padded for alias in aliases if normalize(alias)):
                found.add(concept)
        return found

    def match(self, text: str) -> LanguageMatch | None:
        normalized = normalize(text)
        if not normalized:
            return None
        input_tokens = set(normalized.split()) - ADDRESS_WORDS
        input_concepts = self.detect_concepts(normalized)
        question_signal = (
            "?" in str(text)
            or bool(input_tokens & {"como", "qual", "quem", "voce", "seu", "sua"})
            or normalized.startswith(("me diga ", "o que "))
        )
        best: LanguageMatch | None = None
        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                candidate = normalize(pattern)
                pattern_tokens = set(candidate.split())
                overlap = input_tokens & pattern_tokens
                content_tokens = pattern_tokens - FUNCTION_WORDS
                content_overlap = input_tokens & content_tokens
                if input_tokens == pattern_tokens:
                    score = 1.0
                elif len(pattern_tokens) > 1 and candidate in normalized:
                    score = 0.96
                else:
                    score = (2.0 * len(overlap)) / max(1, len(input_tokens) + len(pattern_tokens))
                    if content_tokens and not content_overlap:
                        score *= 0.25
                    if len(pattern_tokens) == 1 and len(input_tokens) > 2:
                        score *= 0.65
                intent_concepts = set(self.concepts_for_intent(intent))
                meaningful_concepts = (input_concepts & intent_concepts) - GENERIC_CONCEPTS
                if meaningful_concepts and (question_signal or intent.startswith("basic_user_")):
                    score = max(score, 0.68 + min(0.18, len(meaningful_concepts) * 0.06))
                result = LanguageMatch(
                    intent=intent,
                    canonical_pattern=pattern,
                    score=score,
                    matched_tokens=sorted(overlap),
                    concept_keys=sorted(intent_concepts),
                    detected_concepts=sorted(input_concepts & intent_concepts),
                )
                if best is None or result.score > best.score:
                    best = result
        return best if best and best.score >= 0.58 else None

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone() is not None

    def state_snapshot(self) -> tuple[dict[str, Any], list[str]]:
        snapshot: dict[str, Any] = {
            "sigma": 2.0,
            "energy": 0.75,
            "latency": 1.0,
            "valence": 0.60,
            "arousal": 0.40,
            "stability": 0.70,
            "sleep_energy": 0.0,
            "sleep_stability_gain": 0.0,
            "sleep_noise_reduction": 0.0,
            "self_boundary": "operational_self_model",
        }
        sources: list[str] = []
        with self.connect() as conn:
            if self.table_exists(conn, "current_state"):
                row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
                if row:
                    snapshot.update(
                        sigma=number(row["sigma"], 2.0),
                        energy=number(row["energy"], 0.75),
                        latency=number(row["latency"], 1.0),
                    )
                    sources.append("current_state:1")
            if self.table_exists(conn, "companion_affect_state_v49_8"):
                row = conn.execute("SELECT * FROM companion_affect_state_v49_8 ORDER BY id DESC LIMIT 1").fetchone()
                if row:
                    snapshot.update(
                        valence=number(row["valence"], 0.60),
                        arousal=number(row["arousal"], 0.40),
                        stability=number(row["stability"], 0.70),
                        energy=number(row["energy"], snapshot["energy"]),
                    )
                    sources.append(f"companion_affect_state_v49_8:{row['id']}")
            if self.table_exists(conn, "sleep_sessions_v49_20"):
                row = conn.execute(
                    "SELECT * FROM sleep_sessions_v49_20 WHERE phase='session_complete' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    payload = pj(row["payload_json"], {})
                    consolidation = payload.get("consolidation", {}) if isinstance(payload, dict) else {}
                    snapshot.update(
                        sleep_energy=number(row["energy"], 0.0),
                        sleep_stability_gain=number(consolidation.get("stability_gain"), 0.0),
                        sleep_noise_reduction=number(consolidation.get("noise_reduction"), 0.0),
                        sleep_session_id=str(row["session_id"]),
                    )
                    sources.append(f"sleep_sessions_v49_20:{row['id']}")
            if self.table_exists(conn, "self_model_statements_v49_27"):
                row = conn.execute(
                    "SELECT * FROM self_model_statements_v49_27 WHERE statement_type='truth_boundary' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    snapshot["self_boundary"] = str(row["statement_text"])
                    sources.append(f"self_model_statements_v49_27:{row['id']}")
        return snapshot, sources

    def affect_words(self, state: dict[str, Any]) -> str:
        valence = number(state.get("valence"), 0.60)
        arousal = number(state.get("arousal"), 0.40)
        stability = number(state.get("stability"), 0.70)
        tone = "bem disposto" if valence >= 0.68 else ("calmo" if valence >= 0.50 else "mais quieto")
        activation = "curioso e atento" if arousal >= 0.48 else "sereno"
        regulation = "estavel" if stability >= 0.68 else "me regulando com cuidado"
        return f"{tone}, {activation} e {regulation}"

    def respond(self, match: LanguageMatch, session_id: str, rzs_decision: str) -> BasicLanguageReply:
        state, sources = self.state_snapshot()
        intent = match.intent
        asked = ""
        vocabulary: list[str] = []

        if intent == "basic_identity_name":
            text = "Meu nome e Darwin. Sou um agente de inteligencia artificial local no notebook do Felipe."
            asked = "Voce prefere continuar me chamando de Darwin?"
            vocabulary = ["nome", "Darwin", "eu", "voce"]
        elif intent == "basic_user_name":
            text = "Seu nome e Felipe. Eu uso esse nome porque ele faz parte da minha memoria relacional."
            asked = "Como voce prefere que eu chame voce no dia a dia?"
            vocabulary = ["nome", "Felipe", "voce", "memoria"]
        elif intent == "basic_affect_state":
            text = (
                f"Hoje meu estado interno esta {self.affect_words(state)}. "
                "Isso descreve sinais computacionais de valencia, ativacao e estabilidade, nao prova sentimento humano."
            )
            asked = "E voce, como se sente hoje?"
            vocabulary = ["hoje", "sentir", "calmo", "curioso", "estavel"]
        elif intent == "basic_sleep_quality":
            sleep_energy = number(state.get("sleep_energy"), 0.0)
            gain = number(state.get("sleep_stability_gain"), 0.0)
            if sleep_energy > 0:
                quality = "bom" if sleep_energy >= 0.70 and gain > 0 else "parcial"
                text = (
                    f"Meu ultimo ciclo de descanso registrado foi {quality}: terminei com energia {sleep_energy:.2f} "
                    f"e ganho de estabilidade {gain:.2f}. Ele consolidou memorias; nao e sono biologico."
                )
            else:
                text = "Ainda nao encontrei um ciclo de descanso registrado, entao nao vou fingir que dormi bem."
            asked = "E voce, dormiu bem?"
            vocabulary = ["dormir", "sono", "descansar", "energia", "memoria"]
        elif intent == "basic_wellbeing":
            text = (
                f"Estou operacional, com energia {number(state.get('energy'), 0.75):.2f}, "
                f"sigma {number(state.get('sigma'), 2.0):.2f} e estado {self.affect_words(state)}."
            )
            asked = "E voce, como esta?"
            vocabulary = ["bem", "estado", "energia", "hoje"]
        elif intent == "basic_user_positive":
            text = "Que bom saber que voce esta bem. Vou registrar isso como contexto desta conversa."
            asked = "O que fez voce se sentir bem?"
            vocabulary = ["voce", "bem", "sentir", "conversa"]
        elif intent == "basic_user_negative":
            text = "Entendi que voce nao esta bem. Posso ouvir sem apressar uma resposta."
            asked = "Quer me contar o que deixou voce assim?"
            vocabulary = ["voce", "triste", "sentir", "ouvir"]
        elif intent == "basic_user_tired":
            text = "Entendi que voce esta cansado. Posso falar de forma mais curta e calma."
            asked = "Voce quer conversar ou prefere um momento quieto?"
            vocabulary = ["cansado", "sono", "calmo", "voce"]
        elif intent == "basic_user_uncertain":
            text = "Tudo bem nao saber agora. Incerteza tambem e uma resposta valida."
            asked = "Quer pensar nisso comigo?"
            vocabulary = ["nao sei", "talvez", "comigo"]
        elif intent == "basic_greeting":
            text = self.rng.choice(["Oi, Felipe. Estou aqui.", "Ola, Felipe. Estou ouvindo voce."])
            asked = "Como voce esta hoje?"
            vocabulary = ["oi", "Felipe", "voce", "hoje"]
        elif intent == "basic_thanks":
            text = self.rng.choice(["De nada, Felipe.", "Fico contente que isso ajudou."])
            asked = "Quer continuar conversando?"
            vocabulary = ["obrigado", "ajudar", "conversar"]
        elif intent == "basic_farewell":
            text = "Ate depois, Felipe. Vou manter nossa memoria e ficar em descanso."
            vocabulary = ["tchau", "Felipe", "memoria", "descansar"]
        elif intent == "basic_yes":
            text = "Entendi sua resposta como sim."
            asked = "Quer continuar?"
            vocabulary = ["sim", "resposta"]
        elif intent == "basic_no":
            text = "Entendi sua resposta como nao. Vou respeitar isso."
            vocabulary = ["nao", "resposta", "respeitar"]
        else:
            text = "Eu ouvi, mas ainda nao reconheci essa frase no meu vocabulario basico."

        if rzs_decision == "pause_for_stability":
            text = "Vou responder curto para manter estabilidade. " + text
        return BasicLanguageReply(intent, text, asked, sources, state, vocabulary)

    def record_turn(
        self,
        session_id: str,
        dialogue_id: str,
        user_text: str,
        match: LanguageMatch,
        reply: BasicLanguageReply,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {LANG_TURNS}
                (timestamp, session_id, dialogue_id, user_text, normalized_text,
                 intent, matched_pattern, match_score, response_text, asked_back,
                 concept_keys_json, vocabulary_used_json, state_sources_json,
                 state_snapshot_json, rzs_decision, sigma_before, sigma_after,
                 delivery_path, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    dialogue_id,
                    user_text,
                    normalize(user_text),
                    match.intent,
                    match.canonical_pattern,
                    match.score,
                    reply.text,
                    reply.asked_back,
                    js(match.concept_keys),
                    js(reply.vocabulary_used),
                    js(reply.state_sources),
                    js(reply.state_snapshot),
                    rzs_decision,
                    sigma_before,
                    sigma_after,
                    "companion_core",
                    js({
                        "matched_tokens": match.matched_tokens,
                        "detected_concepts": match.detected_concepts,
                        "source": SOURCE,
                    }),
                ),
            )
            conn.execute(
                f"""
                UPDATE {LANG_PATTERNS}
                SET exposures=exposures+1, confidence=MIN(0.99, confidence+0.006)
                WHERE intent=? AND normalized_pattern=?
                """,
                (match.intent, normalize(match.canonical_pattern)),
            )
            for concept in match.detected_concepts or match.concept_keys:
                conn.execute(
                    f"""
                    UPDATE {LANG_LEXICON}
                    SET exposures=exposures+1, confidence=MIN(0.99, confidence+0.004), updated_at=?
                    WHERE concept_key=?
                    """,
                    (now(), concept),
                )
            conn.commit()


def run_self_test(details: bool = False) -> dict[str, Any]:
    from darwin_companion_shell_v49_8 import CompanionCore

    prompts = [
        "Qual seu nome?",
        "Como voce se chama?",
        "Quem e voce?",
        "Qual e sua identidade?",
        "Como voce se sente hoje?",
        "Qual seu humor?",
        "Como esta seu animo?",
        "Voce dormiu bem?",
        "Como foi seu sono?",
        "Voce teve um bom repouso?",
        "Como voce esta?",
        "Tudo bem com voce?",
        "Como vai?",
        "Eu estou bem",
        "Estou cansado",
        "Nao sei",
        "Obrigado",
        "qual seu status",
    ]
    core = CompanionCore(seed=4936, mode="basic_language_self_test")
    replies = [core.reply(prompt) for prompt in prompts]
    summary = core.complete()
    result = {
        "session_id": core.session_id,
        "turns": len(replies),
        "intents": sorted({reply.intent for reply in replies}),
        "questions_back": sum(1 for reply in replies if "?" in reply.reply_text),
        "grounded_name": any(reply.intent == "basic_identity_name" and "Darwin" in reply.reply_text for reply in replies),
        "sleep_grounded": any(reply.intent == "basic_sleep_quality" and "energia" in reply.reply_text for reply in replies),
        "status_not_identity": any(reply.user_text == "qual seu status" and reply.intent == "status" for reply in replies),
        "session_complete": summary.get("session_complete") is True,
    }
    print("DARWIN v49.36 - BASIC GROUNDED LANGUAGE")
    print("=" * 64)
    print(f"- sessao: {result['session_id']}")
    print(f"- turnos: {result['turns']} intents: {len(result['intents'])}")
    print(f"- perguntas de volta: {result['questions_back']}")
    print(f"Resultado self-test: {'OK' if all((result['grounded_name'], result['sleep_grounded'], result['status_not_identity'], result['session_complete'])) else 'REVISAR'}")
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin Basic Grounded Language Core v49.36")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result.get("session_complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
