"""Tabelas de rotas. Um recurso novo escreve a sua função num arquivo desta pasta e registra o caminho aqui."""
from contador.servidor.estaticos import service_worker
from contador.servidor.rotas.anuncio import faixa_de_anuncio
from contador.servidor.rotas.busca import busca_rapida
from contador.servidor.rotas.compartilhamento import cartao_do_placar, icone, manifesto, pagina_inicial
from contador.servidor.rotas.deputados import camara_dos_deputados, mais_votados
from contador.servidor.rotas.exterior import mundo
from contador.servidor.rotas.historico import atualizacoes_da_selecao, historico_da_selecao
from contador.servidor.rotas.mapa import disputas_apertadas, mapa_historico, mapa_por_uf, regioes_do_pais, senado_em_disputa
from contador.servidor.rotas.municipios import mapa_municipal, municipios_da_uf
from contador.servidor.rotas.placar import resultado

# Rotas JSON: caminho -> função(consulta) que devolve (status HTTP, corpo).
ROTAS_API = {
    "/api/resultado": resultado,
    "/api/municipios": municipios_da_uf,
    "/api/historico": historico_da_selecao,
    "/api/atualizacoes": atualizacoes_da_selecao,
    "/api/anuncio": faixa_de_anuncio,
    "/api/mapa": mapa_por_uf,
    "/api/mapa-historico": mapa_historico,
    "/api/regioes": regioes_do_pais,
    "/api/disputas": disputas_apertadas,
    "/api/camara": camara_dos_deputados,
    "/api/maisvotados": mais_votados,
    "/api/senado": senado_em_disputa,
    "/api/mapa-municipal": mapa_municipal,
    "/api/mundo": mundo,
    "/api/busca": busca_rapida,
}

# Rotas que não são JSON: caminho -> função(consulta, cabeçalhos) que devolve (status, tipo, corpo, cabeçalhos extras).
ROTAS_ARQUIVO = {
    "/": pagina_inicial,
    "/og.png": cartao_do_placar,
    "/icone-192.png": icone(192),
    "/icone-512.png": icone(512),
    "/icone-512-mascara.png": icone(512, mascara=True),
    "/manifest.webmanifest": manifesto,
    "/sw.js": service_worker,
}
