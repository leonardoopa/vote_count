"""Servidor web: a página (web/) e a API JSON em cima dos arquivos do TSE.

    estado.py        cache do TSE, histórico, varredor e anúncio (um de cada por processo)
    validacao.py     só valores conhecidos chegam à URL do TSE
    respostas.py     peças que várias rotas usam (erro do TSE, cidades da UF, respostas prontas)
    rotas/           uma rota (ou poucas) por arquivo; rotas/__init__.py liga cada caminho à sua função
    estaticos.py     arquivos de web/ (estilo, scripts, service worker, desenhos dos mapas)
    handler.py       o HTTP: escolhe a rota e envia a resposta
    app.py           a linha de comando que sobe o servidor
"""
