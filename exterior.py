"""Exterior por país: soma o voto dos brasileiros no exterior para o mapa-múndi.

O TSE publica o exterior como a UF "zz" e, dentro dela, uma "cidade" por embaixada ou consulado (186 em 2026,
de Abidjã a Zurique). Não diz o país, então `PAISES` liga cada cidade a um país (código ISO 3166-1 alfa-2, o mesmo
de web/geo/mundo.json). Cidade que não está na tabela fica de fora do mapa e é contada em `sem_pais`.

Funções puras. Quem busca os arquivos é o varredor (`varredura.py`), um por cidade; aqui só se resume e soma.
"""
import contador
import mapa

# país -> cidades, com o nome que o TSE usa (maiúsculas, com acento)
PAISES = {
    "US": ["ATLANTA", "BOSTON", "CHICAGO", "HARTFORD", "HOUSTON", "LOS ANGELES", "MIAMI", "NOVA YORK", "ORLANDO", "SÃO FRANCISCO", "WASHINGTON"],
    "CA": ["MONTREAL", "OTTAWA", "TORONTO", "VANCOUVER"],
    "MX": ["MEXICO"], "GT": ["GUATEMALA"], "BZ": ["BELMOPAN"], "HN": ["TEGUCIGALPA"], "SV": ["SÃO SALVADOR"], "NI": ["MANÁGUA"],
    "CR": ["SÃO JOSÉ"], "PA": ["PANAMA"], "CU": ["HAVANA"], "JM": ["KINGSTON-JAMAICA"], "HT": ["PORTO PRÍNCIPE"], "DO": ["SÃO DOMINGOS"],
    "BS": ["NASSAU"], "BB": ["BRIDGETOWN"], "LC": ["CASTRIES"], "AG": ["SAINT JOHNS"], "TT": ["PORT OF SPAIN"],
    "CO": ["BOGOTÁ"], "VE": ["CARACAS", "CIUDAD GUAYANA", "SANTA ELENA DE UAIRÉN"], "GY": ["GEORGETOWN"], "SR": ["PARAMARIBO"],
    "FR": ["CAIENA", "ST GEORGES DE LOYAPOCK", "MARSELHA", "PARIS"],
    "EC": ["QUITO"], "PE": ["LIMA", "IQUITOS"], "CL": ["SANTIAGO"],
    "BO": ["LA PAZ", "COBIJA", "COCHABAMBA", "SANTA CRUZ DE LA SIERRA", "PUERTO QUIJARRO"],
    "PY": ["ASSUNÇÃO", "CIUDAD DEL ESTE", "ENCARNACIÓN", "PEDRO JUAN CABALLERO", "SALTO DEL GUAIRÁ", "CONCEPCIÓN"],
    "AR": ["BUENOS AIRES", "CÓRDOBA", "MENDOZA", "PASO LOS LIBRES", "PUERTO IGUAZÚ"],
    "UY": ["MONTEVIDÉU", "ARTIGAS", "CHUY", "RIVERA", "RIO BRANCO"],
    "NL": ["AMSTERDÃ"], "GR": ["ATENAS"], "ES": ["BARCELONA", "MADRI"], "RS": ["BELGRADO"], "DE": ["BERLIM", "FRANKFURT", "MUNIQUE"],
    "SK": ["BRATISLAVA"], "BE": ["BRUXELAS"], "RO": ["BUCARESTE"], "HU": ["BUDAPESTE"], "DK": ["COPENHAGUE"], "IE": ["DUBLIN"],
    "SE": ["ESTOCOLMO"], "PT": ["FARO", "LISBOA", "PORTO"], "CH": ["GENEBRA", "ZURIQUE"], "FI": ["HELSINQUE"], "UA": ["KIEV"],
    "SI": ["LIUBLIANA"], "GB": ["LONDRES", "EDIMBURGO"], "IT": ["MILÃO", "ROMA"], "RU": ["MOSCOU"], "CY": ["NICOSIA"], "NO": ["OSLO"],
    "CZ": ["PRAGA"], "BA": ["SARAJEVO"], "BG": ["SÓFIA"], "EE": ["TALIN"], "AL": ["TIRANA"], "PL": ["VARSÓVIA"], "AT": ["VIENA"],
    "HR": ["ZAGREB"], "TR": ["ISTAMBUL", "ANCARA"],
    "AE": ["ABU DHABI"], "JO": ["AMÃ"], "IQ": ["BAGDÁ"], "AZ": ["BAKU"], "BH": ["BAREIN"], "LB": ["BEIRUTE"], "QA": ["DOHA"],
    "AM": ["IEREVAN"], "SA": ["RIADE"], "KW": ["KUAITE"], "OM": ["MASCATE"], "SY": ["DAMASCO"], "IR": ["TEERÃ"], "GE": ["TBILISI"],
    "IL": ["TEL AVIV"], "PS": ["RAMALLAH"], "KZ": ["ASTANA"], "PK": ["ISLAMABADE"], "BD": ["DACCA"], "NP": ["KATMANDU"], "LK": ["COLOMBO"],
    "IN": ["MUMBAI", "NOVA DELHI"], "MM": ["YANGON"], "TH": ["BANGKOK"], "VN": ["HANÓI"], "MY": ["KUALA LUMPUR"], "SG": ["SINGAPURA"],
    "ID": ["JACARTA"], "PH": ["MANILA"], "KR": ["SEUL"], "KP": ["PYONGYANG"], "JP": ["TÓQUIO", "HAMAMATSU", "NAGÓIA"],
    "CN": ["PEQUIM", "XANGAI", "CANTÃO"], "HK": ["HONG KONG"], "TW": ["TAIPÉ"], "TL": ["DÍLI"], "AU": ["CAMBERRA", "SYDNEY"], "NZ": ["WELLINGTON"],
    "CI": ["ABIDJÃ"], "NG": ["ABUJA", "LAGOS"], "GH": ["ACCRA"], "ET": ["ADIS ABEBA"], "DZ": ["ARGEL"], "ML": ["BAMAKO"], "GW": ["BISSAU"],
    "CG": ["BRAZZAVILLE"], "EG": ["CAIRO"], "ZA": ["CIDADE DO CABO", "PRETÓRIA"], "GN": ["CONACRI"], "BJ": ["COTONOU"], "SN": ["DACAR"],
    "TZ": ["DAR ES SALAAM"], "BW": ["GABORONE"], "ZW": ["HARARE"], "CM": ["IAUNDÊ"], "CD": ["KINSHASA"], "GA": ["LIBREVILLE"],
    "MW": ["LILONGUE"], "TG": ["LOMÉ"], "AO": ["LUANDA"], "ZM": ["LUSACA"], "GQ": ["MALABO"], "MZ": ["MAPUTO"], "KE": ["NAIRÓBI"],
    "MA": ["RABAT"], "ST": ["SÃO TOMÉ"], "LY": ["TRÍPOLI"], "TN": ["TUNIS"], "BF": ["UAGADUGU"], "NA": ["WINDHOEK"], "CV": ["PRAIA"],
}
PAIS_DA_CIDADE = {cidade: pais for pais, cidades in PAISES.items() for cidade in cidades}


