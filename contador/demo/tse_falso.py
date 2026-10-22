"""Um TSE falso: a apuração avança sozinha e nada sai da máquina (uso: `python3 -m contador.demo`).

Troca `cliente.buscar` por dados sintéticos no formato do TSE e sobe o servidor de sempre.
Só o ambiente "simulado" responde; o "oficial" dá 404, para ninguém confundir demonstração
com dado real. Candidatos e números são inventados (os partidos são reais, para testar as
cores). Cobre presidente, governador e senador nos dois turnos e os deputados (federal, estadual e
distrital) no 1º; os deputados trazem federações e eleitos a partir de metade da apuração.
A apuração começa zerada, ganha uma totalização nova a cada `--passo` segundos e termina
em `--duracao` segundos.
"""
import functools
import json
import math
import random
import re
import time
import zlib

from contador import caminhos
from contador.tse import catalogo, cliente


BASE = catalogo.AMBIENTES["simulado"]["base"]
ELEICOES = {  # código da eleição -> (tipo, turno)
    codigo: (tipo, turno)
    for tipo, codigos in catalogo.AMBIENTES["simulado"]["eleicoes"].items()
    for turno, codigo in enumerate(codigos, start=1)
}
CARGOS = {codigo: nome for nome, (codigo, _) in catalogo.CARGOS.items()}
ARQUIVO = re.compile(rf"^{re.escape(BASE)}/(\d+)/dados/([a-z]{{2}})/[a-z]{{2}}(\d{{5}})?-c(\d{{4}})-e\d{{6}}-u\.json$")
CONFIG = re.compile(rf"^{re.escape(BASE)}/(\d+)/config/mun-e\d{{6}}-cm\.json$")

NOMES = ["Ana Lima", "Bruno Castro", "Carla Rocha", "Davi Moreira", "Elisa Prado",
         "Fábio Nunes", "Gisele Alves", "Hugo Teles", "Iara Melo", "João Faria"]
PARTIDOS = ["PT", "PL", "REPUBLICANOS", "PSD", "UNIÃO", "MDB", "PP", "PSB", "PSOL", "NOVO", "PDT", "PSDB"]
PRESIDENTES = [  # (número, nome, partido, peso nacional)
    ("13", "Ana Lima", "PT", 0.36), ("22", "Bruno Castro", "PL", 0.33), ("55", "Carla Rocha", "PSD", 0.11),
    ("30", "Davi Moreira", "NOVO", 0.08), ("40", "Elisa Prado", "PSB", 0.07), ("50", "Fábio Nunes", "PSOL", 0.05),
]
SEGUNDO_TURNO_PRESIDENTE = ("13", "22")
CIDADES = ["Alfa", "Beta", "Gama", "Delta", "Ômega"]
DATA = "25/10/2026"
RELOGIO = {"inicio": time.time(), "passo": 10, "duracao": 300}


def semente(*partes):
    return zlib.crc32(":".join(map(str, partes)).encode())


SECOES = {uf: 3000 + semente("secoes", uf) % 40000 for uf in catalogo.UFS}
SECOES["zz"] = 1500 + semente("secoes", "zz") % 2500  # exterior: só presidente


def codigo_cidade(uf, indice):
    return f"{10000 + 1000 * catalogo.UFS.index(uf) + indice}"


@functools.lru_cache(maxsize=None)
def cidades_da_uf(uf):
    """[(código TSE, código IBGE, nome)]: uma cidade por município do desenho da UF (geo/<uf>.json), para o mapa
    por município funcionar na demonstração; sem o arquivo, as 5 cidades inventadas."""
    arquivo = caminhos.WEB / "geo" / f"{uf}.json"
    if arquivo.is_file():
        ibge = sorted(json.loads(arquivo.read_text(encoding="utf-8"))["m"])
        nomes = [f"{CIDADES[i % len(CIDADES)]} {i // len(CIDADES) + 1}" for i in range(len(ibge))]
    else:
        ibge, nomes = [str(9000000 + 100 * catalogo.UFS.index(uf) + i) for i in range(len(CIDADES))], CIDADES
    return tuple((codigo_cidade(uf, i), codigo, nome) for i, (codigo, nome) in enumerate(zip(ibge, nomes)))


