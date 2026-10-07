"""Passphrase, sessioni e protezione dei moduli (CSRF)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSPHRASE = 15
COOKIE_SESSIONE = "minuta_sessione"
COOKIE_CSRF = "minuta_csrf"
DURATA_MODULO = 3600  # un modulo resta valido per un'ora

_hasher = PasswordHasher()  # Argon2id con i parametri consigliati


# [libro:passphrase]
def hash_passphrase(passphrase: str) -> str:
    """Trasforma la passphrase in un hash: il testo originale non si salva."""
    if len(passphrase) < MIN_PASSPHRASE:
        raise ValueError(
            f"La passphrase deve avere almeno {MIN_PASSPHRASE} caratteri"
        )
    return _hasher.hash(passphrase)


def verifica_passphrase(hash_salvato: str, passphrase: str) -> bool:
    """Vero solo se la passphrase corrisponde all'hash salvato."""
    try:
        return _hasher.verify(hash_salvato, passphrase)
    except (VerificationError, InvalidHashError):
        return False


# Se l'utente non esiste verifichiamo comunque una passphrase su questo hash:
# la risposta impiega circa lo stesso tempo e non rivela chi è registrato.
HASH_FITTIZIO = _hasher.hash(secrets.token_urlsafe(24))
# [/libro:passphrase]


def nuovo_gettone() -> str:
    """Un valore casuale e imprevedibile: è il contenuto del cookie."""
    return secrets.token_urlsafe(32)


def impronta(valore: str) -> str:
    """Nel database salviamo solo l'impronta del valore, non il valore."""
    return hashlib.sha256(valore.encode("utf-8")).hexdigest()


def gettone_csrf(
    segreto: str, cookie: str, legame: str, ora: float | None = None
) -> str:
    """Firma un permesso di invio legato al browser e alla sessione."""
    emesso = str(int(time.time() if ora is None else ora))
    return f"{emesso}.{_firma(segreto, cookie, legame, emesso)}"


def csrf_valido(
    segreto: str,
    cookie: str,
    legame: str,
    gettone: str,
    ora: float | None = None,
) -> bool:
    """Controlla firma, legame con la sessione e scadenza del modulo."""
    emesso, _, firma = gettone.partition(".")
    if not (emesso.isascii() and emesso.isdigit()) or not firma:
        return False
    eta = (time.time() if ora is None else ora) - int(emesso)
    if eta < 0 or eta > DURATA_MODULO:
        return False
    attesa = _firma(segreto, cookie, legame, emesso)
    return hmac.compare_digest(firma, attesa)


def _firma(segreto: str, cookie: str, legame: str, emesso: str) -> str:
    messaggio = f"{cookie}|{legame}|{emesso}".encode()
    return hmac.new(
        segreto.encode("utf-8"), messaggio, hashlib.sha256
    ).hexdigest()


def legame_sessione(cookie_sessione: str | None) -> str:
    """A che cosa è legato un modulo: alla sessione, o a nessuna."""
    return impronta(cookie_sessione) if cookie_sessione else "anonimo"
