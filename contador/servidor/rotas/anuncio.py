"""Rota /api/anuncio: a faixa de publicidade do topo."""
from contador.servidor import estado


def faixa_de_anuncio(consulta):
    return 200, estado.ANUNCIO
