#!/usr/bin/env python3
"""Gera os contornos das UFs para o mapa da página, a partir da malha do IBGE.

    python3 tools/gerar_mapa.py > mapa-ufs.js          # baixa a malha do IBGE
    python3 tools/gerar_mapa.py malha.geojson          # ou usa um arquivo já baixado
    python3 tools/gerar_mapa.py --municipios geo       # um arquivo por UF, com os municípios, na pasta geo/

Saída do primeiro modo: um objeto JavaScript `{uf: {d: caminho SVG, c: [x, y], l: largura}}` pronto para
colar em index.html (constante MAPA_UFS), mais a linha com o tamanho do desenho. O modo `--municipios`
grava `geo/<uf>.json` com `{"w": largura, "h": altura, "m": {código IBGE do município: caminho SVG}}`, que o
servidor entrega em /geo/<uf>.json para o mapa por município. Só biblioteca padrão. Roda uma vez por
eleição; o servidor nunca acessa o IBGE.
"""
import gzip
import json
import math
import os
import sys
import urllib.request

URL = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&qualidade=minima&intrarregiao=UF"
URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo}?formato=application/vnd.geo%2Bjson&qualidade=minima&intrarregiao=municipio"
SIGLAS = {
    "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma", "22": "pi",
    "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba", "31": "mg", "32": "es",
    "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms", "51": "mt", "52": "go", "53": "df",
}
LARGURA = 1000     # unidades do desenho na horizontal
TOLERANCIA = 1.0   # simplificação (unidades do desenho); quanto maior, menor o arquivo
AREA_MINIMA = 12   # ilhas menores que isso (unidades²) somem
TOLERANCIA_MUNICIPIOS = 0.7  # os municípios são pequenos: simplifica menos


def aneis(geometria):
    poligonos = geometria["coordinates"] if geometria["type"] == "MultiPolygon" else [geometria["coordinates"]]
    return [poligono[0] for poligono in poligonos]  # só o anel externo: a malha não tem buracos úteis


def distancia(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def douglas_peucker(pontos, tolerancia):
    if len(pontos) < 3:
        return pontos
    maior, indice = 0, 0
    for i in range(1, len(pontos) - 1):
        d = distancia(pontos[i], pontos[0], pontos[-1])
        if d > maior:
            maior, indice = d, i
    if maior <= tolerancia:
        return [pontos[0], pontos[-1]]
    return douglas_peucker(pontos[: indice + 1], tolerancia)[:-1] + douglas_peucker(pontos[indice:], tolerancia)


def simplificar_anel(anel, tolerancia):
    anel = anel[:-1] if anel[0] == anel[-1] else anel
    meio = max(range(len(anel)), key=lambda i: distancia(anel[i], anel[0], anel[0]))
    primeira = douglas_peucker(anel[: meio + 1], tolerancia)
    segunda = douglas_peucker(anel[meio:] + [anel[0]], tolerancia)
    return primeira[:-1] + segunda[:-1]


def area_e_centro(anel):
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1]):
        cruz = x1 * y2 - x2 * y1
        area += cruz
        cx += (x1 + x2) * cruz
        cy += (y1 + y2) * cruz
    area /= 2
    return abs(area), (cx / (6 * area), cy / (6 * area)) if area else anel[0]


def caminho(anel):
    """Caminho SVG com deslocamentos relativos inteiros: bem menor que coordenadas absolutas."""
    pontos = [(round(x), round(y)) for x, y in anel]
    partes = [f"M{pontos[0][0]} {pontos[0][1]}l"]
    anterior = pontos[0]
    deltas = []
    for x, y in pontos[1:]:
        deltas.append(f"{x - anterior[0]} {y - anterior[1]}")
        anterior = (x, y)
    return partes[0] + " ".join(deltas).replace(" -", "-") + "z"


