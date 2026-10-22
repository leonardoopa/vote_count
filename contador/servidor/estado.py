"""Estado compartilhado do processo: o cache do TSE, o histórico, o varredor e a faixa de anúncio.

As rotas leem estes objetos como `estado.CACHE` (e não com `from ... import`) porque os testes trocam o cache.
"""
import os

from contador import varredor
from contador.divulgacao import anuncio
from contador.recursos import historico
from contador.tse.cache import Cache

CACHE = Cache()

# Um ponto do placar a cada totalização nova, por seleção. `resultado()` registra o que já tem no
# cache; as rotas do histórico só leem o que foi guardado, então nunca consultam o TSE.
HISTORICO = historico.do_ambiente()

# Faixa de publicidade do topo: configurada por variáveis de ambiente e lida só na partida.
ANUNCIO = anuncio.do_ambiente()

# Recursos que precisam de dezenas de arquivos do TSE (os deputados de cada UF) são servidos pelo varredor:
# uma thread, poucas buscas por segundo no total, só enquanto alguém olha. 0 desliga esses recursos.
BUSCAS_EXTRAS_POR_SEGUNDO = float(os.environ.get("BUSCAS_EXTRAS_POR_SEGUNDO", "2") or 0)
VARREDOR = varredor.Varredor(BUSCAS_EXTRAS_POR_SEGUNDO)
