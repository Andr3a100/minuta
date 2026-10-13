"""L'addestramento in locale (lezione 30): un modello aperto, sul server
dello studio, con l'insieme della lezione 28.

Il modello di base è Qwen2.5-0.5B, licenza Apache 2.0, in una revisione
fissata: lo stesso file a ogni prova. Non si riscrive il modello: gli si
affianca un adattatore (LoRA), pochi milioni di numeri che restano in
dati/modelli/, dello studio. Un atto resta fuori dall'addestramento, e la
misura vera si fa su quello: misurare sugli atti con cui si è addestrato
direbbe soltanto che il modello li ha imparati a memoria.

La misura è la perplessità: quanto il testo sorprende il modello. Più è
bassa, più gli sembra un testo che avrebbe potuto scrivere lui.

    python -m minuta.addestra dati/addestramento/sarti.jsonl \
        --fuori archivio-10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

MODELLO = "Qwen/Qwen2.5-0.5B"
REVISIONE = "060db6499f32faf8b98477b0a26969ef7d8b9987"
LUNGHEZZA = 256  # token per pezzo
PASSATE = 3
PASSO = 2e-4
SEME = 30


class InsiemeNonValido(Exception):
    """L'insieme non basta per addestrare e misurare: il messaggio dice
    perché."""


def leggi_insieme(percorso: Path) -> list[dict]:
    return [
        json.loads(r) for r in percorso.read_text("utf-8").splitlines() if r
    ]


# [libro:dividi]
def dividi(righe: list[dict], fuori: str) -> tuple[list[str], list[str]]:
    """I testi per addestrare e quello per misurare: l'atto tenuto fuori
    non si vede mai durante l'addestramento."""
    atti = [r["atto"] for r in righe]
    if fuori not in atti:
        raise InsiemeNonValido(f"Nell'insieme non c'è {fuori}.")
    if len(atti) < 2:
        raise InsiemeNonValido("Servono almeno due atti: uno resta fuori.")
    dentro = [r["testo"] for r in righe if r["atto"] != fuori]
    return dentro, [r["testo"] for r in righe if r["atto"] == fuori]


# [/libro:dividi]


def pezzi(ids: list[int], lunghezza: int = LUNGHEZZA) -> list[list[int]]:
    """Un testo lungo in pezzi della stessa lunghezza; l'ultimo, se è troppo
    corto per insegnare qualcosa, si unisce al precedente."""
    divisi = [ids[i : i + lunghezza] for i in range(0, len(ids), lunghezza)]
    if len(divisi) > 1 and len(divisi[-1]) < lunghezza // 4:
        ultimo = divisi.pop()
        divisi[-1] += ultimo
    return divisi


def perplessita(perdite: list[tuple[float, int]]) -> float:
    """Dalla perdita media di ogni pezzo, pesata per i suoi token."""
    token = sum(n for _, n in perdite)
    return math.exp(sum(p * n for p, n in perdite) / token)


def _misura(modello, tokenizer, testi: list[str]) -> float:
    import torch

    perdite = []
    modello.eval()
    with torch.no_grad():
        for testo in testi:
            for pezzo in pezzi(tokenizer(testo)["input_ids"]):
                ids = torch.tensor([pezzo])
                perdita = modello(input_ids=ids, labels=ids).loss.item()
                perdite.append((perdita, len(pezzo) - 1))
    return perplessita(perdite)


