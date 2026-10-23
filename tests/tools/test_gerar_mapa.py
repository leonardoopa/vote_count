"""Testes de `tools/gerar_mapa.py`."""
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools import gerar_mapa


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

    def test_municipios_do_brasil_caem_nas_coordenadas_dos_contornos_das_estados(self):
        def quadrado(x, y, lado):
            return [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]

        ufs = {"features": [{"properties": {"codarea": "35"}, "geometry": {"type": "Polygon", "coordinates": [quadrado(-50, -25, 20)]}}]}
        municipios = {"features": [
            {"properties": {"codarea": "3550308"}, "geometry": {"type": "Polygon", "coordinates": [quadrado(-50, -25, 10)]}},
            {"properties": {"codarea": "3509502"}, "geometry": {"type": "Polygon", "coordinates": [quadrado(-40, -15, 10)]}},
        ]}

        def baixar_malha(url):
            return municipios if "intrarregiao=municipio" in url else ufs

        nomes = lambda url: [{"id": 3550308, "nome": "São Paulo"}, {"id": 3509502, "nome": "Campinas"}]
        with tempfile.TemporaryDirectory() as pasta:
            tamanho = gerar_mapa.gerar_brasil_municipios(pasta, baixar_malha, nomes)
            conteudo = json.loads((Path(pasta) / "brasil.json").read_text(encoding="utf-8"))
        self.assertGreater(tamanho, 50)
        self.assertEqual(set(conteudo), {"w", "h", "m", "c", "n"})
        self.assertEqual(set(conteudo["c"]), set(conteudo["m"]))   # o centro de cada município, para os picos da vantagem
        self.assertEqual(conteudo["w"], gerar_mapa.LARGURA_BRASIL_MUNICIPIOS)
        self.assertEqual(set(conteudo["m"]), {"3550308", "3509502"})
        self.assertEqual(conteudo["n"]["3509502"], "Campinas")
        # o enquadramento é o dos estados (20 graus de lado), não o dos municípios (que ocupam só 10 de cada um)
        self.assertEqual(conteudo["h"], round(conteudo["w"] / math.cos(math.radians(15))))
        self.assertTrue(conteudo["m"]["3550308"].startswith("M0 "))   # começa no canto esquerdo do estado

    def test_mundo_so_com_paises_de_codigo_iso_e_sem_antartida(self):
        def pais(iso, nome, x, y, lado, nome_en="x"):
            quadrado = [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]
            return {"properties": {"ISO_A2_EH": iso, "NAME_PT": nome, "NAME": nome_en}, "geometry": {"type": "Polygon", "coordinates": [quadrado]}}

        malha = {"features": [
            pais("BR", "Brasil", -60, -20, 25), pais("SG", "Singapura", 103.6, 1.2, 0.3),   # minúsculo: não pode sumir
            pais("AQ", "Antártida", -60, -80, 20), pais("-9", "Sem código", 0, 0, 5), pais("-99", "Sem código", 10, 10, 5),
            {"properties": {"ISO_A2_EH": "ID", "NAME_PT": "Indonésia"}, "geometry": {"type": "MultiPolygon", "coordinates": [
                [[[100, -5], [110, -5], [110, 5], [100, 5], [100, -5]]], [[[120, -1], [120.05, -1], [120.05, -0.95], [120, -0.95], [120, -1]]]]}},
        ]}
        largura, altura, formas, nomes = gerar_mapa.converter_mundo(malha)
        self.assertEqual(largura, gerar_mapa.LARGURA_MUNDO)
        self.assertEqual(sorted(formas), ["BR", "ID", "SG"])
        self.assertEqual(nomes, {"BR": "Brasil", "ID": "Indonésia", "SG": "Singapura"})
        self.assertTrue(all(d.startswith("M") and d.endswith("z") for d in formas.values()))
        self.assertEqual(formas["ID"].count("M"), 1)        # a ilhota some, a ilha grande fica
        self.assertGreater(altura, 0)

    def test_miller_afasta_menos_os_polos_que_mercator(self):
        x, y = gerar_mapa.miller(180, 0)
        self.assertAlmostEqual(x, 3.14159, places=4)
        self.assertEqual(round(y, 6), 0)
        self.assertLess(gerar_mapa.miller(0, 80)[1], 3.0)
        self.assertLess(gerar_mapa.miller(0, -30)[1], 0)
