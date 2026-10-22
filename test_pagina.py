"""Conferências estáticas da página (index.html) e do gerador de contornos do mapa."""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import contador
from tools import gerar_mapa

HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def script():
    return re.search(r"<script>(.*?)</script>", HTML, re.S).group(1)


def chaves_do_objeto(nome):
    """Chaves (siglas) do objeto JavaScript `const nome = { sp: ..., rj: ... }`, no nível de cima."""
    corpo = re.search(rf"const {nome} = \{{(.*?)\n\}};", script(), re.S).group(1)
    return re.findall(r'\b([a-z]{2}): [{"]', corpo)


class Pagina(unittest.TestCase):
    def test_todas_as_ufs_tem_nome_e_contorno(self):
        self.assertEqual(sorted(chaves_do_objeto("UFS")), sorted(contador.UFS))
        self.assertEqual(sorted(chaves_do_objeto("MAPA_UFS")), sorted(contador.UFS))

    def test_contornos_sao_caminhos_fechados(self):
        for sigla, d in re.findall(r'(?:^|\n)\s*([a-z]{2}): \{"d":"([^"]+)"', script()):
            with self.subTest(uf=sigla):
                self.assertTrue(d.startswith("M") and d.endswith("z"))
                self.assertRegex(d, r"^[Mlz0-9 .\-]+$")

    def test_sem_dependencia_externa(self):
        self.assertNotRegex(HTML, r"<script[^>]+src=")
        self.assertNotRegex(HTML, r'<link[^>]+rel="stylesheet"')
        self.assertNotIn("@import", HTML)
        self.assertNotRegex(HTML, r"url\(\s*['\"]?https?:")
        self.assertNotRegex(HTML, r"\b(?:src|action)=[\"']https?:")

    def test_ids_usados_pelo_script_existem_na_pagina(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        usados = set(re.findall(r'\$\("([a-z0-9-]+)"\)', script()))
        self.assertEqual(sorted(usados - ids), [])

    def test_sintaxe_do_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "pagina.js"
            arquivo.write_text(script(), encoding="utf-8")
            resultado = subprocess.run([node, "--check", str(arquivo)], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


class GerarMapa(unittest.TestCase):
    def test_simplificar_tira_pontos_alinhados(self):
        reta = [(0, 0), (1, 0.01), (2, 0), (3, 0.01), (4, 0)]
        self.assertEqual(gerar_mapa.douglas_peucker(reta, 0.5), [(0, 0), (4, 0)])
        self.assertEqual(gerar_mapa.douglas_peucker(reta, 0.0001), reta)

    def test_caminho_usa_deslocamentos_inteiros(self):
        self.assertEqual(gerar_mapa.caminho([(10.2, 20.4), (13, 20), (13, 25)]), "M10 20l3 0 0 5z")
        self.assertEqual(gerar_mapa.caminho([(5, 5), (3, 7), (6, 4)]), "M5 5l-2 2 3-3z")

    def test_area_e_centro_de_um_quadrado(self):
        area, centro = gerar_mapa.area_e_centro([(0, 0), (10, 0), (10, 10), (0, 10)])
        self.assertEqual((area, centro), (100, (5, 5)))

    def test_gera_o_objeto_a_partir_de_uma_malha(self):
        def quadrado(x, y, lado=20):
            return [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]

        malha = {"features": [
            {"properties": {"codarea": "35"}, "geometry": {"type": "Polygon", "coordinates": [quadrado(-50, -25)]}},
            {"properties": {"codarea": "33"}, "geometry": {"type": "MultiPolygon", "coordinates": [[quadrado(-30, -20)], [quadrado(-60, -10, 0.001)]]}},
        ]}
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "malha.json"
            arquivo.write_text(json.dumps(malha), encoding="utf-8")
            saida = io.StringIO()
            with mock.patch.object(sys, "argv", ["gerar_mapa.py", str(arquivo)]), redirect_stdout(saida):
                gerar_mapa.main()
        texto = saida.getvalue()
        self.assertIn("const MAPA_TAMANHO = [1000,", texto)
        self.assertRegex(texto, r'\n  sp: \{"d":"M[^"]+z","c":\[\d+,\d+\],"l":\d+\},')
        self.assertRegex(texto, r'\n  rj: \{"d":"M[^"]+z","c"')
        self.assertEqual(texto.count('"d":"M'), 2)  # a ilha minúscula do RJ some


if __name__ == "__main__":
    unittest.main()
