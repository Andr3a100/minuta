"""I percorsi comuni alle prove del pilota.

Stanno qui e non in conftest.py: le prove dell'applicazione, in tests/app,
hanno un conftest.py loro, e un import da «conftest» troverebbe quello.
"""

from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
