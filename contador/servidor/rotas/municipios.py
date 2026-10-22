"""Rotas de cidades: a lista da UF (/api/municipios) e o mapa por município (/api/mapa-municipal)."""
from contador import varredor
from contador.recursos import municipios
from contador.servidor import estado
from contador.servidor.respostas import RECURSO_DESLIGADO, cidades_da_uf, erro_do_tse
from contador.servidor.validacao import validar
from contador.tse import catalogo


def municipios_da_uf(consulta):
    """Devolve (status HTTP, corpo JSON) com as cidades da UF, para a página montar o seletor."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
        if uf == "br":
            raise ValueError("escolha uma UF para listar as cidades")
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
    if falha:
        return falha
    return 200, {"uf": uf, "municipios": lista}


def mapa_municipal(consulta):
    """(status, corpo) com o líder de cada cidade da UF. As cidades são buscadas aos poucos pelo varredor."""
    try:
        cargo, uf, ambiente, turno, _ = validar(consulta)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    if cargo not in ("presidente", "governador") or uf == "br":
        return 400, {"erro": "o mapa por município existe para presidente e governador, dentro de um estado"}
    if not estado.VARREDOR.ligado:
        return RECURSO_DESLIGADO
    lista, falha = cidades_da_uf(ambiente, cargo, turno, uf)
    if falha:
        return falha
    # Só varre se o arquivo da UF existe: no 2º turno de governador, UF sem 2º turno daria 404 em todas as cidades.
    dados, status, _ = estado.CACHE.obter(catalogo.montar_url(ambiente, cargo, uf, turno))
    if dados is None:
        return erro_do_tse(status, "O TSE ainda não publicou o resultado desta seleção (ou o cargo não é disputado neste estado).")
    ibge = municipios.ibge_das_cidades(estado.CACHE.espiar(catalogo.url_municipios(ambiente, cargo, turno)) or {}, uf)

    def fabrica():
        trabalhos = {c["codigo"]: varredor.Trabalho(c["codigo"], catalogo.montar_url(ambiente, cargo, uf, turno, municipio=c["codigo"])) for c in lista}
        return trabalhos, municipios.resumir_cidade, municipios.intervalo

    grupo = estado.VARREDOR.pedir(("cidades", ambiente, cargo, turno, uf), fabrica)
    estado.VARREDOR.priorizar(grupo, municipios.codigos_em_foco(consulta.get("foco", [""])[0], ibge))
    corpo = municipios.montar(uf, lista, ibge, estado.VARREDOR.resumos(grupo), estado.VARREDOR.relogio())
    corpo.update(cargo=cargo, turno=turno, ambiente=ambiente)
    return 200, corpo