def lista_de_cidades():
    return {"abr": [
        {"cd": uf, "mu": [{"cd": tse, "cdi": ibge, "nm": nome.upper(), "c": "s" if i == 0 else "n"}
                          for i, (tse, ibge, nome) in enumerate(cidades_da_uf(uf))]}
        for uf in catalogo.UFS
    ]}


def renormalizar(base):
    total = sum(peso for *_, peso in base)
    return [(n, nome, partido, peso / total) for n, nome, partido, peso in base]


def candidatos_do_cargo(cargo, uf):
    """[(número, nome, partido, peso)] com pesos que somam 1: o resultado final do 1º turno na UF."""
    if cargo == "presidente":
        return renormalizar([
            (n, nome, partido, peso * math.exp(random.Random(semente("pres", uf, n)).gauss(0, 0.45)))
            for n, nome, partido, peso in PRESIDENTES
        ])
    rng = random.Random(semente(cargo, uf))
    quantos = rng.randint(3, 5) if cargo == "governador" else 6
    partidos = rng.sample(PARTIDOS, quantos)
    primeiro = semente(uf)
    pesos = [rng.uniform(0.2, 1.0) ** 2 for _ in range(quantos)]
    pesos[0] *= rng.uniform(1.0, 3.0)
    return renormalizar([
        (str(10 + 5 * i + rng.randint(0, 4)), NOMES[(primeiro + i) % len(NOMES)], partidos[i], pesos[i])
        for i in range(quantos)
    ])


def base_do_turno(cargo, uf, turno):
    """Candidatos do turno ou None quando o TSE não publicaria o arquivo (governador que já ganhou)."""
    lista = candidatos_do_cargo(cargo, uf)
    if turno == 1:
        return lista
    if cargo == "presidente":
        return renormalizar([c for c in lista if c[0] in SEGUNDO_TURNO_PRESIDENTE])
    dois = sorted(lista, key=lambda c: -c[3])[:2]
    return None if dois[0][3] >= 0.5 else renormalizar(dois)


def parcelas_ate(base, lugar, p):
    """Parcela de cada candidato entre os votos já apurados: as primeiras seções favorecem uns, as últimas outros."""
    ajustadas = []
    for n, _, _, peso in base:
        vies = random.Random(semente("vies", lugar, n)).uniform(-0.06, 0.06)
        ajustadas.append(max(peso + vies * (1 - p), 0.001))
    total = sum(ajustadas)
    return [a / total for a in ajustadas]


