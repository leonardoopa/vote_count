"""Rotas que partem do resumo por UF: mapa do Brasil, regiões, disputas apertadas e Senado."""
from contador.recursos import mapa
from contador.servidor import estado
from contador.servidor.respostas import resumo_do_cargo
from contador.servidor.validacao import validar_mapa

DISPUTAS_MAXIMO = 27  # todas as UFs; a página mostra as mais apertadas primeiro


def mapa_por_uf(consulta):
    """Devolve (status HTTP, corpo JSON) com o líder de cada UF, para o mapa do Brasil."""
    try:
        cargo, ambiente, turno = validar_mapa(consulta)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    return resumo_do_cargo(cargo, ambiente, turno)


def derivado(consulta, cargos, funcao):
    """Corpo de uma rota que só reorganiza o resumo por UF (regiões, disputas): sem consulta nova ao TSE."""
    try:
        cargo, ambiente, turno = validar_mapa(consulta, cargos)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    status, corpo = resumo_do_cargo(cargo, ambiente, turno)
    return (status, funcao(corpo)) if status == 200 else (status, corpo)


def regioes_do_pais(consulta):
    return derivado({**consulta, "cargo": ["presidente"]}, ("presidente",), mapa.regioes)


def disputas_apertadas(consulta):
    return derivado(consulta, ("governador", "senador"), lambda corpo: mapa.disputas(corpo, limite=DISPUTAS_MAXIMO))


def senado_em_disputa(consulta):
    return derivado({**consulta, "cargo": ["senador"]}, ("senador",), mapa.senado)


def mapa_historico(consulta):
    """Fotos do mapa por UF ao longo da apuração (/api/mapa-historico). Só lê o que já foi guardado: nunca consulta o TSE."""
    try:
        cargo, ambiente, turno = validar_mapa(consulta)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    return 200, estado.HISTORICO_DO_MAPA.consultar((ambiente, cargo, turno))
