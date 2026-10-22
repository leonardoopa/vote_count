"""Prévia de compartilhamento: meta tags Open Graph por seleção e a imagem do placar (PNG).

Quem monta o link (`?cargo=governador&uf=sp&turno=1`) não executa JavaScript: WhatsApp, X e
outros leem as meta tags do HTML e baixam `/og.png`. Este módulo só monta texto e imagem a partir
do que o servidor já tem; nunca consulta o TSE (veja `servidor.py`).
"""
import html
import re
import unicodedata

import imagem

NOME_DO_SITE = "Contador de votos 2026"
DESCRICAO_PADRAO = "Acompanhe a apuração das Eleições 2026 em tempo real, com dados oficiais do TSE."
CARGOS = {
    "presidente": "Presidente", "governador": "Governador", "senador": "Senador",
    "deputado-federal": "Deputado federal", "deputado-estadual": "Deputado estadual", "deputado-distrital": "Deputado distrital",
}
UFS = {
    "ac": "Acre", "al": "Alagoas", "am": "Amazonas", "ap": "Amapá", "ba": "Bahia", "ce": "Ceará", "df": "Distrito Federal",
    "es": "Espírito Santo", "go": "Goiás", "ma": "Maranhão", "mg": "Minas Gerais", "ms": "Mato Grosso do Sul",
    "mt": "Mato Grosso", "pa": "Pará", "pb": "Paraíba", "pe": "Pernambuco", "pi": "Piauí", "pr": "Paraná",
    "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte", "ro": "Rondônia", "rr": "Roraima", "rs": "Rio Grande do Sul",
    "sc": "Santa Catarina", "se": "Sergipe", "sp": "São Paulo", "to": "Tocantins",
}
# Mesma tabela da página (COR_PARTIDO em index.html): a cor segue o partido, nunca a posição na lista.
COR_PARTIDO = {
    "PT": "vermelho", "PL": "azul", "REPUBLICANOS": "laranja", "PSD": "agua",
    "PSB": "amarelo", "PP": "magenta", "MDB": "verde", "UNIAO": "violeta",
}
CORES = {  # tons do tema escuro da página
    "vermelho": "#e66767", "azul": "#3987e5", "laranja": "#d95926", "agua": "#199e70", "amarelo": "#c98500",
    "magenta": "#d55181", "verde": "#0ca30c", "violeta": "#9085e9", "outros": "#898781",
}
HOST_VALIDO = re.compile(r"^[A-Za-z0-9.-]{1,253}(:\d{1,5})?$")
MAX_CANDIDATOS_NA_IMAGEM = 4


def cor_do_partido(partido):
    base = unicodedata.normalize("NFD", partido or "")
    chave = re.sub(r"[^A-Z0-9]", "", "".join(c for c in base if not unicodedata.combining(c)).upper())
    return imagem.hex_rgb(CORES[COR_PARTIDO.get(chave, "outros")])


def titulo_da_selecao(cargo, uf, turno, cidade=None):
    """'Governador · Campinas (SP) · 2º turno'."""
    lugar = "Brasil" if uf == "br" else f"{cidade} ({uf.upper()})" if cidade else UFS.get(uf, uf.upper())
    return f"{CARGOS.get(cargo, cargo)} · {lugar} · {turno}º turno"


def numero_br(valor):
    return f"{valor:.2f}".replace(".", ",")


def descricao_do_placar(resumo):
    """'ANA LIMA 37,58% · BRUNO CASTRO 31,82% · 50,00% das seções apuradas', ou o texto padrão sem dados."""
    if not resumo or not resumo["votos"]["total"]:
        return DESCRICAO_PADRAO
    topo = " · ".join(f"{c['nome']} {numero_br(c['percentual'])}%" for c in resumo["candidatos"][:3])
    estado = "apuração final" if resumo["final"] else f"{numero_br(resumo['secoes']['percentual'])}% das seções apuradas"
    return f"{topo} · {estado}"


def base_publica(url_publica, cabecalhos):
    """Endereço do site para as URLs absolutas (og:image exige): variável URL_PUBLICA ou o Host da requisição."""
    if url_publica:
        return url_publica.rstrip("/")
    host = (cabecalhos.get("Host") or "").strip()
    if not HOST_VALIDO.match(host):
        return ""
    esquema = (cabecalhos.get("X-Forwarded-Proto") or "http").strip().lower()
    return f"{esquema if esquema in ('http', 'https') else 'http'}://{host}"


