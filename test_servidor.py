import unittest
from unittest import mock

import contador
import servidor
from test_contador import DADOS


class Validar(unittest.TestCase):
    def test_padroes(self):
        self.assertEqual(servidor.validar({}), ("presidente", "br", "oficial", 1, servidor.TOP_PADRAO))

    def test_top_limitado(self):
        self.assertEqual(servidor.validar({"top": ["5000"]})[4], servidor.TOP_MAXIMO)
        self.assertEqual(servidor.validar({"top": ["0"]})[4], 1)

    def test_entradas_invalidas(self):
        for consulta in (
            {"cargo": ["x"]},
            {"cargo": ["governador"]},  # sem UF
            {"uf": ["../etc"]},
            {"turno": ["3"]},
            {"ambiente": ["https://exemplo.com"]},
            {"top": ["-1"]},
            {"cargo": ["deputado-distrital"], "uf": ["sp"]},
            {"cargo": ["deputado-estadual"], "uf": ["df"]},
            {"cargo": ["senador"], "uf": ["sp"], "turno": ["2"]},
        ):
            with self.subTest(consulta=consulta), self.assertRaises(ValueError):
                servidor.validar(consulta)


class Resumir(unittest.TestCase):
    def test_estrutura(self):
        resumo = servidor.resumir(DADOS, 10)
        self.assertFalse(resumo["final"])
        self.assertEqual(resumo["secoes"], {"total": 1000, "apuradas": 250, "percentual": 25.0})
        self.assertEqual(resumo["votos"]["pct_nulos"], 3.33)
        self.assertEqual([c["nome"] for c in resumo["candidatos"]], ["BIA", "ANA"])
        self.assertEqual(resumo["candidatos"][0]["situacao"], "2º turno")

    def test_top(self):
        resumo = servidor.resumir(DADOS, 1)
        self.assertEqual(len(resumo["candidatos"]), 1)
        self.assertEqual(resumo["total_candidatos"], 2)


class CacheTse(unittest.TestCase):
    def resposta(self, status, dados=None):
        return contador.Resposta(status, dados, '"etag"')

    def test_reaproveita_resposta(self):
        with mock.patch.object(contador, "buscar", return_value=self.resposta(200, DADOS)) as buscar:
            cache = servidor.Cache()
            cache.obter("u1")
            cache.obter("u1")
        self.assertEqual(buscar.call_count, 1)

    def test_304_mantem_dados(self):
        cache = servidor.Cache()
        with mock.patch.object(contador, "buscar", return_value=self.resposta(200, DADOS)):
            cache.obter("u1")
        cache._entradas["u1"].valido_ate = 0
        with mock.patch.object(contador, "buscar", return_value=self.resposta(304)):
            dados, status, _ = cache.obter("u1")
        self.assertIs(dados, DADOS)
        self.assertEqual(status, 304)

    def test_limite_de_404_protege_o_ip(self):
        cache = servidor.Cache()
        with mock.patch.object(contador, "buscar", return_value=self.resposta(404)) as buscar:
            for i in range(servidor.LIMITE_404_POR_MINUTO + 5):
                cache.obter(f"url{i}")
        self.assertEqual(buscar.call_count, servidor.LIMITE_404_POR_MINUTO)
        self.assertEqual(cache.obter("url-nova")[1], 429)


class Resultado(unittest.TestCase):
    def test_sem_dados_404(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(None, 404, 0)):
            self.assertEqual(servidor.resultado({})[0], 404)

    def test_com_dados(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(DADOS, 200, 0)):
            status, corpo = servidor.resultado({"top": ["1"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["candidatos"]), 1)
        self.assertNotIn("aviso", corpo)

    def test_aviso_quando_tse_falha_com_dado_antigo(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(DADOS, 500, 0)):
            self.assertIn("aviso", servidor.resultado({})[1])


if __name__ == "__main__":
    unittest.main()
