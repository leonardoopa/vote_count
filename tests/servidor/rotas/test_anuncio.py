"""Testes de `contador/servidor/rotas/anuncio.py`."""
import unittest
from unittest import mock

from contador.servidor import estado, rotas


class Rota(unittest.TestCase):
    def test_rota_devolve_a_configuracao(self):
        configurado = {"ativo": True, "texto": "Oferta", "rotulo": "Publicidade"}
        with mock.patch.object(estado, "ANUNCIO", configurado):
            self.assertEqual(rotas.ROTAS_API["/api/anuncio"]({}), (200, configurado))


class IrParaOAnuncio(unittest.TestCase):
    def test_conta_o_clique_e_redireciona(self):
        contador = mock.Mock()
        with mock.patch.object(estado, "ANUNCIO", {"ativo": True, "texto": "Oferta", "rotulo": "", "link": "https://www.instagram.com/x/"}), \
             mock.patch.object(estado, "ACESSOS", contador):
            status, _, _, extras = rotas.ROTAS_ARQUIVO["/ir/anuncio"]({}, {})
        self.assertEqual((status, extras["Location"]), (302, "https://www.instagram.com/x/"))
        contador.clique.assert_called_once()

    def test_sem_link_nao_conta_nem_redireciona(self):
        contador = mock.Mock()
        with mock.patch.object(estado, "ANUNCIO", {"ativo": False}), mock.patch.object(estado, "ACESSOS", contador):
            self.assertEqual(rotas.ROTAS_ARQUIVO["/ir/anuncio"]({}, {})[0], 404)
        contador.clique.assert_not_called()


class NumerosDeAcesso(unittest.TestCase):
    def test_sem_chave_configurada_a_rota_nao_existe(self):
        with mock.patch.object(estado, "ACESSOS_CHAVE", ""):
            self.assertEqual(rotas.ROTAS_API["/api/acessos"]({"chave": [""]})[0], 404)

    def test_chave_errada_e_404_e_a_certa_mostra(self):
        contador = mock.Mock()
        contador.resumo.return_value = {"hoje": {}}
        with mock.patch.object(estado, "ACESSOS_CHAVE", "segredo"), mock.patch.object(estado, "ACESSOS", contador):
            self.assertEqual(rotas.ROTAS_API["/api/acessos"]({"chave": ["errada"]})[0], 404)
            self.assertEqual(rotas.ROTAS_API["/api/acessos"]({"chave": ["segredo"]}), (200, {"hoje": {}}))
