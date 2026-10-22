"""Resultado por UF, para o mapa do Brasil, o painel por região e as disputas mais apertadas.

São funções puras: recebem `obter(url, ttl)` -> (dados, status, verificado_em), que o servidor
entrega como `CACHE.obter`, e não importam `servidor`. O cuidado com o TSE está em `consultar`.
"""
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait

import contador

TRABALHADORES = 6          # consultas ao TSE ao mesmo tempo, no máximo
PAUSA_S = 0.5              # espera de quem acabou de ir à rede: com 6, dá uns 10 pedidos por segundo
PRAZO_S = 25               # quanto o mapa espera pelas UFs; o que não chegou fica "sem dados" nesta rodada
LIMITE_404 = 3             # 404 que interrompem a rodada (o TSE bloqueia o IP depois de muitos seguidos)
TTL_UF = 20                # segundos no cache por UF; o placar principal usa 10, o mapa pode ser mais lento
TTL_PRIMEIRO_TURNO = 1800  # o 1º turno só diz quem foi ao 2º; depois de apurado não muda mais
IDADE_AVISO_S = 120        # dado de UF mais velho que isso ganha aviso


def decimal(texto):
    return float((texto or "0").replace(",", "."))


def situacao_do_candidato(cand):
    """'eleito', 'segundo_turno', 'nao_eleito' ou '' (o TSE só marca quando está decidido)."""
    texto = unicodedata.normalize("NFKD", cand.get("st") or "").casefold()
    letras = re.sub(r"[^a-z0-9]", "", texto)  # "2º turno" -> "2oturno"; "Não eleito" -> "naoeleito"
    if letras.startswith("eleit"):
        return "eleito"
    if re.fullmatch(r"2o?turno", letras):
        return "segundo_turno"
    return "nao_eleito" if letras else ""


def resumir_candidato(cand):
    situacao = situacao_do_candidato(cand)
    return {
        "numero": cand["n"],
        "nome": cand.get("nmu") or cand["nm"],
        "partido": cand["partido"],
        "votos": contador.inteiro(cand["vap"]),
        "percentual": decimal(cand["pvap"]),
        "eleito": situacao == "eleito",
        "segundo_turno": situacao == "segundo_turno",
    }


def resumir_uf(dados, com_votos=False):
    """O que o mapa precisa de um arquivo de UF: líder, segundo, margem e andamento da apuração.

    `situacao` diz como pintar: 'lider', 'zerado' (sem voto ou sem seção apurada), 'empate' (os
    primeiros com o mesmo número de votos). Só 'lider' tem líder: entre zeros ou empatados ninguém
    é escolhido. `com_votos` acrescenta os votos de todos os candidatos, para somar por região.
    """
    secoes = dados["s"]
    apuradas = contador.inteiro(secoes["st"])
    todos = contador.candidatos(dados)
    resumo = {
        "situacao": "lider",
        "lider": None,
        "segundo": None,
        "margem": None,
        "margem_votos": None,
        "secoes": {"total": contador.inteiro(secoes["ts"]), "apuradas": apuradas, "percentual": decimal(secoes["pst"])},
        "final": dados.get("tf") == "s",
    }
    if com_votos:
        resumo["votos"] = {cand["n"]: contador.inteiro(cand["vap"]) for cand in todos}
    votos = [contador.inteiro(cand["vap"]) for cand in todos]
    if not todos or not any(votos) or apuradas == 0:
        resumo["situacao"] = "zerado"
    elif len(todos) > 1 and votos[0] == votos[1]:
        resumo["situacao"] = "empate"
        resumo["empatados"] = [resumir_candidato(cand) for cand, v in zip(todos, votos) if v == votos[0]]
        resumo["margem"], resumo["margem_votos"] = 0.0, 0
    else:
        lider = resumir_candidato(todos[0])
        segundo = resumir_candidato(todos[1]) if len(todos) > 1 else None
        resumo["lider"], resumo["segundo"] = lider, segundo
        resumo["margem"] = round(lider["percentual"] - (segundo["percentual"] if segundo else 0), 2)
        resumo["margem_votos"] = lider["votos"] - (segundo["votos"] if segundo else 0)
    return resumo


def consultar(obter, urls, ttl=TTL_UF, pausa=PAUSA_S, prazo=PRAZO_S):
    """{uf: (dados, status, verificado_em)} das UFs consultadas; as que ficaram de fora não aparecem.

    `urls` é {uf: url}, e a primeira vai sozinha, como sentinela: se ela não volta com dados (404,
    bloqueio, TSE fora do ar), ninguém mais é consultado, para não gastar 404 à toa (o TSE bloqueia o
    IP depois de muitos) nem insistir num TSE que já está ruim. Com a sentinela boa, as outras vão em
    paralelo, uma pausa depois de cada pedido que foi à rede, e a rodada para de vez ao ver LIMITE_404
    respostas 404 ou qualquer 403/429. O que não chega em `prazo` segundos fica para a próxima rodada.
    """
    ufs = list(urls)
    if not ufs:
        return {}
    resultados = {ufs[0]: _pedir(obter, urls[ufs[0]], ttl)}
    if resultados[ufs[0]][0] is None:
        return resultados
    parar, trava, vistos_404 = threading.Event(), threading.Lock(), [0]

    def uma(uf):
        if parar.is_set():
            return uf, None
        inicio = time.monotonic()
        resposta = _pedir(obter, urls[uf], ttl)
        if time.monotonic() - inicio > 0.005:  # foi ao TSE (do cache sai em microssegundos)
            time.sleep(pausa)
        if resposta[0] is None:
            if resposta[1] == 404:
                with trava:
                    vistos_404[0] += 1
                    if vistos_404[0] >= LIMITE_404:
                        parar.set()
            elif resposta[1] in (403, 429):
                parar.set()
        return uf, resposta

    pool = ThreadPoolExecutor(max_workers=TRABALHADORES)
    futuros = [pool.submit(uma, uf) for uf in ufs[1:]]
    prontos, _ = wait(futuros, timeout=prazo)
    pool.shutdown(wait=False, cancel_futures=True)
    for futuro in prontos:
        uf, resposta = futuro.result()
        if resposta is not None:
            resultados[uf] = resposta
    return resultados


