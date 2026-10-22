"""Pastas do projeto, achadas a partir deste arquivo (valem no Docker e fora dele)."""
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"  # tudo que o navegador recebe: página, estilo, scripts, service worker e desenhos
