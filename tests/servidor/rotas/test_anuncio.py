"""Testes de `contador/servidor/rotas/anuncio.py`."""
import unittest
from unittest import mock

from contador.servidor import estado, rotas


class Rota(unittest.TestCase):
    def test_rota_devolve_a_configuracao(self):
        configurado = {"ativo": True, "texto": "Oferta", "rotulo": "Publicidade"}
        with mock.patch.object(estado, "ANUNCIO", configurado):
            self.assertEqual(rotas.ROTAS_API["/api/anuncio"]({}), (200, configurado))
