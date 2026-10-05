"""Pseudonimizzazione reversibile: prima di ogni invio al fornitore del modello.

Nomi, società, codici fiscali, partite IVA, indirizzi, PEC e IBAN diventano
segnaposto come [PERSONA_1] o [SOGGETTO_2]. La tabella che li ricollega ai
valori veri non lascia mai lo studio, e la risposta del modello si ricompone
in locale.

Attenzione: un testo pseudonimizzato contiene ancora dati personali. Chi ha
la tabella può tornare indietro, e un fatto raro può identificare una persona
anche senza nome. La pseudonimizzazione riduce il rischio; non toglie gli
obblighi del GDPR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAIUSCOLA = "A-ZÀ-ÖØ-Ý"
MINUSCOLA = "a-zà-öø-ÿ"
NOME = rf"[{MAIUSCOLA}][{MINUSCOLA}'’]+"
NOME_MAIUSCOLO = rf"[{MAIUSCOLA}]{{2,}}"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN = re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b")
CODICE_FISCALE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
PARTITA_IVA = re.compile(r"(?:P\.\s?IVA|partita IVA)\s*:?\s*(\d{11})", re.I)
INDIRIZZO = re.compile(
    rf"\b(?:Via|Viale|Corso|Piazza|Piazzale|Largo|Vicolo|Strada)\s+"
    rf"(?:[\w'’]+\s){{0,4}}?[\w'’]+\s+\d+[A-Za-z]?(?:,\s*interno\s*\d+)?")
FORMA = (r"(?:S\.r\.l\.|S\.R\.L\.|S\.p\.A\.|S\.P\.A\.|S\.n\.c\.|S\.N\.C\.|S\.a\.s\.|S\.A\.S\.)"
         rf"(?:\s+(?:di|DI)\s+(?:{NOME}|{NOME_MAIUSCOLO})(?:\s+(?:{NOME}|{NOME_MAIUSCOLO}))*\s*&\s*C\.)?")
SOCIETA = re.compile(rf"(?:(?:{NOME}|{NOME_MAIUSCOLO}|&) ){{1,6}}{FORMA}")
STUDIO_ASSOCIATO = re.compile(rf"Studio Associato (?:(?:{NOME}|&) ?){{1,6}}")
PERSONA_CON_CF = re.compile(
    rf"((?:{NOME}|{NOME_MAIUSCOLO})(?: (?:{NOME}|{NOME_MAIUSCOLO})){{1,3}}) ?\(C\.F\.")
PERSONA_CON_TITOLO = re.compile(
    rf"(?:sig\.ra|sig\.|ing\.|dott\.ssa|dott\.|geom\.|[Aa]vv\.) "
    rf"((?:{NOME}|{NOME_MAIUSCOLO})(?: (?:{NOME}|{NOME_MAIUSCOLO})){{1,2}})")
PERSONA_CON_RUOLO = re.compile(
    rf"(?:amministratore unico|amministratrice unica|legale rappresentante|"
    rf"socio amministratore|Il sottoscritto|La sottoscritta) "
    rf"(?:pro tempore )?(?:(?:sig\.ra|sig\.|ing\.) )?({NOME} {NOME})")

# Parole che compaiono nei nomi delle società ma da sole non identificano
# nessuno: «Imballaggi», «Logistica», un aggettivo geografico.
GENERICHE = {
    "officine", "meccaniche", "logistica", "imballaggi", "supermercati",
    "termoidraulica", "costruzioni", "tipografia", "agenzia", "eventi",
    "impianti", "mobilificio", "ferramenta", "edil", "gastronomia", "studio",
    "associato", "commercialisti", "soluzioni", "emiliana", "frignano", "di",
    "del", "della", "e", "&",
}
FORME = re.compile(rf"\s*{FORMA}$")


@dataclass
class Pseudonimizzatore:
    """Una tabella di segnaposto, per un testo o per un fascicolo intero.

    prefisso distingue i fascicoli: gli esempi presi dall'archivio usano
    [E1_...], [E2_...], così un loro segnaposto finito per errore nella bozza
    di un altro cliente si riconosce e non viene mai ricomposto.
    """

    prefisso: str = ""
    noti: dict[str, str] = field(default_factory=dict)  # valore -> tipo
    generico: bool = False  # segnaposto senza numero, per il profilo dello studio
    tabella: dict[str, str] = field(default_factory=dict)  # segnaposto -> valore
    _valori: dict[str, str] = field(default_factory=dict)  # valore -> segnaposto
    _contatori: dict[str, int] = field(default_factory=dict)

    def segnaposto(self, valore: str, tipo: str) -> str:
        if self.generico:
            return f"[{tipo}]"
        if valore in self._valori:
            return self._valori[valore]
        self._contatori[tipo] = self._contatori.get(tipo, 0) + 1
        etichetta = f"[{self.prefisso}{tipo}_{self._contatori[tipo]}]"
        self._valori[valore] = etichetta
        self.tabella[etichetta] = valore
        return etichetta

    def trova(self, testo: str) -> list[tuple[str, str]]:
        """I valori da nascondere, con il loro tipo, dal più lungo al più corto."""
        trovati: dict[str, str] = dict(self.noti)
        for m in EMAIL.finditer(testo):
            trovati[m.group(0)] = "EMAIL"
        for m in IBAN.finditer(testo):
            trovati[m.group(0)] = "IBAN"
        for m in CODICE_FISCALE.finditer(testo):
            trovati[m.group(0)] = "CF"
        for m in PARTITA_IVA.finditer(testo):
            trovati[m.group(1)] = "PIVA"
        for m in INDIRIZZO.finditer(testo):
            trovati[m.group(0)] = "INDIRIZZO"
        soggetti = [m.group(0).strip() for m in SOCIETA.finditer(testo)]
        soggetti += [m.group(0).strip() for m in STUDIO_ASSOCIATO.finditer(testo)]
        for soggetto in soggetti:
            soggetto = re.sub(r"^(?:Per|contro|Spett\.le)\s*:?\s*", "", soggetto)
            trovati.setdefault(soggetto, "SOGGETTO")
            senza_forma = FORME.sub("", soggetto).strip()
            if senza_forma and senza_forma != soggetto:
                trovati.setdefault(senza_forma, "SOGGETTO")
            for parola in re.findall(rf"{NOME}|{NOME_MAIUSCOLO}", senza_forma):
                if parola.lower() not in GENERICHE:
                    trovati.setdefault(parola, "SOGGETTO")
        persone = []
        for regola in (PERSONA_CON_CF, PERSONA_CON_TITOLO, PERSONA_CON_RUOLO):
            persone += [m.group(1) for m in regola.finditer(testo)]
        for persona in persone:
            trovati.setdefault(persona, "PERSONA")
            parti = persona.split()
            trovati.setdefault(" ".join(reversed(parti)), "PERSONA")
            for parte in parti:
                if parte.lower() not in GENERICHE:
                    trovati.setdefault(parte, "PERSONA")
        return sorted(trovati.items(), key=lambda kv: -len(kv[0]))

    def nascondi(self, testo: str) -> str:
        for valore, tipo in self.trova(testo):
            schema = re.escape(valore)
            if re.match(r"\w", valore):
                schema = r"(?<![\w\[])" + schema
            if re.search(r"\w$", valore):
                schema += r"(?![\w\]])"
            # Ogni modo di scriverlo («BASSI», «Bassi») ha il suo segnaposto:
            # così la bozza ricomposta è identica, maiuscole comprese.
            testo = re.sub(schema, lambda m: self.segnaposto(m.group(0), tipo),
                           testo, flags=re.I)
        return testo

    def ricomponi(self, testo: str) -> str:
        """Rimette i valori veri, ma solo i segnaposto di questa tabella."""
        for segno, valore in sorted(self.tabella.items(), key=lambda kv: -len(kv[0])):
            testo = testo.replace(segno, valore)
        return testo


def segnaposto_estranei(testo: str, prefisso: str = "") -> list[str]:
    """Segnaposto che non appartengono al fascicolo: contaminazione fra clienti."""
    tutti = re.findall(r"\[[A-Z0-9_]+_\d+\]", testo)
    return sorted({s for s in tutti if not re.match(rf"\[{re.escape(prefisso)}[A-Z]+_\d+\]$", s)})
