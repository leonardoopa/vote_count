"""Deputados: resumo de cada UF (cadeiras por partido e bloco, mais votados) e a soma do país.

São funções puras: recebem o arquivo do TSE já lido (`contador.buscar`) e devolvem dicts pequenos. Quem
busca os arquivos é o varredor (`varredura.py`), que guarda só o resumo, nunca o arquivo inteiro.
"""
import heapq

import contador

CADEIRAS_DA_CAMARA = 513
TOP_POR_UF = 20          # mais votados guardados por UF (o país mostra os maiores de todos)
TOP_DO_PAIS = 20
INTERVALO_APURANDO_S = 90
INTERVALO_FINAL_S = 1800


def eleito(cand):
    """O TSE marca 'Eleito por QP', 'Eleito por média' e semelhantes; suplentes e 'Não eleito' ficam de fora."""
    return (cand.get("st") or "").lower().startswith("eleito")


def intervalo(resumo):
    """Segundos até buscar o arquivo da UF de novo: devagar depois de apurado."""
    return INTERVALO_FINAL_S if resumo and resumo["final"] else INTERVALO_APURANDO_S


def resumir_arquivo(dados, uf):
    """O que o hemiciclo e o ranking precisam do arquivo de deputados de uma UF."""
    cargo = dados["carg"][0]
    partidos, blocos, melhores = {}, [], []
    for agrupamento in cargo["agr"]:
        siglas, cadeiras = [], 0
        for partido in agrupamento["par"]:
            siglas.append(partido["sg"])
            for cand in partido["cand"]:
                votos, escolhido = contador.inteiro(cand["vap"]), eleito(cand)
                if escolhido:
                    partidos[partido["sg"]] = partidos.get(partido["sg"], 0) + 1
                    cadeiras += 1
                # (votos, número como desempate estável) vem antes dos dados para o heap comparar só números
                melhores.append((votos, cand["n"], cand.get("nmu") or cand["nm"], partido["sg"], escolhido))
        blocos.append({
            "nome": agrupamento.get("com") or agrupamento.get("nm") or "/".join(siglas),
            "federacao": agrupamento.get("tp") == "f", "partidos": siglas, "cadeiras": cadeiras,
        })
    secoes = dados["s"]
    return {
        "uf": uf,
        "vagas": contador.inteiro(cargo.get("nv")),
        "eleitos": sum(partidos.values()),
        "partidos": partidos,
        "blocos": blocos,
        "mais_votados": [
            {"nome": nome, "partido": partido, "numero": numero, "votos": votos, "eleito": escolhido, "uf": uf}
            for votos, numero, nome, partido, escolhido in heapq.nlargest(TOP_POR_UF, melhores, key=lambda c: (c[0], c[1]))
        ],
        "secoes": {"total": contador.inteiro(secoes["ts"]), "apuradas": contador.inteiro(secoes["st"])},
        "final": dados.get("tf") == "s",
    }


def camara(resumos, total=CADEIRAS_DA_CAMARA):
    """Hemiciclo da Câmara a partir dos resumos das UFs que já responderam ({uf: resumo ou None})."""
    por_partido, por_bloco, bloco_do_partido = {}, {}, {}
    vagas = eleitos = com_dados = 0
    for resumo in resumos.values():
        if not resumo:
            continue
        com_dados += 1
        vagas += resumo["vagas"]
        eleitos += resumo["eleitos"]
        for sigla, n in resumo["partidos"].items():
            por_partido[sigla] = por_partido.get(sigla, 0) + n
        for bloco in resumo["blocos"]:
            atual = por_bloco.setdefault(bloco["nome"], {"bloco": bloco["nome"], "federacao": bloco["federacao"], "partidos": [], "cadeiras": 0})
            atual["cadeiras"] += bloco["cadeiras"]
            for sigla in bloco["partidos"]:
                if sigla not in atual["partidos"]:
                    atual["partidos"].append(sigla)
                bloco_do_partido[sigla] = bloco["nome"]
    ordem_dos_blocos = sorted(por_bloco.values(), key=lambda b: (-b["cadeiras"], b["bloco"]))
    return {
        "casa": "camara",
        "total": total,
        "vagas_conhecidas": vagas,
        "eleitos": eleitos,
        "ufs_com_dados": com_dados,
        "ufs_total": len(resumos),
        "partidos": [
            {"partido": sigla, "cadeiras": n, "bloco": bloco_do_partido.get(sigla, sigla)}
            for sigla, n in sorted(por_partido.items(), key=lambda par: (-par[1], par[0]))
        ],
        "blocos": [b for b in ordem_dos_blocos if b["cadeiras"]],
        "final": bool(com_dados) and com_dados == len(resumos) and all(r["final"] for r in resumos.values() if r),
    }


def mais_votados(resumos, limite=TOP_DO_PAIS):
    """Os candidatos mais votados do país, somando os mais votados guardados de cada UF."""
    todos = [c for r in resumos.values() if r for c in r["mais_votados"]]
    todos.sort(key=lambda c: (-c["votos"], c["uf"], c["numero"]))
    return {
        "ufs_com_dados": sum(1 for r in resumos.values() if r),
        "ufs_total": len(resumos),
        "candidatos": [{"posicao": i, **c} for i, c in enumerate(todos[:limite], start=1)],
        "final": bool(resumos) and all(r and r["final"] for r in resumos.values()),
    }
