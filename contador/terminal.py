"""Contador de votos em tempo real: totalização oficial do TSE (Eleições 2026).

Lê os arquivos JSON de resultado unificado (EA20) publicados pelo TSE e mostra
o placar no terminal. Não conta votos por conta própria: toda a informação vem
do TSE. Só a divulgação oficial do TSE tem valor legal.

Exemplos:
    python3 -m contador                              # presidente, Brasil
    python3 -m contador -c governador --uf sp        # governador de SP
    python3 -m contador -c senador --uf mg --top 5
    python3 -m contador -c governador --uf sp --cidade campinas   # só uma cidade
    python3 -m contador --ambiente simulado          # dados de teste do TSE
"""
import argparse
import sys
import time

from contador.tse import catalogo, cliente, leitura


def barra(percentual, lider, largura=24):
    """Barra proporcional ao líder da lista (o líder ocupa a largura inteira)."""
    valor, maximo = (float(p.replace(",", ".")) for p in (percentual, lider))
    return "█" * round(valor / maximo * largura) if maximo else ""


def renderizar(dados, args, aviso=""):
    secoes, eleitores, votos = dados["s"], dados["e"], dados["v"]
    final = dados.get("tf") == "s"
    linhas = [
        f"ELEIÇÕES 2026 · {args.turno}º TURNO · {args.cargo.upper()} · {args.uf.upper()}"
        + (f" · {args.cidade_nome.upper()}" if getattr(args, "cidade_nome", None) else "")
        + ("   [DADOS SIMULADOS DO TSE]" if args.ambiente == "simulado" else ""),
        f"Totalização {'FINAL' if final else 'PARCIAL'}"
        f" · seções apuradas {leitura.milhar(secoes['st'])} de {leitura.milhar(secoes['ts'])}"
        f" ({secoes['pst']}%)",
        f"Última totalização: {dados.get('dt') or '—'} {dados.get('ht') or ''}".rstrip()
        + f" · arquivo gerado {dados['dg']} {dados['hg']} (Brasília)",
        "",
        f"Eleitores aptos {leitura.milhar(eleitores['te'])}"
        f" · comparecimento {leitura.milhar(eleitores['c'])} ({eleitores['pc']}%)"
        f" · abstenção {leitura.milhar(eleitores['a'])} ({eleitores['pa']}%)",
        f"Total de votos {leitura.milhar(votos['tv'])}"
        f" · brancos {leitura.milhar(votos['vb'])} ({votos['pvb']}%)"
        f" · nulos {leitura.milhar(votos['tvn'])} ({votos['ptvn']}%)",
        "",
        f"{'#':>3} {'Nº':>5}  {'Candidato':<30} {'Partido':<8} {'Votos':>13} {'%':>7}",
    ]
    ranking = leitura.candidatos(dados)[: args.top]
    for posicao, cand in enumerate(ranking, start=1):
        linhas.append(
            f"{posicao:>3} {cand['n']:>5}  {(cand.get('nmu') or cand['nm'])[:30]:<30}"
            f" {cand['partido'][:8]:<8} {leitura.milhar(cand['vap']):>13} {cand['pvap']:>7}"
            f"  {barra(cand['pvap'], ranking[0]['pvap'])} {leitura.situacao(cand)}".rstrip()
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


def resolver_cidade(args):
    """Troca --cidade por --municipio (e guarda o nome para o título), lendo a lista do TSE."""
    resposta = cliente.buscar(catalogo.url_municipios(args.ambiente, args.cargo, args.turno, args.eleicao))
    if resposta.dados is None:
        sys.exit(f"Não foi possível ler a lista de cidades do TSE (HTTP {resposta.status or 'sem resposta'}).")
    lista = leitura.municipios(resposta.dados, args.uf)
    if args.cidade:
        cidade, parecidas = leitura.achar_municipio(lista, args.cidade)
        if cidade is None:
            sugestoes = ", ".join(m["nome"] for m in parecidas[:10])
            sys.exit(
                f"Cidade '{args.cidade}' não encontrada em {args.uf.upper()}."
                + (f" Parecidas: {sugestoes}." if sugestoes else "")
            )
        args.municipio = cidade["codigo"]
    else:
        cidade = leitura.cidade_por_codigo(lista, args.municipio)
        if cidade is None:
            sys.exit(f"Código de município {args.municipio} não existe em {args.uf.upper()}.")
    args.cidade_nome = cidade["nome"]


def executar(args):
    if args.cidade or args.municipio:
        resolver_cidade(args)
    url = catalogo.montar_url(args.ambiente, args.cargo, args.uf, args.turno, args.eleicao, args.municipio)
    dados, etag, falhas = None, None, 0
    while True:
        resposta = cliente.buscar(url, etag)
        espera = args.intervalo
        aviso = ""
        if resposta.status == 200:
            dados, etag, falhas = resposta.dados, resposta.etag, 0
        elif resposta.status == 304:
            falhas = 0
        elif resposta.status == 404 and dados is None:
            sys.exit(f"Arquivo não encontrado: {url}\nConfira --cargo, --uf e --turno.")
        elif resposta.status in (403, 429):
            espera = cliente.ESPERA_BLOQUEIO
            aviso = f"TSE limitou o acesso (HTTP {resposta.status}). Nova tentativa em {espera}s."
        else:
            falhas += 1
            espera = min(args.intervalo * 2**falhas, cliente.ESPERA_MAXIMA_ERRO)
            aviso = f"Falha ao ler o TSE (HTTP {resposta.status}). Mostrando último dado. Nova tentativa em {espera}s."
        if dados is not None:
            mostrar(renderizar(dados, args, aviso), args.uma_vez)
        if args.uma_vez:
            return
        time.sleep(espera)


def ler_argumentos(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m contador", description="Contador de votos em tempo real (TSE, 2026).")
    parser.add_argument("-c", "--cargo", choices=catalogo.CARGOS, default="presidente")
    parser.add_argument("--uf", help="sigla da UF; 'br' (padrão) só para presidente")
    parser.add_argument("--cidade", help="nome da cidade (precisa de --uf); mostra só o resultado dela")
    parser.add_argument("--municipio", help="código TSE da cidade, 5 dígitos (alternativa a --cidade)")
    parser.add_argument("--turno", type=int, choices=(1, 2), default=1)
    parser.add_argument("--ambiente", choices=catalogo.AMBIENTES, default="oficial")
    parser.add_argument("--eleicao", type=int, help="código da eleição no TSE (sobrescreve o padrão)")
    parser.add_argument("--top", type=int, default=15, help="quantos candidatos mostrar")
    parser.add_argument("--intervalo", type=int, default=10, help="segundos entre consultas (mín. 10)")
    parser.add_argument("--uma-vez", action="store_true", help="consulta uma vez e sai")
    args = parser.parse_args(argv)
    args.uf = (args.uf or ("br" if args.cargo == "presidente" else "")).lower()
    if not catalogo.uf_valida(args.cargo, args.uf):
        parser.error(f"--uf inválida para {args.cargo}: use uma de {', '.join(catalogo.UFS)}")
    if args.intervalo < 10:
        parser.error("--intervalo mínimo é 10 segundos (limite de acesso do TSE)")
    if args.cidade and args.municipio:
        parser.error("use --cidade ou --municipio, não os dois")
    if (args.cidade or args.municipio) and args.uf == "br":
        parser.error("cidade precisa de uma UF: use --uf")
    if args.municipio and not (args.municipio.isdigit() and len(args.municipio) == 5):
        parser.error("--municipio deve ter 5 dígitos (código do TSE)")
    return args


def main():
    try:
        executar(ler_argumentos())
    except KeyboardInterrupt:
        print()
