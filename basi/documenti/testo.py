"""Il testo di un documento, PDF o Word: lezione B8.

    python testo.py decreto.pdf
"""

import sys
from pathlib import Path

percorso = Path(sys.argv[1])
if percorso.suffix.lower() == ".pdf":
    import pymupdf

    with pymupdf.open(percorso) as documento:
        testo = "\n".join(pagina.get_text() for pagina in documento).strip()
elif percorso.suffix.lower() == ".docx":
    import docx

    testo = "\n".join(p.text for p in docx.Document(percorso).paragraphs).strip()
else:
    sys.exit(f"{percorso.name}: formato non previsto")
print(testo or f"{percorso.name}: nessun testo da leggere, solo immagini")
