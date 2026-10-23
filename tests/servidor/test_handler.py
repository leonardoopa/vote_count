"""Testes de `contador/servidor/handler.py`: o que o HTTP faz com o corpo da rota."""
import gzip
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from contador.servidor import rotas
from contador.servidor.handler import GZIP_MINIMO, Handler


class RespostaJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.http.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def pedir(self, corpo, aceita_gzip):
        cabecalhos = {"Accept-Encoding": "gzip"} if aceita_gzip else {}
        with mock.patch.dict(rotas.ROTAS_API, {"/api/teste": lambda consulta: (200, corpo)}):
            with urllib.request.urlopen(urllib.request.Request(self.base + "/api/teste", headers=cabecalhos), timeout=5) as resposta:
                return resposta.headers, resposta.read()

    def test_resposta_grande_sai_comprimida_para_quem_aceita(self):
        corpo = {"lista": ["município"] * 2000}
        cabecalhos, dados = self.pedir(corpo, True)
        self.assertEqual(cabecalhos["Content-Encoding"], "gzip")
        self.assertEqual(cabecalhos["Vary"], "Accept-Encoding")
        self.assertEqual(json.loads(gzip.decompress(dados)), corpo)
        self.assertLess(len(dados), len(json.dumps(corpo)) // 5)

    def test_sem_aceitar_gzip_ou_pequena_sai_como_esta(self):
        grande, pequena = {"lista": ["município"] * 2000}, {"ok": True}
        for corpo, aceita in ((grande, False), (pequena, True)):
            with self.subTest(grande=corpo is grande, aceita=aceita):
                cabecalhos, dados = self.pedir(corpo, aceita)
                self.assertIsNone(cabecalhos["Content-Encoding"])
                self.assertEqual(json.loads(dados), corpo)
        self.assertGreater(len(json.dumps(grande)), GZIP_MINIMO)
