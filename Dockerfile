FROM python:3.12-slim

LABEL org.opencontainers.image.title="Contador de votos 2026" \
      org.opencontainers.image.description="Placar em tempo real da totalização do TSE" \
      org.opencontainers.image.source="https://github.com/leonardoopa/vote_count"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN useradd --create-home --uid 10001 app
# Histórico da apuração. O volume nomeado do compose herda este dono na primeira vez que é montado,
# então o usuário `app` consegue gravar mesmo com `read_only: true`.
RUN mkdir /dados && chown app /dados
ENV HISTORICO_DIR=/dados
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY contador.py servidor.py anuncio.py compartilhar.py deputados.py exterior.py historico.py imagem.py mapa.py municipios.py varredura.py ./
COPY web ./web
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=3)"

CMD ["python", "servidor.py", "--host", "0.0.0.0", "--porta", "8000"]