def meta_tags(base, consulta, titulo=None, descricao=DESCRICAO_PADRAO):
    """Bloco do <head>: Open Graph, cartão do X, manifesto e ícones. `consulta` é a query já validada ('a=1&b=2')."""
    consulta = f"?{consulta}" if consulta else ""
    pagina_titulo = f"{titulo} · {NOME_DO_SITE}" if titulo else NOME_DO_SITE
    linhas = [
        ('property', 'og:type', 'website'),
        ('property', 'og:site_name', NOME_DO_SITE),
        ('property', 'og:locale', 'pt_BR'),
        ('property', 'og:title', pagina_titulo),
        ('property', 'og:description', descricao),
        ('name', 'twitter:card', 'summary_large_image'),
        ('name', 'twitter:title', pagina_titulo),
        ('name', 'twitter:description', descricao),
        ('name', 'theme-color', '#0d0d0d'),
        ('name', 'apple-mobile-web-app-capable', 'yes'),
    ]
    if base:
        linhas += [
            ('property', 'og:url', f"{base}/{consulta}"),
            ('property', 'og:image', f"{base}/og.png{consulta}"),
            ('property', 'og:image:type', 'image/png'),
            ('property', 'og:image:width', str(imagem.LARGURA_OG)),
            ('property', 'og:image:height', str(imagem.ALTURA_OG)),
            ('property', 'og:image:alt', f"Placar: {pagina_titulo}"),
            ('name', 'twitter:image', f"{base}/og.png{consulta}"),
        ]
    saida = [f'<meta {atributo}="{html.escape(nome)}" content="{html.escape(valor)}">' for atributo, nome, valor in linhas]
    saida += [
        '<link rel="manifest" href="/manifest.webmanifest">',
        '<link rel="apple-touch-icon" href="/icone-192.png">',
        '<link rel="icon" type="image/png" sizes="192x192" href="/icone-192.png">',
    ]
    return "\n".join(saida)


def cartao(titulo, resumo=None, ambiente="oficial"):
    """PNG 1200x630 do placar. `resumo` é o que `servidor.resumir` devolve; sem ele a imagem só traz o título."""
    fundo, branco, claro, apagado, trilho = (13, 13, 13), (255, 255, 255), (195, 194, 183), (137, 135, 129), (44, 44, 42)
    margem, largura = 56, imagem.LARGURA_OG - 112
    tela = imagem.Tela(imagem.LARGURA_OG, imagem.ALTURA_OG, fundo)
    tela.retangulo(0, 0, imagem.LARGURA_OG, 10, imagem.hex_rgb("#2a78d6"))
    tela.texto(margem, 44, NOME_DO_SITE, apagado, 3)
    if ambiente == "simulado":
        tela.texto(margem + largura, 44, "DADOS SIMULADOS (TESTE)", imagem.hex_rgb("#c98500"), 3, "direita")
    escala, texto = imagem.texto_que_cabe(titulo, largura)
    tela.texto(margem, 100, texto, branco, escala)
    if resumo and resumo["votos"]["total"]:
        situacao = "APURAÇÃO FINAL" if resumo["final"] else f"APURAÇÃO PARCIAL · {numero_br(resumo['secoes']['percentual'])}% DAS SEÇÕES"
    else:
        situacao = "A APURAÇÃO AINDA NÃO COMEÇOU"
    tela.texto(margem, 100 + imagem.altura_do_texto(escala) + 34, situacao, claro, 3)
    candidatos = resumo["candidatos"][:MAX_CANDIDATOS_NA_IMAGEM] if resumo and resumo["votos"]["total"] else []
    topo, passo = 252, 80
    lider = max((c["percentual"] for c in candidatos), default=0) or 1
    for i, c in enumerate(candidatos):
        y = topo + i * passo
        selo = " · ELEITO" if c["eleito"] else " · 2º TURNO" if c["situacao"].lower().startswith("2") else ""
        percentual = f"{numero_br(c['percentual'])}%"
        espaco = largura - imagem.largura_do_texto(percentual, 5) - 24
        escala_nome, nome = imagem.texto_que_cabe(f"{c['nome']} ({c['partido']}){selo}", espaco, (4, 3, 2))
        tela.texto(margem, y, nome, branco, escala_nome)
        tela.texto(margem + largura, y - 4, percentual, branco, 5, "direita")
        tela.retangulo(margem, y + 40, largura, 16, trilho)
        tela.retangulo(margem, y + 40, max(4, largura * c["percentual"] / lider), 16, cor_do_partido(c["partido"]))
    rodape = "RESULTADOS.TSE.JUS.BR · SÓ A DIVULGAÇÃO OFICIAL DO TSE TEM VALOR LEGAL"
    if resumo and resumo.get("ultima_totalizacao"):
        rodape = f"ÚLTIMA TOTALIZAÇÃO: {resumo['ultima_totalizacao']} · " + "RESULTADOS.TSE.JUS.BR"
    tela.texto(margem, 580, rodape, apagado, 2)
    return tela.png()
