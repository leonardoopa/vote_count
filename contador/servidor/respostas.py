"""Peças que várias rotas usam para montar a resposta: erro do TSE, cidades da UF e respostas prontas."""
import threading
import time

from contador.recursos import mapa
from contador.servidor import estado
from contador.tse import catalogo, leitura
from contador.tse.cache import TTL_MUNICIPIOS

# Uma resposta pronta por seleção: vários visitantes dividem o mesmo mapa em vez de cada um abrir
# a sua rodada de consultas (são 29 arquivos por rodada). Poucas chaves: ambiente x cargo x turno.
TTL_RESPOSTA_MAPA = 5
_PRONTAS, _TRAVAS_PRONTAS, _TRAVA_GERAL = {}, {}, threading.Lock()


def lembrar(chave, construir, ttl=TTL_RESPOSTA_MAPA):
    """(status, corpo) de `construir()`, refeito no máximo a cada `ttl` segundos por chave."""
    with _TRAVA_GERAL:
        trava = _TRAVAS_PRONTAS.setdefault(chave, threading.Lock())
    with trava:  # quem chega com a resposta vencida refaz; os outros esperam e reaproveitam
        pronta = _PRONTAS.get(chave)
        if pronta is None or time.time() >= pronta[0]:
            status, corpo = construir()
            pronta = _PRONTAS[chave] = (time.time() + ttl, status, corpo)
        return pronta[1], pronta[2]


RECURSO_DESLIGADO = (503, {"erro": "Este recurso está desligado neste servidor (BUSCAS_EXTRAS_POR_SEGUNDO=0)."})


def erro_do_tse(status, mensagem_404):
    """(status HTTP, corpo) para quando o TSE não deu dados."""
    if status == 404:
        return 404, {"erro": mensagem_404}
    if status in (403, 429):
        return 503, {"erro": "Muitas consultas seguidas ao TSE. Aguarde alguns minutos e tente de novo."}
    return 503, {"erro": f"Não foi possível ler o TSE agora (HTTP {status or 'sem resposta'}). Tentando de novo em instantes."}


def cidades_da_uf(ambiente, cargo, turno, uf):
    """(lista de cidades, None) ou (None, (status HTTP, corpo)) se o TSE não respondeu."""
    url = catalogo.url_municipios(ambiente, cargo, turno)
    dados, status, _ = estado.CACHE.obter(url, ttl=TTL_MUNICIPIOS)
    if dados is None:
        return None, erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    return leitura.municipios(dados, uf), None


def resumo_do_cargo(cargo, ambiente, turno):
    """(status, corpo) do resumo por UF: uma rodada de consultas que mapa, regiões e disputas dividem."""
    def construir():
        corpo, falha = mapa.resumo_por_uf(estado.CACHE.obter, ambiente, cargo, turno)
        if not falha:
            estado.HISTORICO_DO_MAPA.registrar((ambiente, cargo, turno), corpo, time.time())  # replay do palco
        return erro_do_tse(*falha) if falha else (200, corpo)

    return lembrar(("mapa", ambiente, cargo, turno), construir)
