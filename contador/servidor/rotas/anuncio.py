"""Rotas do anúncio: a faixa do topo (/api/anuncio), a passagem que conta o clique (/ir/anuncio) e os números (/api/acessos)."""
import hmac

from contador.servidor import estado


def faixa_de_anuncio(consulta):
    return 200, estado.ANUNCIO


def ir_para_o_anuncio(consulta, cabecalhos=None):
    """Conta o clique e manda para o link do anúncio. Sem link configurado não há para onde ir."""
    link = estado.ANUNCIO.get("link")
    if not link:
        return 404, "text/plain; charset=utf-8", b"anuncio sem link", {}
    estado.ACESSOS.clique()
    return 302, "text/plain; charset=utf-8", b"", {"Location": link, "Referrer-Policy": "no-referrer"}


def numeros_de_acesso(consulta):
    """Os números de acesso, só com ?chave= igual a ACESSOS_CHAVE. Sem a variável, a rota não existe."""
    chave = consulta.get("chave", [""])[0]
    if not estado.ACESSOS_CHAVE or not hmac.compare_digest(chave.encode(), estado.ACESSOS_CHAVE.encode()):
        return 404, {"erro": "nao encontrado"}
    return 200, estado.ACESSOS.resumo()
