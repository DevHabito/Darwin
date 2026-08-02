"""Offline TTY broker that keeps the consent private key out of Darwin."""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .asymmetric_consent import (
    Ed25519ConsentReceiptSigner,
    public_key_fingerprint,
)
from .consent import (
    INTERACTIVE_TTY_CHANNEL,
    ConsentError,
    ConsentReceipt,
    ConsentRequest,
    InteractiveConsentGate,
)
from .models import ValidationError, canonical_json


MAX_BROKER_FILE_BYTES = 256 * 1024
MIN_PASSPHRASE_BYTES = 16


class ConsentBrokerError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validated_passphrase(passphrase: bytes) -> bytes:
    if (
        not isinstance(passphrase, bytes)
        or len(passphrase) < MIN_PASSPHRASE_BYTES
        or b"\0" in passphrase
    ):
        raise ConsentBrokerError("broker_passphrase_too_weak")
    return passphrase


def _resolved_new_target(path: str | Path) -> Path:
    target = Path(path)
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as exc:
        raise ConsentBrokerError("broker_target_parent_unavailable") from exc
    if not parent.is_dir():
        raise ConsentBrokerError("broker_target_parent_not_directory")
    resolved = parent / target.name
    if resolved.exists() or resolved.is_symlink():
        raise ConsentBrokerError("broker_target_exists")
    return resolved


def _write_new_file(path: str | Path, data: bytes, *, private: bool) -> Path:
    target = _resolved_new_target(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(target, flags, 0o600 if private else 0o644)
    except FileExistsError as exc:
        raise ConsentBrokerError("broker_target_exists") from exc
    except OSError as exc:
        raise ConsentBrokerError("broker_target_create_failed") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if private and os.name != "nt":
            os.chmod(target, 0o600)
    except BaseException:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    return target


def _read_limited(path: str | Path) -> bytes:
    try:
        target = Path(path).resolve(strict=True)
    except OSError as exc:
        raise ConsentBrokerError("broker_input_unavailable") from exc
    if not target.is_file():
        raise ConsentBrokerError("broker_input_not_file")
    size = target.stat().st_size
    if size > MAX_BROKER_FILE_BYTES:
        raise ConsentBrokerError("broker_input_too_large")
    data = target.read_bytes()
    if len(data) > MAX_BROKER_FILE_BYTES:
        raise ConsentBrokerError("broker_input_too_large")
    return data


def _strict_json_object(data: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ConsentBrokerError("broker_json_duplicate_key")
            value[key] = item
        return value

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsentBrokerError("broker_json_invalid") from exc
    if not isinstance(value, dict):
        raise ConsentBrokerError("broker_json_not_object")
    return value


def generate_encrypted_keypair(
    *,
    private_key_path: str | Path,
    public_key_path: str | Path,
    passphrase: bytes,
) -> str:
    passphrase = _validated_passphrase(passphrase)
    private_target = _resolved_new_target(private_key_path)
    public_target = _resolved_new_target(public_key_path)
    if private_target == public_target:
        raise ConsentBrokerError("broker_key_paths_identical")

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    written_private: Path | None = None
    try:
        written_private = _write_new_file(
            private_target,
            private_pem,
            private=True,
        )
        _write_new_file(public_target, public_pem, private=False)
    except BaseException:
        if written_private is not None:
            written_private.unlink(missing_ok=True)
        raise
    return public_key_fingerprint(public_key)


def load_private_key(
    path: str | Path,
    *,
    passphrase: bytes,
) -> Ed25519PrivateKey:
    passphrase = _validated_passphrase(passphrase)
    try:
        key = serialization.load_pem_private_key(
            _read_limited(path),
            password=passphrase,
        )
    except (TypeError, UnsupportedAlgorithm, ValueError) as exc:
        raise ConsentBrokerError("broker_private_key_invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ConsentBrokerError("broker_private_key_not_ed25519")
    return key


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(_read_limited(path))
    except (TypeError, UnsupportedAlgorithm, ValueError) as exc:
        raise ConsentBrokerError("broker_public_key_invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ConsentBrokerError("broker_public_key_not_ed25519")
    return key


def export_consent_request(
    path: str | Path,
    request: ConsentRequest,
) -> Path:
    return _write_new_file(
        path,
        (canonical_json(request.to_dict()) + "\n").encode("utf-8"),
        private=False,
    )


def load_consent_request(path: str | Path) -> ConsentRequest:
    try:
        return ConsentRequest.from_dict(_strict_json_object(_read_limited(path)))
    except ValidationError as exc:
        raise ConsentBrokerError("broker_request_invalid") from exc


def export_consent_receipt(
    path: str | Path,
    receipt: ConsentReceipt,
) -> Path:
    return _write_new_file(
        path,
        (canonical_json(receipt.to_dict()) + "\n").encode("utf-8"),
        private=False,
    )


def load_consent_receipt(path: str | Path) -> ConsentReceipt:
    try:
        return ConsentReceipt.from_dict(_strict_json_object(_read_limited(path)))
    except ValidationError as exc:
        raise ConsentBrokerError("broker_receipt_invalid") from exc


def _read_passphrase(prompt: str) -> bytes:
    if not sys.stdin.isatty():
        raise ConsentBrokerError("broker_tty_required")
    return getpass(prompt).encode("utf-8")


def _keygen(args: argparse.Namespace) -> int:
    first = _read_passphrase("Nova frase secreta do broker: ")
    second = _read_passphrase("Repita a frase secreta: ")
    if first != second:
        raise ConsentBrokerError("broker_passphrases_differ")
    fingerprint = generate_encrypted_keypair(
        private_key_path=args.private_key,
        public_key_path=args.public_key,
        passphrase=first,
    )
    sys.stdout.write(f"Chave criada. Fingerprint: {fingerprint}\n")
    return 0


def _sign(args: argparse.Namespace) -> int:
    private_key = load_private_key(
        args.private_key,
        passphrase=_read_passphrase("Frase secreta do broker: "),
    )
    signer = Ed25519ConsentReceiptSigner(
        issuer=args.issuer,
        private_key=private_key,
        channel=INTERACTIVE_TTY_CHANNEL,
    )
    if signer.fingerprint != args.expected_fingerprint:
        raise ConsentBrokerError("broker_key_fingerprint_mismatch")
    request = load_consent_request(args.request)
    gate = InteractiveConsentGate(signer, require_tty=True)
    receipt = gate.decide(request)
    export_consent_receipt(args.receipt, receipt)
    sys.stdout.write(
        f"Decisão registrada em {Path(args.receipt)}; "
        f"aprovado={str(receipt.approved).lower()}\n"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autoridade externa de consentimento Darwin v50"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    keygen = subparsers.add_parser("keygen")
    keygen.add_argument("--private-key", required=True)
    keygen.add_argument("--public-key", required=True)
    keygen.set_defaults(handler=_keygen)

    sign = subparsers.add_parser("sign")
    sign.add_argument("--issuer", required=True)
    sign.add_argument("--private-key", required=True)
    sign.add_argument("--expected-fingerprint", required=True)
    sign.add_argument("--request", required=True)
    sign.add_argument("--receipt", required=True)
    sign.set_defaults(handler=_sign)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        return int(args.handler(args))
    except (ConsentBrokerError, ConsentError, ValidationError) as exc:
        code = (
            exc.code
            if isinstance(exc, (ConsentBrokerError, ConsentError))
            else "validation_failed"
        )
        sys.stderr.write(f"broker recusou a operação: {code}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
