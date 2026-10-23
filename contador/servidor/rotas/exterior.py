"""Rota /api/mundo: o voto no exterior por país, para o mapa-múndi."""
import re

from contador import varredor
from contador.recursos import exterior, municipios
from contador.servidor import estado, respostas
from contador.servidor.respostas import RECURSO_DESLIGADO, erro_do_tse
from contador.tse import catalogo, leitura
from contador.tse.cache import TTL_MUNICIPIOS


def mundo(consulta):
    """(status, corpo) do exterior por país, para o mapa-múndi. Com `pais` (ISO alfa-2), traz também o detalhe dele.

    O TSE publica um arquivo por cidade do exterior (embaixadas e consulados); o varredor busca os 186 aos poucos, como no mapa
    por município, e `recursos/exterior.py` soma por país. O Brasil vem do resumo por UF, que a página já pede.
    """
    ambiente, turno = consulta.get("ambiente", ["oficial"])[0], consulta.get("turno", ["1"])[0]
    pais = consulta.get("pais", [""])[0].upper()
    if ambiente not in catalogo.AMBIENTES or turno not in ("1", "2") or (pais and not re.fullmatch(r"[A-Z]{2}", pais)):
        return 400, {"erro": "ambiente, turno ou país inválido"}
    if not estado.VARREDOR.ligado:
        return RECURSO_DESLIGADO
    turno = int(turno)
    config, status, _ = estado.CACHE.obter(catalogo.url_municipios(ambiente, "presidente", turno), ttl=TTL_MUNICIPIOS)
    if config is None:
        return erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    dados, status, _ = estado.CACHE.obter(catalogo.montar_url(ambiente, "presidente", "zz", turno))
    if dados is None:   # só varre se o arquivo do exterior existe (no 2º turno ele só aparece depois da apuração começar)
        return erro_do_tse(status, "O TSE ainda não publicou o resultado do exterior.")
    cidades = exterior.cidades_do_exterior(config)

    def fabrica():
        trabalhos = {c["codigo"]: varredor.Trabalho(c["codigo"], catalogo.montar_url(ambiente, "presidente", "zz", turno, municipio=c["codigo"])) for c in cidades}
        return trabalhos, exterior.resumir_cidade, municipios.intervalo

    grupo = estado.VARREDOR.pedir(("exterior", ambiente, turno), fabrica)
    corpo = exterior.montar(cidades, estado.VARREDOR.resumos(grupo), estado.VARREDOR.relogio(), pais or None)
    corpo.update(ambiente=ambiente, turno=turno)
    # a foto de cada candidato (pela posição no arquivo do exterior): o cartão do país mostra líder e segundo com foto
    corpo["fotos"] = {c["n"]: catalogo.url_foto(ambiente, "presidente", "br", turno, c.get("sqcand")) for c in leitura.candidatos(dados)}
    status_do_mapa, mapa_dos_estados = respostas.resumo_do_cargo("presidente", ambiente, turno)
    corpo["brasil"] = exterior.brasil(mapa_dos_estados) if status_do_mapa == 200 else None
    return 200, corpo
