"""Rotas de cidades: a lista da UF (/api/municipios) e o mapa por município (/api/mapa-municipal)."""
from contador import varredor
from contador.recursos import municipios
from contador.servidor import estado
from contador.servidor import respostas
from contador.servidor.respostas import RECURSO_DESLIGADO, cidades_da_uf, erro_do_tse
from contador.servidor.validacao import validar, validar_mapa
from contador.tse import catalogo
from contador.tse.cache import TTL_MUNICIPIOS


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


def mapa_municipal_do_brasil(consulta):
    """(status, corpo) com o líder de cada cidade do país (`?uf=br`), em listas curtas, para pintar o mapa do Brasil por município.

    São ~5,6 mil arquivos do TSE, buscados aos poucos pelo varredor (o teto é BUSCAS_EXTRAS_POR_SEGUNDO) e só enquanto
    alguém olha. As cidades vão intercaladas entre os estados, então o mapa enche por todo o território. No 2º turno de
    governador só entram os estados que têm 2º turno: nos outros não existe arquivo.
    """
    try:
        cargo, ambiente, turno = validar_mapa(consulta)
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    if not estado.VARREDOR.ligado:
        return RECURSO_DESLIGADO
    config, status, _ = estado.CACHE.obter(catalogo.url_municipios(ambiente, cargo, turno), ttl=TTL_MUNICIPIOS)
    if config is None:
        return erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    status_mapa, resumo = respostas.resumo_do_cargo(cargo, ambiente, turno)   # quem tem arquivo: o mapa por estado já sabe
    if status_mapa != 200:
        return status_mapa, resumo
    ufs = [uf for uf in catalogo.UFS if resumo["ufs"][uf]["situacao"] not in ("sem_dados", "sem_segundo_turno")]
    cidades_por_uf = {}   # uf -> [(código IBGE, código TSE)]
    for uf in ufs:
        ibge = municipios.ibge_das_cidades(config, uf)
        cidades_por_uf[uf] = [(codigo_ibge, codigo_tse) for codigo_tse, codigo_ibge in ibge.items()]
    por_ibge = {codigo_ibge: (uf, codigo_tse) for uf, pares in cidades_por_uf.items() for codigo_ibge, codigo_tse in pares}

    def fabrica():
        ordem = municipios.ordem_espalhada({uf: [c for c, _ in pares] for uf, pares in cidades_por_uf.items()})
        trabalhos = {c: varredor.Trabalho(c, catalogo.montar_url(ambiente, cargo, por_ibge[c][0], turno, municipio=por_ibge[c][1])) for c in ordem}
        return trabalhos, municipios.resumir_cidade_do_brasil, municipios.intervalo

    grupo = estado.VARREDOR.pedir(("cidades-do-brasil", ambiente, cargo, turno), fabrica, total=len(por_ibge))   # estado novo com arquivo: o grupo cresce
    foto_de = lambda uf, sqcand: catalogo.url_foto(ambiente, cargo, uf, turno, sqcand)
    corpo = municipios.montar_brasil(cargo, estado.VARREDOR.resumos(grupo), len(por_ibge), foto_de, estado.VARREDOR.relogio())
    corpo.update(cargo=cargo, turno=turno, ambiente=ambiente)
    return 200, corpo


def mapa_municipal(consulta):
    """(status, corpo) com o líder de cada cidade da UF. As cidades são buscadas aos poucos pelo varredor."""
    if consulta.get("uf") == ["br"]:
        return mapa_municipal_do_brasil(consulta)
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
