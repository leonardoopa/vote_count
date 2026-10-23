"""Placar de uma seleção (cargo, UF e cidade): o resumo que a API entrega em /api/resultado."""
from contador.tse import leitura


def resumir(dados, top, foto=None):
    """Placar de um arquivo do TSE: seções, eleitores, votos e os `top` primeiros candidatos.

    Com `foto` (função do `sqcand` do candidato para o endereço da foto), cada candidato ganha o campo `foto`.
    """
    secoes, eleitores, votos = dados["s"], dados["e"], dados["v"]
    todos = leitura.candidatos(dados)
    return {
        "final": dados.get("tf") == "s",
        "ultima_totalizacao": f"{dados.get('dt', '')} {dados.get('ht', '')}".strip(),
        "gerado": f"{dados['dg']} {dados['hg']}",
        "secoes": {
            "total": leitura.inteiro(secoes["ts"]),
            "apuradas": leitura.inteiro(secoes["st"]),
            "percentual": leitura.decimal(secoes["pst"]),
        },
        "eleitores": {
            "aptos": leitura.inteiro(eleitores["te"]),
            "comparecimento": leitura.inteiro(eleitores["c"]),
            "pct_comparecimento": leitura.decimal(eleitores["pc"]),
            "abstencao": leitura.inteiro(eleitores["a"]),
            "pct_abstencao": leitura.decimal(eleitores["pa"]),
        },
        "votos": {
            "total": leitura.inteiro(votos["tv"]),
            "brancos": leitura.inteiro(votos["vb"]),
            "pct_brancos": leitura.decimal(votos["pvb"]),
            "nulos": leitura.inteiro(votos["tvn"]),
            "pct_nulos": leitura.decimal(votos["ptvn"]),
        },
        "total_candidatos": len(todos),
        "candidatos": [_candidato(posicao, cand, foto) for posicao, cand in enumerate(todos[:top], start=1)],
    }


def _candidato(posicao, cand, foto):
    resumo = {
        "posicao": posicao,
        "numero": cand["n"],
        "nome": cand.get("nmu") or cand["nm"],
        "partido": cand["partido"],
        "votos": leitura.inteiro(cand["vap"]),
        "percentual": leitura.decimal(cand["pvap"]),
        "eleito": cand.get("st", "").lower().startswith("eleito"),
        "situacao": leitura.situacao(cand),
    }
    if foto:
        resumo["foto"] = foto(cand.get("sqcand"))
    return resumo
