"""Consulta HTTP a um arquivo do TSE, com ETag e gzip."""
import gzip
import json
import urllib.error
import urllib.request
from collections import namedtuple


# O TSE bloqueia o IP por 10 minutos ao passar de 100 req/s e após muitos 404 seguidos.
ESPERA_BLOQUEIO = 600
ESPERA_MAXIMA_ERRO = 120

Resposta = namedtuple("Resposta", "status dados etag")


def buscar(url, etag=None):
    cabecalhos = {"Accept-Encoding": "gzip", "User-Agent": "contador-votos/1.0"}
    if etag:
        cabecalhos["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=cabecalhos), timeout=20
        ) as resp:
            corpo = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                corpo = gzip.decompress(corpo)
            return Resposta(resp.status, json.loads(corpo), resp.headers.get("ETag"))
    except urllib.error.HTTPError as erro:  # inclui 304 Not Modified
        return Resposta(erro.code, None, etag)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Resposta(0, None, etag)
