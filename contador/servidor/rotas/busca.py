"""Rota /api/busca: busca rápida de cidades pelo nome, na lista que o TSE já deu."""
from contador.servidor import estado
from contador.servidor.respostas import erro_do_tse
from contador.servidor.validacao import validar
from contador.tse import catalogo, leitura
from contador.tse.cache import TTL_MUNICIPIOS

MAX_BUSCA = 40        # caracteres do termo
MAX_RESULTADOS = 10   # cidades devolvidas
_INDICE = (None, [])  # (arquivo de cidades do TSE, [(uf, código, nome, nome sem acento, capital)])


def indice_de_cidades(config):
    """Cidades de todas as UFs já sem acento, guardadas enquanto o arquivo do TSE no cache for o mesmo."""
    global _INDICE
    if _INDICE[0] is not config:
        lista = [
            (abr["cd"], m["cd"], leitura.nome_proprio(m["nm"]), leitura.sem_acento(m["nm"]), m.get("c") == "s")
            for abr in config.get("abr", []) if abr.get("cd") in catalogo.UFS
            for m in abr.get("mu", [])
        ]
        _INDICE = (config, lista)
    return _INDICE[1]


def buscar_cidades(config, cargo, termo, limite=MAX_RESULTADOS):
    """Cidades cujo nome contém o termo (sem diferenciar acento nem caixa). Quem começa com o termo vem primeiro."""
    alvo = leitura.sem_acento(termo)
    if len(alvo) < 2:
        return []
    achadas = []
    for uf, codigo, nome, normal, capital in indice_de_cidades(config):
        posicao = normal.find(alvo)
        if posicao < 0 or not catalogo.uf_valida(cargo, uf):
            continue
        rank = 0 if posicao == 0 else 1 if normal[posicao - 1] == " " else 2
        achadas.append(((rank, not capital, len(normal), normal, uf), {"uf": uf, "codigo": codigo, "nome": nome, "capital": capital}))
    achadas.sort(key=lambda par: par[0])
    return [cidade for _, cidade in achadas[:limite]]


def busca_rapida(consulta):
    """Devolve (status HTTP, corpo JSON) com as cidades que combinam com `q`. A lista vem do cache: sem consulta nova."""
    cargo = consulta.get("cargo", ["presidente"])[0]
    uf = "br" if cargo == "presidente" else "df" if cargo == "deputado-distrital" else "sp"
    try:
        cargo, _, ambiente, _, _ = validar({**consulta, "uf": [uf], "turno": ["1"]})
    except ValueError as erro:
        return 400, {"erro": str(erro)}
    termo = consulta.get("q", [""])[0]
    if len(termo) > MAX_BUSCA:
        return 400, {"erro": "termo de busca longo demais"}
    if len(leitura.sem_acento(termo)) < 2:
        return 200, {"cidades": []}
    # a lista de cidades é a mesma em qualquer turno: o 1º turno sempre existe
    config, status, _ = estado.CACHE.obter(catalogo.url_municipios(ambiente, cargo, 1), ttl=TTL_MUNICIPIOS)
    if config is None:
        return erro_do_tse(status, "O TSE não publicou a lista de cidades desta eleição.")
    return 200, {"cidades": buscar_cidades(config, cargo, termo)}