def cidades_do_exterior(config):
    """[{codigo, nome (do TSE), pais}] das cidades da UF "zz" no arquivo de configuração do TSE; `pais` é None se a cidade não está na tabela."""
    for abrangencia in config.get("abr", []):
        if abrangencia.get("cd") == "zz":
            return [{"codigo": m["cd"], "nome": m["nm"], "pais": PAIS_DA_CIDADE.get(m["nm"].strip().upper())} for m in abrangencia.get("mu", [])]
    return []


def resumir_cidade(dados, codigo=None):
    """O que se guarda de um arquivo de cidade: votos por candidato, seções e nomes. Compacto: são 186 cidades."""
    resumo = mapa.resumir_uf(dados, com_votos=True)
    return {
        "votos": resumo["votos"],
        "secoes": [resumo["secoes"]["apuradas"], resumo["secoes"]["total"]],
        "final": resumo["final"],
        "nomes": {cand["n"]: [cand.get("nmu") or cand["nm"], cand["partido"]] for cand in contador.candidatos(dados)},
    }


def _candidatos(votos, nomes):
    """Candidatos do mais votado para o menos, com o percentual sobre os votos nos candidatos (os válidos)."""
    validos = sum(votos.values())
    ordem = sorted(votos.items(), key=lambda par: (-par[1], par[0]))
    return [
        {"numero": numero, "nome": nomes[numero][0], "partido": nomes[numero][1], "votos": v, "percentual": round(100 * v / validos, 2) if validos else 0.0}
        for numero, v in ordem
    ]


def resumir_territorio(votos, nomes, apuradas, total, locais, carregados, final):
    """O resumo de um país (ou do Brasil): líder, segundo, margem e andamento. O formato é o que `pintura()` da página espera."""
    resumo = {"locais": locais, "carregados": carregados, "votos": sum(votos.values()), "apurado": round(100 * apuradas / total, 2) if total else 0.0,
              "final": bool(carregados) and carregados == locais and final, "situacao": "lider", "lider": None, "segundo": None, "margem": None, "margem_votos": None}
    candidatos = _candidatos(votos, nomes)
    if not carregados:
        resumo["situacao"] = "sem_dados"
    elif not resumo["votos"] or not apuradas:
        resumo["situacao"] = "zerado"
    elif len(candidatos) > 1 and candidatos[0]["votos"] == candidatos[1]["votos"]:
        resumo["situacao"] = "empate"
        resumo["margem"], resumo["margem_votos"] = 0.0, 0
    else:
        resumo["lider"], resumo["segundo"] = candidatos[0], candidatos[1] if len(candidatos) > 1 else None
        resumo["margem"] = round(candidatos[0]["percentual"] - (candidatos[1]["percentual"] if len(candidatos) > 1 else 0), 2)
        resumo["margem_votos"] = candidatos[0]["votos"] - (candidatos[1]["votos"] if len(candidatos) > 1 else 0)
    return resumo


