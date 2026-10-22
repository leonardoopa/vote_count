"""Testes de `contador/tse/cache.py`."""
import time
import unittest
from unittest import mock

from contador.tse import cache as tse_cache
from contador.tse import cliente
from contador.tse.cache import LIMITE_404_POR_MINUTO, LIMITE_BUSCAS_POR_SEGUNDO, TTL_MUNICIPIOS, Cache
from tests.dados import CONFIG_MUNICIPIOS, DADOS


class CacheTse(unittest.TestCase):
    def resposta(self, status, dados=None):
        return cliente.Resposta(status, dados, '"etag"')

    def test_reaproveita_resposta(self):
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(200, DADOS)) as buscar:
            cache = Cache()
            cache.obter("u1")
            cache.obter("u1")
        self.assertEqual(buscar.call_count, 1)

    def test_304_mantem_dados(self):
        cache = Cache()
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(200, DADOS)):
            cache.obter("u1")
        cache._entradas["u1"].valido_ate = 0
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(304)):
            dados, status, _ = cache.obter("u1")
        self.assertIs(dados, DADOS)
        self.assertEqual(status, 304)

    def test_limite_de_404_protege_o_ip(self):
        cache = Cache()
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(404)) as buscar:
            for i in range(LIMITE_404_POR_MINUTO + 5):
                cache.obter(f"url{i}")
        self.assertEqual(buscar.call_count, LIMITE_404_POR_MINUTO)
        self.assertEqual(cache.obter("url-nova")[1], 429)


class Limites(unittest.TestCase):
    def resposta(self, status, dados=None):
        return cliente.Resposta(status, dados, '"etag"')

    def test_cache_nao_cresce_sem_limite(self):
        cache = Cache()
        with mock.patch.object(tse_cache, "MAX_ENTRADAS", 3), mock.patch.object(
            cliente, "buscar", return_value=self.resposta(200, DADOS)
        ):
            for i in range(10):
                cache.obter(f"u{i}")
        self.assertEqual(list(cache._entradas), ["u7", "u8", "u9"])

    def test_uso_recente_protege_da_remocao(self):
        cache = Cache()
        with mock.patch.object(tse_cache, "MAX_ENTRADAS", 2), mock.patch.object(
            cliente, "buscar", return_value=self.resposta(200, DADOS)
        ):
            cache.obter("a")
            cache.obter("b")
            cache.obter("a")
            cache.obter("c")
        self.assertEqual(list(cache._entradas), ["a", "c"])

    def test_varredura_de_cidades_nao_passa_do_limite_do_tse(self):
        cache = Cache()
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(200, DADOS)) as buscar:
            for i in range(LIMITE_BUSCAS_POR_SEGUNDO * 3):
                cache.obter(f"cidade{i}")
        self.assertEqual(buscar.call_count, LIMITE_BUSCAS_POR_SEGUNDO)
        self.assertEqual(cache.obter("outra")[1], 429)

    def test_limite_nao_marca_o_tse_como_fora_do_ar_para_sempre(self):
        cache = Cache()
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(200, DADOS)):
            for i in range(LIMITE_BUSCAS_POR_SEGUNDO + 1):
                cache.obter(f"u{i}")
            barrada = cache._entradas[f"u{LIMITE_BUSCAS_POR_SEGUNDO}"]
            self.assertLessEqual(barrada.valido_ate - time.time(), 1.5)

    def test_ttl_longo_para_a_lista_de_cidades(self):
        cache = Cache()
        with mock.patch.object(cliente, "buscar", return_value=self.resposta(200, CONFIG_MUNICIPIOS)) as buscar:
            cache.obter("config", ttl=TTL_MUNICIPIOS)
            cache.obter("config", ttl=TTL_MUNICIPIOS)
        self.assertEqual(buscar.call_count, 1)
        self.assertGreater(cache._entradas["config"].valido_ate - time.time(), 3600)
