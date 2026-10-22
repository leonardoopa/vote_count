"""O que o TSE publica: ambientes, cargos, UFs e o endereço de cada arquivo."""

AMBIENTES = {
    "oficial": {
        "base": "https://resultados.tse.jus.br/oficial/ele2026",
        # (1º turno, 2º turno) por tipo de eleição
        "eleicoes": {"federal": (6257, 6258), "estadual": (6259, 6260)},
    },
    "simulado": {
        "base": "https://resultados-sim.tse.jus.br/simulado/simulado2026/ele2026",
        "eleicoes": {"federal": (21270, 21271), "estadual": (21272, 21273)},
    },
}

# nome na linha de comando: (código do cargo no TSE, tipo de eleição)
CARGOS = {
    "presidente": (1, "federal"),
    "governador": (3, "estadual"),
    "senador": (5, "estadual"),
    "deputado-federal": (6, "estadual"),
    "deputado-estadual": (7, "estadual"),
    "deputado-distrital": (8, "estadual"),
}

UFS = (
    "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to"
).split()


def uf_valida(cargo, uf):
    """'br' só existe para presidente; distrital só no DF; estadual em todas as UFs menos o DF."""
    if cargo == "presidente" and uf == "br":
        return True
    if cargo == "deputado-distrital":
        return uf == "df"
    if cargo == "deputado-estadual":
        return uf in UFS and uf != "df"
    return uf in UFS


def codigo_eleicao(ambiente, cargo, turno, eleicao=None):
    tipo = CARGOS[cargo][1]
    return eleicao or AMBIENTES[ambiente]["eleicoes"][tipo][turno - 1]


def montar_url(ambiente, cargo, uf, turno, eleicao=None, municipio=None):
    """URL do resultado: da UF/Brasil ou, com `municipio` (código TSE de 5 dígitos), da cidade."""
    codigo_cargo = CARGOS[cargo][0]
    codigo = codigo_eleicao(ambiente, cargo, turno, eleicao)
    arquivo = f"{uf}{municipio or ''}-c{codigo_cargo:04d}-e{codigo:06d}-u.json"
    return f"{AMBIENTES[ambiente]['base']}/{codigo}/dados/{uf}/{arquivo}"


def url_municipios(ambiente, cargo, turno, eleicao=None):
    """Lista de municípios (por UF) da eleição: a mesma para todos os cargos dela."""
    codigo = codigo_eleicao(ambiente, cargo, turno, eleicao)
    return f"{AMBIENTES[ambiente]['base']}/{codigo}/config/mun-e{codigo:06d}-cm.json"
