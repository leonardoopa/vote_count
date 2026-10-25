"""Testes de `contador/servidor/estaticos.py`."""
import http.client
import json
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from contador.servidor import estaticos
from contador.servidor.handler import Handler
from contador.tse import catalogo


class Desenhos(unittest.TestCase):
    def test_todas_as_ufs_tem_desenho_e_ele_bate_com_o_codigo_do_tse(self):
        for uf in catalogo.UFS:
            status, tipo, corpo, extras = estaticos.desenho_dos_municipios(f"/geo/{uf}.json")
            self.assertEqual((status, tipo, extras["Cache-Control"]), (200, "application/json; charset=utf-8", "no-cache"))
            self.assertTrue(extras["ETag"].startswith('W/"'))
            desenho = json.loads(corpo)
            self.assertEqual(set(desenho), {"w", "h", "m", "n"})
            self.assertEqual(set(desenho["n"]), set(desenho["m"]))                     # todo município desenhado tem nome
            self.assertTrue(all(isinstance(nome, str) and nome for nome in desenho["n"].values()))
            self.assertTrue(all(d.startswith("M") and d.endswith("z") for d in desenho["m"].values()))
            self.assertTrue(all(len(c) == 7 and c.isdigit() for c in desenho["m"]))  # código IBGE do município

    def test_o_desenho_do_brasil_tem_todos_os_municipios_nas_coordenadas_dos_estados(self):
        status, tipo, corpo, extras = estaticos.desenho_dos_municipios("/geo/brasil.json")
        self.assertEqual((status, tipo), (200, "application/json; charset=utf-8"))
        desenho = json.loads(corpo)
        self.assertEqual(set(desenho), {"w", "h", "m", "c", "n"})
        self.assertGreater(len(desenho["m"]), 5500)
        self.assertEqual(set(desenho["c"]), set(desenho["m"]))
        self.assertEqual(set(desenho["n"]), set(desenho["m"]))
        # o canvas da página desenha esta camada em escala MAPA_TAMANHO[0] / w sobre os contornos dos estados (hoje 1: as mesmas coordenadas)
        mapa_ufs = (estaticos.WEB / "js" / "contornos-ufs.js").read_text(encoding="utf-8")
        largura, altura = (int(n) for n in re.search(r"MAPA_TAMANHO = \[(\d+), (\d+)\]", mapa_ufs).groups())
        self.assertEqual((desenho["w"] / largura, desenho["h"] / altura), (1, 1))

    def test_o_desenho_cobre_os_municipios_do_tse_menos_os_muito_novos(self):
        # em 2026 o desenho do IBGE ainda não traz 1 município de MT; os demais têm todos o seu contorno
        for uf in ("sp", "ac", "df", "rj"):
            desenho = json.loads(estaticos.desenho_dos_municipios(f"/geo/{uf}.json")[2])["m"]
            self.assertGreater(len(desenho), 0)

    def test_caminhos_que_nao_sao_desenho(self):
        for caminho in ("/geo/xx.json", "/geo/sp.txt", "/geo/", "/geo/../app.py", "/geo/sp.json/x", "/outra/sp.json", "/geo/SP.json"):
            with self.subTest(caminho=caminho):
                self.assertIsNone(estaticos.desenho_dos_municipios(caminho))

    def test_desenho_que_falta_da_404(self):
        with mock.patch.object(estaticos, "GEO", Path("/nao/existe")):
            self.assertEqual(estaticos.desenho_dos_municipios("/geo/sp.json")[0], 404)


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def pedir(self, caminho):
        conexao = http.client.HTTPConnection("127.0.0.1", self.http.server_address[1], timeout=10)
        conexao.request("GET", caminho)
        resposta = conexao.getresponse()
        corpo = resposta.read()
        conexao.close()
        return resposta, corpo

    def test_desenho_pelo_http(self):
        resposta, corpo = self.pedir("/geo/sp.json")
        self.assertEqual((resposta.status, resposta.getheader("Cache-Control")), (200, "no-cache"))
        self.assertGreater(len(json.loads(corpo)["m"]), 600)
        self.assertEqual(self.pedir("/geo/zz.json")[0].status, 404)
        self.assertEqual(self.pedir("/geo/..%2Fapp.py")[0].status, 404)


class IconeDoAnuncio(unittest.TestCase):
    def test_serve_o_icone_com_tipo_de_imagem(self):
        status, tipo, corpo, _ = estaticos.arquivo_da_web("/anuncios/outlets-import.jpg")
        self.assertEqual((status, tipo), (200, "image/jpeg"))
        self.assertTrue(corpo.startswith(b"\xff\xd8"))

    def test_icone_que_nao_existe_e_404(self):
        self.assertEqual(estaticos.arquivo_da_web("/anuncios/nao-existe.png")[0], 404)

    def test_so_nomes_simples_de_imagem(self):
        for caminho in ("/anuncios/../sw.js", "/anuncios/a.svg", "/anuncios/A.png", "/anuncios/", "/anuncios/a.jpg/x"):
            with self.subTest(caminho=caminho):
                self.assertIsNone(estaticos.arquivo_da_web(caminho))
