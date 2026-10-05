"""Trasforma gli atti di prova (testo) in PDF, come quelli di un archivio vero.

    .venv/bin/python strumenti/genera_pdf.py

Ogni riga del sorgente è un paragrafo; le righe vuote sono solo spazio.
"""

from html import escape
from pathlib import Path

import pymupdf

RADICE = Path(__file__).resolve().parents[1]
CSS = """
p { font-family: serif; font-size: 11pt; line-height: 1.35;
    margin-top: 0; margin-bottom: 7pt; text-align: justify; }
"""


def genera(sorgente: Path, uscita: Path) -> None:
    righe = [r.strip() for r in sorgente.read_text("utf-8").splitlines()]
    html = "".join(f"<p>{escape(r)}</p>" for r in righe if r)
    storia = pymupdf.Story(html=html, user_css=CSS)
    scrittore = pymupdf.DocumentWriter(str(uscita))
    pagina = pymupdf.paper_rect("a4")
    area = pagina + (72, 72, -72, -72)
    altro = True
    while altro:
        dispositivo = scrittore.begin_page(pagina)
        altro, _ = storia.place(area)
        storia.draw(dispositivo)
        scrittore.end_page()
    scrittore.close()


if __name__ == "__main__":
    for sorgente in sorted((RADICE / "archivio/sorgenti").glob("*.txt")):
        uscita = RADICE / "archivio/pdf" / (sorgente.stem + ".pdf")
        genera(sorgente, uscita)
        print(uscita.relative_to(RADICE))