def _pedir(obter, url, ttl):
    try:
        return obter(url, ttl)
    except Exception:  # uma UF que dá erro não derruba as outras
        return None, 0, 0


def foram_ao_segundo_turno(dados):
    """Governo do 1º turno: alguém marcado '2º turno' pelo TSE. (Já eleito no 1º turno, o líder é 'Eleito'.)"""
    return any(situacao_do_candidato(cand) == "segundo_turno" for cand in contador.candidatos(dados))


def resumo_por_uf(obter, ambiente, cargo, turno, pausa=PAUSA_S, prazo=PRAZO_S, agora=time.time):
    """Mapa do Brasil: (corpo, None) ou (None, (status do TSE, mensagem para o caso de 404)).

    Presidente começa pelo arquivo nacional ('br'); governador, pela primeira UF. Sem ele, não se
    consulta mais nada. No 2º turno de governador só existem arquivos nas UFs que o TSE mandou para
    o 2º turno, e quem diz isso é o 1º turno: as outras nunca são consultadas.
    """
    presidente = cargo == "presidente"
    segundo_turno = cargo == "governador" and turno == 2
    consultaveis = list(contador.UFS)
    situacao_fixa = {}  # uf -> resumo que dispensa consulta (sem 2º turno, ou 1º turno indisponível)
    if segundo_turno:
        urls = {uf: contador.montar_url(ambiente, cargo, uf, 1) for uf in contador.UFS}
        primeiro = consultar(obter, urls, TTL_PRIMEIRO_TURNO, pausa, prazo)
        sentinela = primeiro.get(contador.UFS[0])
        if sentinela is None or sentinela[0] is None:
            return None, (sentinela[1] if sentinela else 0, "O TSE ainda não publicou o resultado do 1º turno, que diz quais estados têm 2º turno.")
        consultaveis = []
        for uf in contador.UFS:
            dados = primeiro.get(uf, (None, 0, 0))[0]
            if dados is None:
                situacao_fixa[uf] = {"situacao": "sem_dados"}
            elif foram_ao_segundo_turno(dados):
                consultaveis.append(uf)
            else:
                situacao_fixa[uf] = {"situacao": "sem_segundo_turno", "primeiro_turno": resumir_uf(dados)["lider"]}
    urls = {uf: contador.montar_url(ambiente, cargo, uf, turno) for uf in consultaveis}
    if presidente:
        urls = {"br": contador.montar_url(ambiente, cargo, "br", turno), **urls}
    respostas = consultar(obter, urls, TTL_UF, pausa, prazo)
    primeira = respostas.get(next(iter(urls), None))
    if urls and (primeira is None or primeira[0] is None):
        return None, (primeira[1] if primeira else 0, "O TSE ainda não publicou o resultado desta eleição.")

    ufs, nomes, sem_dados, mais_velho = {}, {}, 0, 0
    for uf in contador.UFS:
        resposta = respostas.get(uf)
        if uf in situacao_fixa:
            ufs[uf] = situacao_fixa[uf]
        elif resposta is None or resposta[0] is None:
            ufs[uf] = {"situacao": "sem_dados"}
        else:
            ufs[uf] = resumir_uf(resposta[0], com_votos=presidente)
            mais_velho = max(mais_velho, agora() - resposta[2])
            for cand in contador.candidatos(resposta[0]):
                nomes.setdefault(cand["n"], (cand.get("nmu") or cand["nm"], cand["partido"]))
        sem_dados += ufs[uf]["situacao"] == "sem_dados"
    com_dados = [u for u in ufs.values() if u["situacao"] not in ("sem_dados", "sem_segundo_turno")]
    corpo = {
        "cargo": cargo,
        "turno": turno,
        "ambiente": ambiente,
        "final": bool(com_dados) and not sem_dados and all(u["final"] for u in com_dados),
        "ufs": ufs,
        "idade_s": round(mais_velho),
    }
    if presidente:
        corpo["candidatos"] = _candidatos_do_pais(ufs, nomes)
    corpo["partidos"] = sorted({u[papel]["partido"] for u in ufs.values() for papel in ("lider", "segundo") if u.get(papel)})
    if sem_dados:
        corpo["aviso"] = f"O TSE não respondeu para {sem_dados} estado{'s' if sem_dados > 1 else ''} agora; eles aparecem sem dados."
    elif mais_velho > IDADE_AVISO_S:
        corpo["aviso"] = "O TSE não respondeu nas últimas tentativas; o mapa mostra os últimos dados recebidos."
    return corpo, None


def _candidatos_do_pais(ufs, nomes):
    """Candidatos que aparecem em alguma UF, do mais votado no conjunto das UFs para o menos."""
    total = {}
    for uf in ufs.values():
        for numero, votos in uf.get("votos", {}).items():
            total[numero] = total.get(numero, 0) + votos
    return [
        {"numero": numero, "nome": nomes[numero][0], "partido": nomes[numero][1], "votos": votos}
        for numero, votos in sorted(total.items(), key=lambda par: (-par[1], par[0]))
    ]
