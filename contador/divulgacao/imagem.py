"""Imagens PNG sem dependências: prévia de compartilhamento (Open Graph) e ícones do app.

Só `zlib` e `struct`. A `Tela` guarda pixels RGB e sabe desenhar retângulos, linhas grossas e texto
em uma fonte de pixels 5x7 (maiúsculas, números e pontuação; acentos do português vêm de
marcas desenhadas por cima da letra). O texto sai sempre em maiúsculas.
"""
import struct
import unicodedata
import zlib


LARGURA_OG, ALTURA_OG = 1200, 630

# Cada letra: 7 linhas de 5 colunas ('#' = pixel aceso).
FONTE = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    ";": [".....", ".##..", ".##..", ".....", ".##..", "..#..", ".#..."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "%": ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    "(": ["...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."],
    ")": [".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."],
    "·": [".....", ".....", ".....", "..#..", ".....", ".....", "....."],
    "º": [".##..", "#..#.", "#..#.", ".##..", ".....", ".....", "....."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    "'": ["..#..", "..#..", ".#...", ".....", ".....", ".....", "....."],
}
# Acentos desenhados acima da letra (2 linhas) ou abaixo (cedilha).
ACENTOS = {
    "́": (["...#.", "..#.."], "cima"),          # agudo
    "̀": ([".#...", "..#.."], "cima"),          # grave
    "̂": (["..#..", ".#.#."], "cima"),          # circunflexo
    "̃": ([".##.#", "#..#."], "cima"),          # til
    "̈": (["#...#", "....."], "cima"),          # trema (aproximado)
    "̧": (["..#..", ".#..."], "baixo"),         # cedilha
}
ALTURA_GLIFO, LARGURA_GLIFO, ESPACO_ENTRE = 7, 5, 1


def hex_rgb(cor):
    """'#rrggbb' -> (r, g, b)."""
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def glifos(texto):
    """[(letra, [marcas])] do texto em maiúsculas; o que a fonte não tem vira '?'."""
    saida = []
    for caractere in unicodedata.normalize("NFD", texto.upper()):
        if unicodedata.combining(caractere):
            if saida and caractere in ACENTOS:
                saida[-1][1].append(caractere)
            continue
        saida.append((caractere if caractere in FONTE else "?", []))
    return saida


def largura_do_texto(texto, escala):
    n = len(glifos(texto))
    return max(0, n * (LARGURA_GLIFO + ESPACO_ENTRE) - ESPACO_ENTRE) * escala


def altura_do_texto(escala):
    return ALTURA_GLIFO * escala


def texto_que_cabe(texto, largura_maxima, escalas=(6, 5, 4, 3, 2)):
    """(escala, texto): a maior escala em que cabe; se nem a menor serve, corta com reticências."""
    for escala in escalas:
        if largura_do_texto(texto, escala) <= largura_maxima:
            return escala, texto
    escala = escalas[-1]
    while texto and largura_do_texto(texto + "...", escala) > largura_maxima:
        texto = texto[:-1]
    return escala, texto.rstrip() + "..."


class Tela:
    def __init__(self, largura, altura, fundo=(0, 0, 0)):
        self.largura, self.altura = largura, altura
        self.pixels = bytearray(bytes(fundo) * (largura * altura))

    def retangulo(self, x, y, largura, altura, cor):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(self.largura, int(x + largura)), min(self.altura, int(y + altura))
        if x1 <= x0 or y1 <= y0:
            return
        faixa = bytes(cor) * (x1 - x0)
        for linha in range(y0, y1):
            inicio = (linha * self.largura + x0) * 3
            self.pixels[inicio:inicio + len(faixa)] = faixa

    def retangulo_arredondado(self, x, y, largura, altura, raio, cor):
        """Retângulo com cantos redondos (sem suavização: serve para ícones e barras)."""
        raio = int(min(raio, largura / 2, altura / 2))
        for linha in range(int(altura)):
            recuo = 0
            if linha < raio:
                recuo = raio - int((raio * raio - (raio - linha - 0.5) ** 2) ** 0.5 + 0.5)
            elif linha >= altura - raio:
                dentro = linha - (altura - raio)
                recuo = raio - int((raio * raio - (dentro + 0.5) ** 2) ** 0.5 + 0.5)
            self.retangulo(x + recuo, y + linha, largura - 2 * recuo, 1, cor)

    def linha_grossa(self, x1, y1, x2, y2, espessura, cor):
        """Segmento com pontas quadradas, feito de pequenos quadrados ao longo do traço."""
        passos = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
        meia = espessura / 2
        for i in range(passos + 1):
            t = i / passos
            self.retangulo(x1 + (x2 - x1) * t - meia, y1 + (y2 - y1) * t - meia, espessura, espessura, cor)

    def texto(self, x, y, texto, cor, escala=1, alinhamento="esquerda"):
        """Desenha o texto com o canto superior esquerdo em (x, y). Devolve a largura usada."""
        largura = largura_do_texto(texto, escala)
        if alinhamento == "direita":
            x -= largura
        elif alinhamento == "centro":
            x -= largura // 2
        cursor = x
        for letra, marcas in glifos(texto):
            for linha, padrao in enumerate(FONTE[letra]):
                for coluna, ponto in enumerate(padrao):
                    if ponto == "#":
                        self.retangulo(cursor + coluna * escala, y + linha * escala, escala, escala, cor)
            for marca in marcas:
                padrao, lugar = ACENTOS[marca]
                topo = y - 2 * escala if lugar == "cima" else y + ALTURA_GLIFO * escala
                for linha, texto_da_linha in enumerate(padrao):
                    for coluna, ponto in enumerate(texto_da_linha):
                        if ponto == "#":
                            self.retangulo(cursor + coluna * escala, topo + linha * escala, escala, escala, cor)
            cursor += (LARGURA_GLIFO + ESPACO_ENTRE) * escala
        return largura

    def png(self):
        brutas = b"".join(
            b"\x00" + bytes(self.pixels[linha * self.largura * 3:(linha + 1) * self.largura * 3])
            for linha in range(self.altura)
        )
        return b"".join((
            b"\x89PNG\r\n\x1a\n",
            _bloco(b"IHDR", struct.pack(">IIBBBBB", self.largura, self.altura, 8, 2, 0, 0, 0)),
            _bloco(b"IDAT", zlib.compress(brutas, 6)),
            _bloco(b"IEND", b""),
        ))


def _bloco(tipo, dados):
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)


def icone(lado, mascara=False):
    """Ícone do app: quadrado azul com o visto branco. `mascara` deixa margem para ícones adaptativos."""
    azul, branco = hex_rgb("#2a78d6"), (255, 255, 255)
    tela = Tela(lado, lado, azul if mascara else (13, 13, 13))
    if not mascara:
        tela.retangulo_arredondado(0, 0, lado, lado, lado * 0.22, azul)
    margem = lado * (0.22 if mascara else 0.0)
    area = lado - 2 * margem
    ponto = lambda fx, fy: (margem + fx * area, margem + fy * area)
    espessura = max(2, area * 0.11)
    tela.linha_grossa(*ponto(0.27, 0.53), *ponto(0.44, 0.70), espessura, branco)
    tela.linha_grossa(*ponto(0.44, 0.70), *ponto(0.74, 0.32), espessura, branco)
    return tela.png()