def numeros(cargo, uf, turno, municipio, p):
    base = base_do_turno(cargo, uf, turno)
    if base is None:
        return None
    secoes = SECOES[uf]
    if municipio:
        secoes = max(20, secoes // 15)
        base = renormalizar([
            (n, nome, partido, peso * math.exp(random.Random(semente("cid", municipio, n)).gauss(0, 0.3)))
            for n, nome, partido, peso in base
        ])
    parcelas = parcelas_ate(base, municipio or uf, p)
    totais_da_apuracao = totais(secoes, p)
    return {
        "base": [(n, nome, partido) for n, nome, partido, _ in base],
        **totais_da_apuracao,
        "votos": {n: round(totais_da_apuracao["validos"] * parcela) for (n, *_), parcela in zip(base, parcelas)},
    }


def totais(secoes, p):
    """Seções, eleitores e votos (válidos, brancos e nulos) quando a apuração está em `p` (0 a 1)."""
    aptos = secoes * 280
    comparecimento = round(aptos * 0.79 * p)
    brancos = round(comparecimento * 0.03)
    nulos = round(comparecimento * 0.05)
    return {
        "secoes": secoes, "apuradas": round(secoes * p), "aptos": aptos, "apurados": round(aptos * p),
        "comparecimento": comparecimento, "brancos": brancos, "nulos": nulos, "validos": comparecimento - brancos - nulos,
    }


def numeros_do_brasil(turno, p):
    """Presidente no Brasil: a soma das 27 UFs e do exterior, para o mapa e o placar nacional baterem."""
    soma = None
    for uf in (*catalogo.UFS, "zz"):
        parte = numeros("presidente", uf, turno, "", p)
        if soma is None:
            soma = {**parte, "votos": dict(parte["votos"])}
            continue
        for campo in ("secoes", "apuradas", "aptos", "apurados", "comparecimento", "brancos", "nulos", "validos"):
            soma[campo] += parte[campo]
        for n, votos in parte["votos"].items():
            soma["votos"][n] += votos
    return soma


def rotulos_finais(cargo, turno, n, ordem):
    """Situação de cada candidato no fim da apuração (antes disso o TSE não marca ninguém)."""
    primeiro = ordem[0][0]
    if cargo == "senador":
        eleitos = {c[0] for c in ordem[:2]}
        return {c[0]: "Eleito" if c[0] in eleitos else "Não eleito" for c in ordem}
    if turno == 2 or n["votos"][primeiro] * 2 > n["validos"]:
        return {c[0]: "Eleito" if c[0] == primeiro else "Não eleito" for c in ordem}
    dois = {c[0] for c in ordem[:2]}
    return {c[0]: "2º turno" if c[0] in dois else "Não eleito" for c in ordem}


def pct(parte, total):
    return f"{100 * parte / total if total else 0:.2f}".replace(".", ",")


def relogio(p):
    horas, resto = divmod(17 * 3600 + int(p * 4 * 3600), 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def cabecalho(n, p):
    """Campos do arquivo que não dependem do cargo: horário, seções, eleitores e votos."""
    final = p >= 1
    hora = relogio(p)
    return {
        "tf": "s" if final else "n",
        "dt": DATA if p > 0 else "", "ht": hora if p > 0 else "",
        "dg": DATA, "hg": hora if p > 0 else "16:59:00",
        "s": {"ts": str(n["secoes"]), "st": str(n["apuradas"]), "pst": pct(n["apuradas"], n["secoes"])},
        "e": {"te": str(n["aptos"]), "c": str(n["comparecimento"]), "pc": pct(n["comparecimento"], n["apurados"]),
              "a": str(n["apurados"] - n["comparecimento"]), "pa": pct(n["apurados"] - n["comparecimento"], n["apurados"])},
        "v": {"tv": str(n["comparecimento"]), "vb": str(n["brancos"]), "pvb": pct(n["brancos"], n["comparecimento"]),
              "tvn": str(n["nulos"]), "ptvn": pct(n["nulos"], n["comparecimento"])},
    }


def montar(cargo, uf, turno, municipio, p):
    n = numeros_do_brasil(turno, p) if uf == "br" else numeros(cargo, uf, turno, municipio, p)
    if n is None:
        return None
    final = p >= 1
    ordem = sorted(n["base"], key=lambda c: -n["votos"][c[0]])
    rotulos = rotulos_finais(cargo, turno, n, ordem) if final else {}
    return {
        **cabecalho(n, p),
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [{
                "n": numero, "nm": nome.upper(), "nmu": nome.upper(), "dvt": "Válido",
                "vap": str(n["votos"][numero]), "pvap": pct(n["votos"][numero], n["validos"]),
                "st": rotulos.get(numero, ""),
            }]}]}
            for numero, nome, partido in n["base"]
        ]}],
    }


# ---- deputados ----

FEDERACOES = {  # número -> (sigla, partidos), como as federações reais de 2026
    "101": ("PT/PC do B/PV", ["PT", "PC do B", "PV"]), "104": ("UNIÃO/PP", ["UNIÃO", "PP"]),
    "102": ("PSOL/REDE", ["PSOL", "REDE"]), "100": ("PSDB/CIDADANIA", ["PSDB", "CIDADANIA"]),
}
PARTIDOS_DEPUTADOS = ["PT", "PC do B", "PV", "PL", "REPUBLICANOS", "PSD", "UNIÃO", "PP", "MDB", "PSB", "PSOL", "REDE",
                      "NOVO", "PDT", "PSDB", "CIDADANIA", "PODE", "AVANTE"]
