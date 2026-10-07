"""Il punto d'ingresso per Uvicorn: python -m uvicorn app.main:app

app.main:app significa: importa il modulo app.main e usa l'oggetto app.
La configurazione si legge una volta sola, all'avvio del processo.
"""

from .factory import create_app

app = create_app()
