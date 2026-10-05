"""Operator-owned keys: native OS storage or process memory; never plaintext files."""

from __future__ import annotations

import os
import threading

_LOCK = threading.RLock()
_SESSION: dict[str, str] = {}
PROVIDERS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "morpheus": "MORPHEUS_API_KEY",
}


def _local_env_value(name):
    """Read only named local values; never inject arbitrary entries into process env."""
    if name not in {"MORPHEUS_API_KEY", "MORPHEUS_BASE_URL"}:
        return None
    from frictionlab.configuration import ROOT

    path = ROOT / ".env"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.partition("=")[2].strip()
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def _local_env_key(provider):
    if provider != "morpheus":
        return None
    value = _local_env_value("MORPHEUS_API_KEY")
    return validate_key(provider, value) if value else None


def morpheus_base_url():
    value = os.environ.get("MORPHEUS_BASE_URL") or _local_env_value("MORPHEUS_BASE_URL")
    if value and value.rstrip("/") != "https://api.mor.org/api/v1":
        raise ValueError("Morpheus base URL must be the documented HTTPS endpoint")
    return "https://api.mor.org/api/v1"


def validate_key(provider, value):
    if (
        provider not in PROVIDERS
        or not isinstance(value, str)
        or not 8 <= len(value) <= 4096
        or any(c.isspace() for c in value)
    ):
        raise ValueError(
            "Choose a supported provider and enter a valid key; its value is not displayed."
        )
    return value


def secure_backend():
    # Select core native backends explicitly: no configurable/third-party plaintext fallback.
    import sys

    if sys.platform == "win32":
        from keyring.backends.Windows import WinVaultKeyring

        backend = WinVaultKeyring()
    elif sys.platform == "darwin":
        from keyring.backends.macOS import Keyring

        backend = Keyring()
    else:
        from keyring.backends.SecretService import Keyring

        backend = Keyring()
    if backend.priority <= 0:
        raise ValueError("Native credential storage is unavailable; use session-only mode.")
    return backend


def storage_available():
    try:
        secure_backend()
        return True
    except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
        return False


def save_key(provider, value, *, remember=False):
    value = validate_key(provider, value)
    with _LOCK:
        if remember:
            try:
                secure_backend().set_password("FrictionLab", provider, value)
            except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
                raise ValueError(
                    "Secure key storage failed. Nothing was written to a plaintext file; choose session-only mode."
                ) from None
        _SESSION[provider] = value


def get_key(provider):
    if provider not in PROVIDERS:
        return None
    with _LOCK:
        environment_value = os.environ.get(PROVIDERS[provider])
        if environment_value:
            return validate_key(provider, environment_value)
        value = _SESSION.get(provider) or _local_env_key(provider)
        if not value:
            try:
                value = secure_backend().get_password("FrictionLab", provider)
            except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
                value = None
        if value:
            validate_key(provider, value)
            _SESSION[provider] = value
        return value


def forget_key(provider):
    if provider not in PROVIDERS:
        raise ValueError("Unsupported provider")
    with _LOCK:
        _SESSION.pop(provider, None)
        try:
            backend = secure_backend()
            if backend.get_password("FrictionLab", provider):
                backend.delete_password("FrictionLab", provider)
        except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
            raise ValueError(
                "Could not verify removal from the native credential store; remove it there directly."
            ) from None


def known_keys():
    with _LOCK:
        return tuple(_SESSION.values())
