"""Rota /api/resultado: o placar de uma seleção."""
import time

from contador.recursos.placar import resumir
from contador.servidor import estado
from contador.servidor.respostas import cidades_da_uf, erro_do_tse
from contador.servidor.validacao import validar, validar_municipio
from contador.tse import catalogo, leitura


def resultado(consulta):
    """Devolve (status HTTP, corpo JSON)."""
    try:
        cargo, uf, ambiente, turno, top = validar(consulta)
        municipio = validar_municipio(consulta, uf)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    cidade = None
    if municipio:
        # Só código que o TSE lista para esta UF vira URL: evita 404 em série (bloqueio do IP).
        lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
        if falha:
            return falha
        cidade = leitura.cidade_por_codigo(lista, municipio)
        if cidade is None:
            return 400, {"erro": "município inválido para esta UF"}
    url = catalogo.montar_url(ambiente, cargo, uf, turno, municipio=municipio or None)
    dados, status, verificado_em = estado.CACHE.obter(url)
    if dados is None:
        return erro_do_tse(status, "O TSE ainda não publicou o resultado desta seleção (ou o cargo não é disputado nesta UF).")
    estado.HISTORICO.registrar((ambiente, cargo, uf, turno, municipio), dados)  # só memória e disco: o histórico nunca consulta o TSE
    corpo = resumir(dados, top)
    corpo["ambiente"] = ambiente
    corpo["municipio"] = {"codigo": cidade["codigo"], "nome": cidade["nome"]} if cidade else None
    corpo["idade_s"] = round(time.time() - verificado_em)
    if status not in (200, 304):
        corpo["aviso"] = "O TSE não respondeu na última tentativa; mostrando o último placar recebido."
    return 200, corpo
