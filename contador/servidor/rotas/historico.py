"""Rotas do histórico: a série do placar (/api/historico) e o feed de atualizações (/api/atualizacoes).

Só leem o que já foi guardado; nunca consultam o TSE.
"""
from contador.recursos import historico
from contador.servidor import estado
from contador.servidor.validacao import validar, validar_municipio


def chave_do_historico(consulta):
    """(chave da série, None) ou (None, (status HTTP, corpo)) quando a seleção não pode ter histórico."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
        municipio = validar_municipio(consulta, uf)
    except ValueError as erro:
        return None, (400, {"erro": str(erro)})
    if cargo not in historico.CARGOS:
        return None, (400, {"erro": "o histórico só existe para presidente, governador e senador"})
    return (ambiente, cargo, uf, turno, municipio), None


def historico_da_selecao(consulta):
    chave, erro = chave_do_historico(consulta)
    return erro or (200, estado.HISTORICO.consultar(chave))


def atualizacoes_da_selecao(consulta):
    chave, erro = chave_do_historico(consulta)
    return erro or (200, estado.HISTORICO.atualizacoes(chave))
