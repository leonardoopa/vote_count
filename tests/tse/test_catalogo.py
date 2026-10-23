"""Testes de `contador/tse/catalogo.py`."""
import unittest

from contador.tse import catalogo


class UrlFoto(unittest.TestCase):
    def test_presidente(self):
        self.assertEqual(
            catalogo.url_foto("oficial", "presidente", "br", 1, "280002551544"),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/fotos/br/280002551544.jpeg",
        )

    def test_cargo_estadual_no_segundo_turno_fica_na_pasta_da_uf(self):
        self.assertEqual(
            catalogo.url_foto("oficial", "governador", "sp", 2, "250002541303"),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/fotos/sp/250002541303.jpeg",
        )

    def test_foto_de_presidente_fica_na_pasta_br_mesmo_dentro_de_um_estado(self):
        self.assertEqual(
            catalogo.url_foto("oficial", "presidente", "pe", 1, "280002551544"),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/fotos/br/280002551544.jpeg",
        )

    def test_so_aceita_numero_de_candidato(self):
        for sqcand in (None, "", "12 3", "../x", "1.jpeg?x=1", "١٢٣"):
            with self.subTest(sqcand=sqcand):
                self.assertIsNone(catalogo.url_foto("oficial", "presidente", "br", 1, sqcand))


class MontarUrl(unittest.TestCase):
    def test_presidente_oficial(self):
        self.assertEqual(
            catalogo.montar_url("oficial", "presidente", "br", 1),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json",
        )

    def test_governador_segundo_turno(self):
        self.assertEqual(
            catalogo.montar_url("oficial", "governador", "sp", 2),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/dados/sp/sp-c0003-e006260-u.json",
        )

    def test_cidade_usa_uf_mais_codigo_no_nome_do_arquivo(self):
        self.assertEqual(
            catalogo.montar_url("oficial", "presidente", "sp", 1, municipio="71072"),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/sp/sp71072-c0001-e006257-u.json",
        )

    def test_cidade_de_cargo_estadual_no_segundo_turno(self):
        self.assertEqual(
            catalogo.montar_url("oficial", "governador", "sp", 2, municipio="62910"),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/dados/sp/sp62910-c0003-e006260-u.json",
        )

    def test_lista_de_cidades_e_por_eleicao(self):
        self.assertEqual(
            catalogo.url_municipios("oficial", "presidente", 1),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json",
        )
        self.assertIn("/6259/config/mun-e006259-cm.json", catalogo.url_municipios("oficial", "senador", 1))

    def test_simulado(self):
        self.assertIn("resultados-sim.tse.jus.br/simulado/simulado2026/ele2026/21272/", catalogo.montar_url("simulado", "senador", "ac", 1))
