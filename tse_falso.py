#!/usr/bin/env python3
"""Demonstração com um TSE falso: a apuração avança sozinha e nada sai da máquina.

    python3 tse_falso.py                  # http://127.0.0.1:8000/?ambiente=simulado
    python3 tse_falso.py --duracao 600 --passo 15 --porta 8010

Troca `contador.buscar` por dados sintéticos no formato do TSE e sobe o servidor de sempre.
Só o ambiente "simulado" responde; o "oficial" dá 404, para ninguém confundir demonstração
com dado real. Candidatos e números são inventados (os partidos são reais, para testar as
cores). Cobre presidente, governador e senador nos dois turnos; os outros cargos dão 404.
A apuração começa zerada, ganha uma totalização nova a cada `--passo` segundos e termina
em `--duracao` segundos.
"""
import argparse
import math
import random
import re
import sys
import time
import zlib

import contador
import servidor

BASE = contador.AMBIENTES["simulado"]["base"]
ELEICOES = {  # código da eleição -> (tipo, turno)
    codigo: (tipo, turno)
    for tipo, codigos in contador.AMBIENTES["simulado"]["eleicoes"].items()
    for turno, codigo in enumerate(codigos, start=1)
}
CARGOS = {codigo: nome for nome, (codigo, _) in contador.CARGOS.items()}
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


SECOES = {uf: 3000 + semente("secoes", uf) % 40000 for uf in contador.UFS}
SECOES["zz"] = 1500 + semente("secoes", "zz") % 2500  # exterior: só presidente


def codigo_cidade(uf, indice):
    return f"{10000 + 100 * contador.UFS.index(uf) + indice}"


def lista_de_cidades():
    return {"abr": [
        {"cd": uf, "mu": [{"cd": codigo_cidade(uf, i), "nm": nome.upper(), "c": "s" if i == 0 else "n"}
                          for i, nome in enumerate(CIDADES)]}
        for uf in contador.UFS
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
    aptos = secoes * 280
    comparecimento = round(aptos * 0.79 * p)
    brancos = round(comparecimento * 0.03)
    nulos = round(comparecimento * 0.05)
    validos = comparecimento - brancos - nulos
    parcelas = parcelas_ate(base, municipio or uf, p)
    return {
        "base": [(n, nome, partido) for n, nome, partido, _ in base],
        "secoes": secoes, "apuradas": round(secoes * p), "aptos": aptos, "apurados": round(aptos * p),
        "comparecimento": comparecimento, "brancos": brancos, "nulos": nulos, "validos": validos,
        "votos": {n: round(validos * parcela) for (n, *_), parcela in zip(base, parcelas)},
    }


def numeros_do_brasil(turno, p):
    """Presidente no Brasil: a soma das 27 UFs e do exterior, para o mapa e o placar nacional baterem."""
    soma = None
    for uf in (*contador.UFS, "zz"):
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


def montar(cargo, uf, turno, municipio, p):
    n = numeros_do_brasil(turno, p) if uf == "br" else numeros(cargo, uf, turno, municipio, p)
    if n is None:
        return None
    final = p >= 1
    ordem = sorted(n["base"], key=lambda c: -n["votos"][c[0]])
    rotulos = rotulos_finais(cargo, turno, n, ordem) if final else {}
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
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [{
                "n": numero, "nm": nome.upper(), "nmu": nome.upper(), "dvt": "Válido",
                "vap": str(n["votos"][numero]), "pvap": pct(n["votos"][numero], n["validos"]),
                "st": rotulos.get(numero, ""),
            }]}]}
            for numero, nome, partido in n["base"]
        ]}],
    }


def progresso():
    """(número da totalização atual, fração apurada de 0 a 1)."""
    passos = max(1, RELOGIO["duracao"] // RELOGIO["passo"])
    atual = min(passos, int((time.time() - RELOGIO["inicio"]) // RELOGIO["passo"]))
    return atual, atual / passos


def buscar_falso(url, etag=None):
    """No lugar de `contador.buscar`: mesma assinatura e mesmos códigos (200, 304, 404)."""
    if CONFIG.match(url):
        return contador.Resposta(304, None, '"cidades"') if etag == '"cidades"' else contador.Resposta(200, lista_de_cidades(), '"cidades"')
    achado = ARQUIVO.match(url)
    if not achado:
        return contador.Resposta(404, None, etag)
    eleicao, uf, municipio, codigo_cargo = int(achado[1]), achado[2], achado[3] or "", int(achado[4])
    cargo = CARGOS.get(codigo_cargo)
    tipo, turno = ELEICOES.get(eleicao, (None, None))
    if cargo not in ("presidente", "governador", "senador") or contador.CARGOS[cargo][1] != tipo:
        return contador.Resposta(404, None, etag)
    if uf in ("br", "zz") and not (cargo == "presidente" and not municipio):
        return contador.Resposta(404, None, etag)
    if uf not in ("br", "zz", *contador.UFS):
        return contador.Resposta(404, None, etag)
    if municipio and municipio not in {codigo_cidade(uf, i) for i in range(len(CIDADES))}:
        return contador.Resposta(404, None, etag)
    passo, p = progresso()
    marca = f'"{passo}"'
    if etag == marca:
        return contador.Resposta(304, None, marca)
    dados = montar(cargo, uf, turno, municipio, p)
    return contador.Resposta(404, None, etag) if dados is None else contador.Resposta(200, dados, marca)


def main():
    parser = argparse.ArgumentParser(description="Demonstração com TSE falso (nada sai da máquina).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--duracao", type=int, default=300, help="segundos da apuração, de 0 a 100%%")
    parser.add_argument("--passo", type=int, default=10, help="segundos entre totalizações novas")
    args = parser.parse_args()
    RELOGIO.update(inicio=time.time(), passo=max(1, args.passo), duracao=max(args.passo, args.duracao))
    contador.buscar = buscar_falso
    print(f"TSE FALSO: dados inventados. Abra http://{args.host}:{args.porta}/?ambiente=simulado", flush=True)
    sys.argv = ["servidor.py", "--host", args.host, "--porta", str(args.porta)]
    servidor.main()


if __name__ == "__main__":
    main()
