"""Mapa por município: quem lidera em cada cidade de uma UF, para colorir o desenho (geo/<uf>.json).

Funções puras. Cada cidade é um arquivo do TSE; quem busca é o varredor (`varredor.py`), devagar, e
este módulo só resume o que chegou. O desenho vem do IBGE (veja tools/gerar_mapa.py) e a ligação entre
os dois é o código IBGE (`cdi`) que o próprio TSE traz no arquivo de configuração das cidades.
"""
from contador.recursos import mapa
from contador.tse import leitura


INTERVALO_APURANDO_S = 120
INTERVALO_FINAL_S = 1800
MAX_FOCO = 60  # cidades que a página pode pedir para buscar primeiro


def intervalo(resumo):
    """Segundos até buscar a cidade de novo: devagar depois de apurada."""
    return INTERVALO_FINAL_S if resumo and resumo["final"] else INTERVALO_APURANDO_S


def resumir_cidade(dados, codigo=None):
    """O que o mapa precisa de uma cidade: situação, líder, margem e andamento. Compacto: são até 645 por UF."""
    inteiro = mapa.resumir_uf(dados)
    resumo = {"situacao": inteiro["situacao"], "apurado": inteiro["secoes"]["percentual"], "final": inteiro["final"]}
    if inteiro["situacao"] == "lider":
        lider, segundo = inteiro["lider"], inteiro["segundo"]
        resumo["lider"] = {chave: lider[chave] for chave in ("numero", "nome", "partido", "percentual", "votos", "eleito", "segundo_turno")}
        if segundo:
            resumo["segundo"] = {chave: segundo[chave] for chave in ("numero", "nome", "partido", "percentual", "votos")}
        resumo["margem"], resumo["margem_votos"] = inteiro["margem"], inteiro["margem_votos"]
    elif inteiro["situacao"] == "empate":
        resumo["empatados"] = [{"nome": c["nome"], "partido": c["partido"]} for c in inteiro["empatados"]]
    return resumo


UF_DO_CODIGO_IBGE = {
    "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma", "22": "pi",
    "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba", "31": "mg", "32": "es",
    "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms", "51": "mt", "52": "go", "53": "df",
}


def resumir_cidade_do_brasil(dados, codigo=None):
    """Como `resumir_cidade`, para o mapa do país: são ~5,6 mil cidades, então só o essencial, com o `sqcand` (a foto)."""
    inteiro = mapa.resumir_uf(dados)
    resumo = {"situacao": inteiro["situacao"], "apurado": inteiro["secoes"]["percentual"], "final": inteiro["final"]}
    if inteiro["situacao"] == "lider":
        sqcand = {c["n"]: c.get("sqcand") for c in leitura.candidatos(dados)}
        for papel in ("lider", "segundo"):
            c = inteiro[papel]
            if c:
                resumo[papel] = {"numero": c["numero"], "nome": c["nome"], "partido": c["partido"], "percentual": c["percentual"], "sqcand": sqcand.get(c["numero"])}
        resumo["margem_votos"] = inteiro["margem_votos"]
    return resumo


def ordem_espalhada(codigos_por_uf):
    """Intercala as cidades das UFs (uma de cada UF por vez): o mapa do país enche por todo o território, não estado por estado."""
    filas = [list(codigos) for codigos in codigos_por_uf.values()]
    saida = []
    for posicao in range(max((len(fila) for fila in filas), default=0)):
        saida.extend(fila[posicao] for fila in filas if posicao < len(fila))
    return saida


def montar_brasil(cargo, resumos, total, foto_de, agora):
    """Corpo de /api/mapa-municipal?uf=br: o líder e o segundo de cada cidade já buscada, em listas curtas.

    `resumos` é {código IBGE: (resumo, verificado_em, status)} do varredor e `foto_de(uf, sqcand)` dá o endereço da foto.
    `candidatos` é a tabela de quem aparece; `cidades` guarda, por código IBGE,
    [candidato líder, % do líder, candidato segundo (-1 se não há), % do segundo, % das seções, votos de vantagem, final (0 ou 1)].
    O candidato é um só no país para presidente; em governador é um por UF.
    """
    candidatos, indice, cidades, verificados = [], {}, {}, []
    for ibge, (resumo, verificado, _) in resumos.items():
        if not resumo:
            continue
        verificados.append(verificado)
        if resumo["situacao"] != "lider":
            continue
        uf = UF_DO_CODIGO_IBGE.get(ibge[:2])
        linha = []
        for papel in ("lider", "segundo"):
            c = resumo.get(papel)
            if not c:
                linha += [-1, 0.0]
                continue
            chave = (uf if cargo == "governador" else "br", c["numero"])
            if chave not in indice:
                indice[chave] = len(candidatos)
                candidatos.append({"numero": c["numero"], "nome": c["nome"], "partido": c["partido"], "foto": foto_de(uf, c.get("sqcand"))})
            linha += [indice[chave], c["percentual"]]
        cidades[ibge] = [linha[0], linha[1], linha[2], linha[3], resumo["apurado"], resumo["margem_votos"], int(resumo["final"])]
    return {
        "total": total,
        "carregadas": len(verificados),
        "idade_s": round(agora - min(verificados)) if verificados else None,
        "candidatos": candidatos,
        "cidades": cidades,
    }


def ibge_das_cidades(config, uf):
    """{código TSE: código IBGE} das cidades da UF no arquivo de configuração do TSE."""
    for abrangencia in config.get("abr", []):
        if abrangencia.get("cd") == uf:
            return {m["cd"]: m["cdi"] for m in abrangencia.get("mu", []) if m.get("cdi")}
    return {}


def codigos_em_foco(foco, ibge):
    """Códigos TSE, na ordem pedida, das cidades que a página está vendo.

    `foco` é o parâmetro da URL: códigos IBGE separados por vírgula (a página só conhece o desenho). Lixo, repetição
    e cidades de outra UF são ignorados, e a lista tem no máximo MAX_FOCO.
    """
    tse_de = {codigo_ibge: codigo_tse for codigo_tse, codigo_ibge in ibge.items()}
    codigos = []
    for pedido in foco[:2000].split(","):
        codigo = tse_de.get(pedido.strip())
        if codigo is not None and codigo not in codigos:
            codigos.append(codigo)
    return codigos[:MAX_FOCO]


def montar(uf, cidades, ibge, fotos, agora):
    """Corpo de /api/mapa-municipal.

    `cidades` é a lista de `leitura.municipios`; `ibge` vem de `ibge_das_cidades`; `fotos` é
    {código TSE: (resumo, verificado_em, status)} do varredor. A resposta é por código IBGE (o do desenho)
    e só traz as cidades que já foram buscadas.
    """
    desenhaveis = {}
    for cidade in cidades:
        resumo = (fotos.get(cidade["codigo"]) or (None,))[0]
        if resumo and ibge.get(cidade["codigo"]):
            desenhaveis[ibge[cidade["codigo"]]] = {"nome": cidade["nome"], "codigo": cidade["codigo"], **resumo}
    verificados = [foto[1] for foto in fotos.values() if foto[0]]
    return {
        "uf": uf,
        "total": len(cidades),
        "carregadas": len(verificados),
        "idade_s": round(agora - min(verificados)) if verificados else None,
        "cidades": desenhaveis,
    }
