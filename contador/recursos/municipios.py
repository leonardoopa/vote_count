"""Mapa por município: quem lidera em cada cidade de uma UF, para colorir o desenho (geo/<uf>.json).

Funções puras. Cada cidade é um arquivo do TSE; quem busca é o varredor (`varredor.py`), devagar, e
este módulo só resume o que chegou. O desenho vem do IBGE (veja tools/gerar_mapa.py) e a ligação entre
os dois é o código IBGE (`cdi`) que o próprio TSE traz no arquivo de configuração das cidades.
"""
from contador.recursos import mapa


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
        lider = inteiro["lider"]
        resumo["lider"] = {chave: lider[chave] for chave in ("nome", "partido", "percentual", "eleito", "segundo_turno")}
        resumo["margem"], resumo["margem_votos"] = inteiro["margem"], inteiro["margem_votos"]
    elif inteiro["situacao"] == "empate":
        resumo["empatados"] = [{"nome": c["nome"], "partido": c["partido"]} for c in inteiro["empatados"]]
    return resumo


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
