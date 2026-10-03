#!/usr/bin/env python3
"""Contador de votos em tempo real: totalização oficial do TSE (Eleições 2026).

Lê os arquivos JSON de resultado unificado (EA20) publicados pelo TSE e mostra
o placar no terminal. Não conta votos por conta própria: toda a informação vem
do TSE. Só a divulgação oficial do TSE tem valor legal.

Exemplos:
    python3 contador.py                              # presidente, Brasil
    python3 contador.py -c governador --uf sp        # governador de SP
    python3 contador.py -c senador --uf mg --top 5
    python3 contador.py --ambiente simulado          # dados de teste do TSE
"""
import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from collections import namedtuple

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

# O TSE bloqueia o IP por 10 minutos ao passar de 100 req/s e após muitos 404 seguidos.
ESPERA_BLOQUEIO = 600
ESPERA_MAXIMA_ERRO = 120

Resposta = namedtuple("Resposta", "status dados etag")


def uf_valida(cargo, uf):
    """'br' só existe para presidente; distrital só no DF; estadual em todas as UFs menos o DF."""
    if cargo == "presidente" and uf == "br":
        return True
    if cargo == "deputado-distrital":
        return uf == "df"
    if cargo == "deputado-estadual":
        return uf in UFS and uf != "df"
    return uf in UFS


def montar_url(ambiente, cargo, uf, turno, eleicao=None):
    codigo_cargo, tipo = CARGOS[cargo]
    config = AMBIENTES[ambiente]
    codigo_eleicao = eleicao or config["eleicoes"][tipo][turno - 1]
    arquivo = f"{uf}-c{codigo_cargo:04d}-e{codigo_eleicao:06d}-u.json"
    return f"{config['base']}/{codigo_eleicao}/dados/{uf}/{arquivo}"


def buscar(url, etag=None):
    cabecalhos = {"Accept-Encoding": "gzip", "User-Agent": "contador-votos/1.0"}
    if etag:
        cabecalhos["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=cabecalhos), timeout=20
        ) as resp:
            corpo = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                corpo = gzip.decompress(corpo)
            return Resposta(resp.status, json.loads(corpo), resp.headers.get("ETag"))
    except urllib.error.HTTPError as erro:  # inclui 304 Not Modified
        return Resposta(erro.code, None, etag)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Resposta(0, None, etag)


def inteiro(valor):
    return int(valor or 0)


def milhar(valor):
    return f"{inteiro(valor):,}".replace(",", ".")


def candidatos(dados):
    """Candidatos do arquivo, do mais votado para o menos votado."""
    lista = [
        {**cand, "partido": partido["sg"]}
        for cargo in dados["carg"]
        for agrupamento in cargo["agr"]
        for partido in agrupamento["par"]
        for cand in partido["cand"]
    ]
    return sorted(lista, key=lambda c: (-inteiro(c["vap"]), c["nm"]))


def situacao(cand):
    marcas = []
    if cand.get("dvt") not in (None, "", "Válido"):
        marcas.append(cand["dvt"])
    if cand.get("st"):
        marcas.append(cand["st"])
    return " / ".join(marcas)


def barra(percentual, lider, largura=24):
    """Barra proporcional ao líder da lista (o líder ocupa a largura inteira)."""
    valor, maximo = (float(p.replace(",", ".")) for p in (percentual, lider))
    return "█" * round(valor / maximo * largura) if maximo else ""