def addestra(insieme: Path, fuori: str, cartella: Path) -> dict:
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(SEME)
    torch.use_deterministic_algorithms(True)
    righe = leggi_insieme(insieme)
    dentro, tenuto = dividi(righe, fuori)
    tokenizer = AutoTokenizer.from_pretrained(MODELLO, revision=REVISIONE)
    modello = AutoModelForCausalLM.from_pretrained(
        MODELLO, revision=REVISIONE, dtype=torch.float32
    )
    prima = (
        _misura(modello, tokenizer, dentro),
        _misura(modello, tokenizer, tenuto),
    )
    lora = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.0,
        target_modules=["q_proj", "v_proj"],
        task_type="CAUSAL_LM",
    )
    modello = get_peft_model(modello, lora)
    addestrabili = sum(
        p.numel() for p in modello.parameters() if p.requires_grad
    )
    totali = sum(p.numel() for p in modello.parameters())
    lotti = [p for t in dentro for p in pezzi(tokenizer(t)["input_ids"])]
    ottimizzatore = torch.optim.AdamW(
        [p for p in modello.parameters() if p.requires_grad], lr=PASSO
    )
    modello.train()
    for _ in range(PASSATE):
        for pezzo in lotti:
            ids = torch.tensor([pezzo])
            modello(input_ids=ids, labels=ids).loss.backward()
            ottimizzatore.step()
            ottimizzatore.zero_grad()
    dopo = (
        _misura(modello, tokenizer, dentro),
        _misura(modello, tokenizer, tenuto),
    )
    cartella.mkdir(parents=True, exist_ok=True)
    modello.save_pretrained(cartella)
    peso = sum(f.stat().st_size for f in cartella.iterdir())
    return {
        "quando": datetime.now(UTC).isoformat(timespec="seconds"),
        "modello": MODELLO,
        "revisione": REVISIONE,
        "insieme": insieme.as_posix(),
        "impronta": hashlib.sha256(insieme.read_bytes()).hexdigest(),
        "atti": len(righe),
        "fuori": fuori,
        "pezzi": len(lotti),
        "passate": PASSATE,
        "addestrabili": addestrabili,
        "totali": totali,
        "perplessita": {
            "addestramento": [round(prima[0], 1), round(dopo[0], 1)],
            "fuori": [round(prima[1], 1), round(dopo[1], 1)],
        },
        "adattatore": cartella.as_posix(),
        "byte_adattatore": peso,
    }


def resoconto(esito: dict) -> list[str]:
    p = esito["perplessita"]
    quota = esito["addestrabili"] / esito["totali"] * 100
    numeri = f"{esito['addestrabili']:,}".replace(",", ".")
    insieme = f"L'insieme: {esito['insieme']}, {esito['atti']} atti"
    modello = f"Il modello: {esito['modello']}, revisione"
    pezzi_ = f"{esito['pezzi']} pezzi da {LUNGHEZZA} token"
    mega = esito["byte_adattatore"] / 1_000_000
    return [
        f"{insieme}; tenuto fuori: {esito['fuori']}.",
        f"{modello} {esito['revisione'][:12]}, su questa macchina.",
        (
            f"Addestramento: {esito['atti'] - 1} atti, {pezzi_}, "
            f"{esito['passate']} passate."
        ),
        f"L'adattatore: {numeri} numeri, lo {quota:.2f}% del modello.",
        "Perplessità, prima e dopo:",
        (
            f"  sugli atti dell'addestramento  {p['addestramento'][0]:>6} → "
            f"{p['addestramento'][1]:>6}"
        ),
        (
            f"  sull'atto tenuto fuori         {p['fuori'][0]:>6} → "
            f"{p['fuori'][1]:>6}"
        ),
        (
            f"Salvato in {esito['adattatore']}/, {mega:.1f} MB; il modello "
            "di base resta com'era."
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m minuta.addestra")
    parser.add_argument("insieme", type=Path)
    parser.add_argument("--fuori", required=True, help="l'atto per misurare")
    parser.add_argument("--verbale", type=Path, help="il verbale, in JSON")
    args = parser.parse_args(argv)
    cartella = Path("dati/modelli") / args.insieme.stem
    try:
        esito = addestra(args.insieme, args.fuori, cartella)
    except InsiemeNonValido as errore:
        print(errore, file=sys.stderr)
        return 1
    righe = resoconto(esito)
    print("\n".join(righe))
    if args.verbale:
        esito["stampa"] = "\n".join(righe)
        args.verbale.write_text(
            json.dumps(esito, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
