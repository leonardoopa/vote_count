#!/usr/bin/env python3
"""Gera os contornos das UFs para o mapa da página, a partir da malha do IBGE.

    python3 tools/gerar_mapa.py > mapa-ufs.js          # baixa a malha do IBGE
    python3 tools/gerar_mapa.py malha.geojson          # ou usa um arquivo já baixado

Saída: um objeto JavaScript `{uf: {d: caminho SVG, c: [x, y], l: largura}}` pronto para colar em
index.html (constante MAPA_UFS), mais a linha com o tamanho do desenho. Só biblioteca padrão.
Roda uma vez por eleição; o servidor nunca acessa o IBGE.
"""
import json
import math
import sys
import urllib.request

URL = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&qualidade=minima&intrarregiao=UF"
SIGLAS = {
    "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma", "22": "pi",
    "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba", "31": "mg", "32": "es",
    "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms", "51": "mt", "52": "go", "53": "df",
}
LARGURA = 1000     # unidades do desenho na horizontal
TOLERANCIA = 1.0   # simplificação (unidades do desenho); quanto maior, menor o arquivo
AREA_MINIMA = 12   # ilhas menores que isso (unidades²) somem


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


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    else:
        with urllib.request.urlopen(URL, timeout=60) as resposta:
            dados = json.load(resposta)
    lons = [p[0] for f in dados["features"] for anel in aneis(f["geometry"]) for p in anel]
    lats = [p[1] for f in dados["features"] for anel in aneis(f["geometry"]) for p in anel]
    fator = math.cos(math.radians(-15))  # um grau de longitude vale menos que um de latitude
    escala = LARGURA / ((max(lons) - min(lons)) * fator)
    projetar = lambda lon, lat: ((lon - min(lons)) * fator * escala, (max(lats) - lat) * escala)
    altura = round((max(lats) - min(lats)) * escala)
    saida = {}
    for feicao in dados["features"]:
        sigla = SIGLAS[feicao["properties"]["codarea"]]
        d, maior = [], (0, None, None)
        for anel in aneis(feicao["geometry"]):
            simples = simplificar_anel([projetar(*p) for p in anel], TOLERANCIA)
            area, centro = area_e_centro(simples)
            if len(simples) < 3 or area < AREA_MINIMA:
                continue
            d.append(caminho(simples))
            if area > maior[0]:
                xs = [x for x, _ in simples]
                maior = (area, centro, max(xs) - min(xs))
        saida[sigla] = {"d": "".join(d), "c": [round(maior[1][0]), round(maior[1][1])], "l": round(maior[2])}
    print(f"/* Contornos das UFs (malha do IBGE, simplificada por tools/gerar_mapa.py). Desenho {LARGURA}x{altura}. */")
    print(f"const MAPA_TAMANHO = [{LARGURA}, {altura}];")
    print("const MAPA_UFS = {")
    for sigla in sorted(saida):
        print(f"  {sigla}: {json.dumps(saida[sigla], separators=(',', ':'))},")
    print("};")


if __name__ == "__main__":
    main()