def somar(resumos):
    """(votos, nomes, seções apuradas, seções no total, todas finais) de uma lista de resumos de cidade."""
    votos, nomes, apuradas, total = {}, {}, 0, 0
    for resumo in resumos:
        for numero, v in resumo["votos"].items():
            votos[numero] = votos.get(numero, 0) + v
        nomes.update(resumo["nomes"])
        apuradas += resumo["secoes"][0]
        total += resumo["secoes"][1]
    return votos, nomes, apuradas, total, all(resumo["final"] for resumo in resumos)


def pais_do_resumo(resumos, locais):
    votos, nomes, apuradas, total, final = somar(resumos)
    return resumir_territorio(votos, nomes, apuradas, total, locais, len(resumos), final)


def brasil(corpo_do_mapa):
    """Resumo do Brasil (as 27 UFs, sem o exterior) a partir do corpo de `mapa.resumo_por_uf` do presidente; None se faltam dados."""
    ufs = [uf for uf in corpo_do_mapa.get("ufs", {}).values() if uf.get("votos")]
    if not ufs:
        return None
    votos, apuradas, total = {}, 0, 0
    for uf in ufs:
        for numero, v in uf["votos"].items():
            votos[numero] = votos.get(numero, 0) + v
        apuradas += uf["secoes"]["apuradas"]
        total += uf["secoes"]["total"]
    nomes = {c["numero"]: [c["nome"], c["partido"]] for c in corpo_do_mapa.get("candidatos", [])}
    votos = {numero: v for numero, v in votos.items() if numero in nomes}
    return resumir_territorio(votos, nomes, apuradas, total, len(ufs), len(ufs), all(uf["final"] for uf in ufs))


def montar(cidades, fotos, agora, pais=None):
    """Corpo de /api/mundo.

    `cidades` vem de `cidades_do_exterior`; `fotos` é {código TSE: (resumo, verificado_em, status)} do varredor. A resposta traz
    o resumo de cada país com cidade já buscada, `locais` (quantas cidades com urna cada país tem) e, com `pais` (ISO), o detalhe dele: candidatos e cidades.
    """
    por_pais, sem_pais = {}, 0
    for cidade in cidades:
        if cidade["pais"]:
            por_pais.setdefault(cidade["pais"], []).append(cidade)
        else:
            sem_pais += 1
    paises = {}
    for iso, lista in por_pais.items():
        resumos = [fotos[c["codigo"]][0] for c in lista if (fotos.get(c["codigo"]) or (None,))[0]]
        if resumos:
            paises[iso] = pais_do_resumo(resumos, len(lista))
    verificados = [foto[1] for foto in fotos.values() if foto[0]]
    corpo = {"total": len(cidades), "carregadas": len(verificados), "sem_pais": sem_pais, "paises": paises,
             "locais": {iso: len(lista) for iso, lista in por_pais.items()},   # países com urna, mesmo os ainda não buscados
             "idade_s": round(agora - min(verificados)) if verificados else None}
    if pais in por_pais:
        resumos = [(c, (fotos.get(c["codigo"]) or (None,))[0]) for c in por_pais[pais]]
        carregados = [r for _, r in resumos if r]
        votos, nomes = somar(carregados)[:2] if carregados else ({}, {})
        corpo["detalhe"] = {
            "pais": pais,
            "candidatos": _candidatos(votos, nomes),
            "cidades": [_cidade_do_detalhe(c, r) for c, r in sorted(resumos, key=lambda par: contador.sem_acento(par[0]["nome"]))],
        }
    return corpo


def _cidade_do_detalhe(cidade, resumo):
    """Linha de uma cidade na lista do país: nome, líder e andamento. Sem resumo, só o nome (a cidade ainda não foi buscada)."""
    linha = {"codigo": cidade["codigo"], "nome": contador.nome_proprio(cidade["nome"]), "situacao": "sem_dados"}
    if resumo:
        e = pais_do_resumo([resumo], 1)
        linha.update(situacao=e["situacao"], votos=e["votos"], apurado=e["apurado"], lider=e["lider"] and {k: e["lider"][k] for k in ("nome", "partido", "percentual")})
    return linha