def renderizar(dados, args, aviso=""):
    secoes, eleitores, votos = dados["s"], dados["e"], dados["v"]
    final = dados.get("tf") == "s"
    linhas = [
        f"ELEIÇÕES 2026 · {args.turno}º TURNO · {args.cargo.upper()} · {args.uf.upper()}"
        + ("   [DADOS SIMULADOS DO TSE]" if args.ambiente == "simulado" else ""),
        f"Totalização {'FINAL' if final else 'PARCIAL'}"
        f" · seções apuradas {milhar(secoes['st'])} de {milhar(secoes['ts'])}"
        f" ({secoes['pst']}%)",
        f"Última totalização: {dados.get('dt') or '—'} {dados.get('ht') or ''}".rstrip()
        + f" · arquivo gerado {dados['dg']} {dados['hg']} (Brasília)",
        "",
        f"Eleitores aptos {milhar(eleitores['te'])}"
        f" · comparecimento {milhar(eleitores['c'])} ({eleitores['pc']}%)"
        f" · abstenção {milhar(eleitores['a'])} ({eleitores['pa']}%)",
        f"Total de votos {milhar(votos['tv'])}"
        f" · brancos {milhar(votos['vb'])} ({votos['pvb']}%)"
        f" · nulos {milhar(votos['tvn'])} ({votos['ptvn']}%)",
        "",
        f"{'#':>3} {'Nº':>5}  {'Candidato':<30} {'Partido':<8} {'Votos':>13} {'%':>7}",
    ]
    ranking = candidatos(dados)[: args.top]
    for posicao, cand in enumerate(ranking, start=1):
        linhas.append(
            f"{posicao:>3} {cand['n']:>5}  {(cand.get('nmu') or cand['nm'])[:30]:<30}"
            f" {cand['partido'][:8]:<8} {milhar(cand['vap']):>13} {cand['pvap']:>7}"
            f"  {barra(cand['pvap'], ranking[0]['pvap'])} {situacao(cand)}".rstrip()
        )
    linhas += [
        "",
        "Fonte: TSE (resultados.tse.jus.br). Percentuais sobre votos válidos, como no TSE.",
        aviso or f"Atualiza a cada {args.intervalo}s. Ctrl+C para sair.",
    ]
    return "\n".join(linhas)


def mostrar(texto, uma_vez):
    if not uma_vez and sys.stdout.isatty():
        sys.stdout.write("\033[H\033[J")
    print(texto, flush=True)


def executar(args):
    url = montar_url(args.ambiente, args.cargo, args.uf, args.turno, args.eleicao)
    dados, etag, falhas = None, None, 0
    while True:
        resposta = buscar(url, etag)
        espera = args.intervalo
        aviso = ""
        if resposta.status == 200:
            dados, etag, falhas = resposta.dados, resposta.etag, 0
        elif resposta.status == 304:
            falhas = 0
        elif resposta.status == 404 and dados is None:
            sys.exit(f"Arquivo não encontrado: {url}\nConfira --cargo, --uf e --turno.")
        elif resposta.status in (403, 429):
            espera = ESPERA_BLOQUEIO
            aviso = f"TSE limitou o acesso (HTTP {resposta.status}). Nova tentativa em {espera}s."
        else:
            falhas += 1
            espera = min(args.intervalo * 2**falhas, ESPERA_MAXIMA_ERRO)
            aviso = f"Falha ao ler o TSE (HTTP {resposta.status}). Mostrando último dado. Nova tentativa em {espera}s."
        if dados is not None:
            mostrar(renderizar(dados, args, aviso), args.uma_vez)
        if args.uma_vez:
            return
        time.sleep(espera)


def ler_argumentos(argv=None):
    parser = argparse.ArgumentParser(description="Contador de votos em tempo real (TSE, 2026).")
    parser.add_argument("-c", "--cargo", choices=CARGOS, default="presidente")
    parser.add_argument("--uf", help="sigla da UF; 'br' (padrão) só para presidente")
    parser.add_argument("--turno", type=int, choices=(1, 2), default=1)
    parser.add_argument("--ambiente", choices=AMBIENTES, default="oficial")
    parser.add_argument("--eleicao", type=int, help="código da eleição no TSE (sobrescreve o padrão)")
    parser.add_argument("--top", type=int, default=15, help="quantos candidatos mostrar")
    parser.add_argument("--intervalo", type=int, default=10, help="segundos entre consultas (mín. 10)")
    parser.add_argument("--uma-vez", action="store_true", help="consulta uma vez e sai")
    args = parser.parse_args(argv)
    args.uf = (args.uf or ("br" if args.cargo == "presidente" else "")).lower()
    if not uf_valida(args.cargo, args.uf):
        parser.error(f"--uf inválida para {args.cargo}: use uma de {', '.join(UFS)}")
    if args.intervalo < 10:
        parser.error("--intervalo mínimo é 10 segundos (limite de acesso do TSE)")
    return args


if __name__ == "__main__":
    try:
        executar(ler_argumentos())
    except KeyboardInterrupt:
        print()