PRIMEIROS = ["ANA", "BRUNO", "CARLA", "DAVI", "ELISA", "FÁBIO", "GISELE", "HUGO", "IARA", "JOÃO", "KAREN", "LUCAS", "MARTA", "NELSON", "ÓLIVIA", "PAULO"]
SOBRENOMES = ["LIMA", "CASTRO", "ROCHA", "MOREIRA", "PRADO", "NUNES", "ALVES", "TELES", "MELO", "FARIA", "COSTA", "SOUZA", "DIAS", "RAMOS", "BORGES", "MENDES"]
CARGOS_DEPUTADOS = ("deputado-federal", "deputado-estadual", "deputado-distrital")


def distribuir(total, pesos, minimo):
    """Divide `total` cadeiras entre as chaves de `pesos`, no mínimo `minimo` cada, pelo maior resto."""
    livre = total - minimo * len(pesos)
    soma = sum(pesos.values())
    cotas = {k: livre * v / soma for k, v in pesos.items()}
    partes = {k: minimo + int(c) for k, c in cotas.items()}
    for k in sorted(cotas, key=lambda k: (int(cotas[k]) - cotas[k], k))[: total - sum(partes.values())]:
        partes[k] += 1
    return partes


VAGAS_FEDERAL = distribuir(513, {uf: SECOES[uf] for uf in catalogo.UFS}, 8)


def vagas_de(cargo, uf):
    return {"deputado-federal": VAGAS_FEDERAL[uf], "deputado-estadual": 3 * VAGAS_FEDERAL[uf], "deputado-distrital": 24}[cargo]


def montar_deputados(cargo, uf, p):
    """Arquivo de deputados de uma UF no formato do TSE: agrupamentos (federações e partidos), candidatos e eleitos."""
    rng = random.Random(semente(cargo, uf, "deputados"))
    vagas = vagas_de(cargo, uf)
    n = totais(SECOES[uf], p)
    na_federacao = {sigla: numero for numero, (_, siglas) in FEDERACOES.items() for sigla in siglas}
    # agrupamentos: cada federação vale um só; os demais partidos entram sozinhos
    agrupamentos = {}
    for sigla in PARTIDOS_DEPUTADOS:
        chave = na_federacao.get(sigla, sigla)
        agrupamentos.setdefault(chave, []).append(sigla)
    forca = {chave: rng.uniform(0.3, 1.0) ** 2 for chave in agrupamentos}
    candidatos_por_agrupamento = {chave: max(2, round(vagas * 3.2 * f / sum(forca.values()) * len(forca) / 3)) for chave, f in forca.items()}
    todos = []  # (votos, chave do agrupamento, partido, indice)
    contador_de_nomes = 0
    for chave, siglas in agrupamentos.items():
        quantos = candidatos_por_agrupamento[chave]
        pesos = [rng.uniform(0.05, 1.0) ** 3 for _ in range(quantos)]
        soma_pesos = sum(pesos)
        for peso in pesos:
            todos.append([forca[chave] * peso / soma_pesos, chave, rng.choice(siglas), contador_de_nomes])
            contador_de_nomes += 1
    total_bruto = sum(c[0] for c in todos)
    for c in todos:
        c[0] = round(n["validos"] * 0.9 * c[0] / total_bruto * (1 + 0.04 * math.sin(c[3] + p * 6)))
    # quem fica com as cadeiras: D'Hondt entre os agrupamentos, e dentro de cada um os mais votados
    eleitos, cadeiras = set(), {}
    if p >= 0.5:
        soma_por_agrupamento = {chave: sum(c[0] for c in todos if c[1] == chave) for chave in agrupamentos}
        ganhas = dict.fromkeys(agrupamentos, 0)
        for _ in range(vagas):
            melhor = max(agrupamentos, key=lambda k: (soma_por_agrupamento[k] / (ganhas[k] + 1), k))
            ganhas[melhor] += 1
        for chave, quantas in ganhas.items():
            do_grupo = sorted((c for c in todos if c[1] == chave), key=lambda c: -c[0])[:quantas]
            eleitos.update(c[3] for c in do_grupo)
        cadeiras = ganhas
    final = p >= 1
    por_votos = sorted(todos, key=lambda c: -c[0])
    posicao = {c[3]: i for i, c in enumerate(por_votos)}

    def candidato(c):
        votos, _, sigla, indice = c
        nome = f"{PRIMEIROS[indice % 16]} {SOBRENOMES[(indice // 16 + indice) % 16]}"
        escolhido = indice in eleitos
        situacao = "Eleito por QP" if escolhido else ("Suplente" if posicao[indice] < vagas * 2 else "Não eleito") if final else ""
        return {"n": str(1000 + 10 * indice + PARTIDOS_DEPUTADOS.index(sigla)), "sqcand": str(250000000000 + indice), "nm": nome,
                "nmu": nome, "dvt": "Válido", "seq": str(indice + 1), "e": "s" if escolhido else "n", "st": situacao,
                "vap": str(votos), "pvap": pct(votos, n["validos"])}

    agr = []
    for chave, siglas in agrupamentos.items():
        federacao = FEDERACOES.get(chave)
        agr.append({
            "n": chave, "nm": f"FEDERAÇÃO {federacao[0]}" if federacao else siglas[0], "tp": "f" if federacao else "i",
            "com": federacao[0] if federacao else siglas[0], "vag": str(cadeiras.get(chave, 0)),
            "par": [{"n": str(10 + PARTIDOS_DEPUTADOS.index(sigla)), "sg": sigla, "nm": sigla, "nfed": chave if federacao else "",
                     "dvt": "Válido (legenda)", "cand": [candidato(c) for c in todos if c[1] == chave and c[2] == sigla]}
                    for sigla in siglas],
        })
    return {
        **cabecalho(n, p),
        "carg": [{"cd": str(catalogo.CARGOS[cargo][0]), "nv": str(vagas),
                  "fed": [{"n": numero, "sg": sigla, "com": sigla, "npar": []} for numero, (sigla, _) in FEDERACOES.items()],
                  "agr": agr}],
    }


