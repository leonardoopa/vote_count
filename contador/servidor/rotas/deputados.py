"""Rotas dos deputados: hemiciclo da Câmara (/api/camara) e mais votados (/api/maisvotados)."""
from contador import varredor
from contador.recursos import deputados
from contador.servidor import estado
from contador.servidor.respostas import RECURSO_DESLIGADO
from contador.tse import catalogo

FAMILIAS = {"deputado-federal": "federal", "deputado-estadual": "estadual", "deputado-distrital": "estadual"}


def cargo_da_familia(familia, uf):
    """Federal: um cargo em todas as UFs. Estadual: o do DF é o distrital."""
    return "deputado-federal" if familia == "federal" else "deputado-distrital" if uf == "df" else "deputado-estadual"


def painel_de_deputados(consulta, familia, montar):
    """(status, corpo) de um recurso feito com os arquivos de deputados de todas as UFs. `montar` recebe {uf: resumo}."""
    ambiente = consulta.get("ambiente", ["oficial"])[0]
    if ambiente not in catalogo.AMBIENTES:
        return 400, {"erro": "ambiente inválido"}

    def fabrica():
        trabalhos = {uf: varredor.Trabalho(uf, catalogo.montar_url(ambiente, cargo_da_familia(familia, uf), uf, 1)) for uf in catalogo.UFS}
        return trabalhos, deputados.resumir_arquivo, deputados.intervalo

    grupo = estado.VARREDOR.pedir(("deputados", ambiente, familia), fabrica)
    if grupo is None:
        return RECURSO_DESLIGADO
    fotos = estado.VARREDOR.resumos(grupo)
    corpo = montar({uf: foto[0] for uf, foto in fotos.items()})
    verificados = [foto[1] for foto in fotos.values() if foto[0]]
    corpo.update(ambiente=ambiente, idade_s=round(estado.VARREDOR.relogio() - min(verificados)) if verificados else None)
    return 200, corpo


def camara_dos_deputados(consulta):
    return painel_de_deputados(consulta, "federal", deputados.camara)


def mais_votados(consulta):
    cargo = consulta.get("cargo", ["deputado-federal"])[0]
    if cargo not in FAMILIAS:
        return 400, {"erro": "só deputado federal, estadual ou distrital têm ranking de mais votados"}
    status, corpo = painel_de_deputados(consulta, FAMILIAS[cargo], deputados.mais_votados)
    return status, {**corpo, "cargo": cargo} if status == 200 else corpo