def converter(dados, chave_de, largura=LARGURA, tolerancia=TOLERANCIA, area_minima=AREA_MINIMA, latitude=None):
    """(largura, altura, {chave: {"d": caminho, "c": [x, y], "l": largura}}) de uma malha GeoJSON do IBGE.

    `latitude` é a latitude que dá a escala da longitude (padrão: o meio da malha)."""
    lons = [p[0] for f in dados["features"] for anel in aneis(f["geometry"]) for p in anel]
    lats = [p[1] for f in dados["features"] for anel in aneis(f["geometry"]) for p in anel]
    fator = math.cos(math.radians((min(lats) + max(lats)) / 2 if latitude is None else latitude))  # um grau de longitude vale menos que um de latitude
    escala = largura / ((max(lons) - min(lons)) * fator)
    projetar = lambda lon, lat: ((lon - min(lons)) * fator * escala, (max(lats) - lat) * escala)
    saida = {}
    for feicao in dados["features"]:
        d, maior = [], (0, None, None)
        for anel in aneis(feicao["geometry"]):
            projetado = [projetar(*p) for p in anel]
            simples = simplificar_anel(projetado, tolerancia)
            if len(simples) < 3 and area_minima == 0:  # município minúsculo: a simplificação o apagaria, fica como veio
                simples = projetado[:-1] if projetado[0] == projetado[-1] else projetado
            area, centro = area_e_centro(simples)
            if len(simples) < 3 or area < area_minima:
                continue
            d.append(caminho(simples))
            if area > maior[0]:
                xs = [x for x, _ in simples]
                maior = (area, centro, max(xs) - min(xs))
        if d:
            saida[chave_de(feicao)] = {"d": "".join(d), "c": [round(maior[1][0]), round(maior[1][1])], "l": round(maior[2])}
    return largura, round((max(lats) - min(lats)) * escala), saida


def baixar(url):
    with urllib.request.urlopen(url, timeout=120) as resposta:
        corpo = resposta.read()
    if corpo[:2] == b"\x1f\x8b":  # o IBGE às vezes manda gzip mesmo sem o cliente pedir
        corpo = gzip.decompress(corpo)
    return json.loads(corpo)


def gerar_municipios(pasta, baixar_malha=baixar):
    """Um arquivo `<uf>.json` por UF com o desenho dos municípios. Devolve {uf: tamanho do arquivo em bytes}."""
    os.makedirs(pasta, exist_ok=True)
    tamanhos = {}
    for codigo, sigla in sorted(SIGLAS.items(), key=lambda par: par[1]):
        largura, altura, formas = converter(
            baixar_malha(URL_MUNICIPIOS.format(codigo=codigo)), lambda f: f["properties"]["codarea"],
            tolerancia=TOLERANCIA_MUNICIPIOS, area_minima=0)
        conteudo = json.dumps({"w": largura, "h": altura, "m": {c: f["d"] for c, f in sorted(formas.items())}}, separators=(",", ":"))
        with open(os.path.join(pasta, f"{sigla}.json"), "w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
        tamanhos[sigla] = len(conteudo.encode("utf-8"))
    return tamanhos


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--municipios":
        pasta = sys.argv[2] if len(sys.argv) > 2 else "geo"
        tamanhos = gerar_municipios(pasta)
        print(f"{len(tamanhos)} arquivos em {pasta}/, {sum(tamanhos.values()) / 1024:.0f} KB no total", file=sys.stderr)
        return
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    else:
        dados = baixar(URL)
    largura, altura, saida = converter(dados, lambda f: SIGLAS[f["properties"]["codarea"]], latitude=-15)
    print(f"/* Contornos das UFs (malha do IBGE, simplificada por tools/gerar_mapa.py). Desenho {largura}x{altura}. */")
    print(f"const MAPA_TAMANHO = [{largura}, {altura}];")
    print("const MAPA_UFS = {")
    for sigla in sorted(saida):
        print(f"  {sigla}: {json.dumps(saida[sigla], separators=(',', ':'))},")
    print("};")


if __name__ == "__main__":
    main()