def progresso():
    """(número da totalização atual, fração apurada de 0 a 1)."""
    passos = max(1, RELOGIO["duracao"] // RELOGIO["passo"])
    atual = min(passos, int((time.time() - RELOGIO["inicio"]) // RELOGIO["passo"]))
    return atual, atual / passos


def buscar_falso(url, etag=None):
    """No lugar de `cliente.buscar`: mesma assinatura e mesmos códigos (200, 304, 404)."""
    if CONFIG.match(url):
        return cliente.Resposta(304, None, '"cidades"') if etag == '"cidades"' else cliente.Resposta(200, lista_de_cidades(), '"cidades"')
    achado = ARQUIVO.match(url)
    if not achado:
        return cliente.Resposta(404, None, etag)
    eleicao, uf, municipio, codigo_cargo = int(achado[1]), achado[2], achado[3] or "", int(achado[4])
    cargo = CARGOS.get(codigo_cargo)
    tipo, turno = ELEICOES.get(eleicao, (None, None))
    if cargo in CARGOS_DEPUTADOS:
        valido = turno == 1 and not municipio and catalogo.uf_valida(cargo, uf) and uf != "br"
        if not valido:
            return cliente.Resposta(404, None, etag)
        passo, p = progresso()
        marca = f'"{passo}"'
        if etag == marca:
            return cliente.Resposta(304, None, marca)
        return cliente.Resposta(200, montar_deputados(cargo, uf, p), marca)
    if cargo not in ("presidente", "governador", "senador") or catalogo.CARGOS[cargo][1] != tipo:
        return cliente.Resposta(404, None, etag)
    if uf in ("br", "zz") and not (cargo == "presidente" and not municipio):
        return cliente.Resposta(404, None, etag)
    if uf not in ("br", "zz", *catalogo.UFS):
        return cliente.Resposta(404, None, etag)
    if municipio and municipio not in {tse for tse, _, _ in cidades_da_uf(uf)}:
        return cliente.Resposta(404, None, etag)
    passo, p = progresso()
    marca = f'"{passo}"'
    if etag == marca:
        return cliente.Resposta(304, None, marca)
    dados = montar(cargo, uf, turno, municipio, p)
    return cliente.Resposta(404, None, etag) if dados is None else cliente.Resposta(200, dados, marca)
