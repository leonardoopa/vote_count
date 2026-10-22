"""Testes de `contador/servidor/rotas/placar.py` e da lista de cidades da UF (`rotas/municipios.py`)."""
import unittest
from unittest import mock

from contador.servidor import estado, rotas
from contador.tse import catalogo
from contador.tse.cache import INTERVALO_TSE
from tests.dados import CONFIG_MUNICIPIOS, DADOS


class Cidades(unittest.TestCase):
    def cache_falso(self, resultados_por_url):
        def obter(url, ttl=INTERVALO_TSE):
            return resultados_por_url.get(url, (None, 404, 0))

        return mock.patch.object(estado.CACHE, "obter", side_effect=obter)

    def urls(self):
        config = catalogo.url_municipios("oficial", "presidente", 1)
        cidade = catalogo.montar_url("oficial", "presidente", "sp", 1, municipio="62910")
        return config, cidade

    def test_lista_para_o_seletor(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            status, corpo = rotas.municipios_da_uf({"cargo": ["presidente"], "uf": ["sp"]})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["uf"], "sp")
        self.assertEqual(corpo["municipios"][0], {"codigo": "62910", "nome": "Campinas", "capital": False})

    def test_lista_exige_uf(self):
        self.assertEqual(rotas.municipios_da_uf({})[0], 400)  # presidente, Brasil

    def test_lista_com_tse_fora_do_ar(self):
        with self.cache_falso({}):
            self.assertEqual(rotas.municipios_da_uf({"uf": ["sp"]})[0], 404)

    def test_resultado_da_cidade(self):
        config, cidade = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0), cidade: (DADOS, 200, 0)}):
            status, corpo = rotas.resultado({"uf": ["sp"], "municipio": ["62910"]})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["municipio"], {"codigo": "62910", "nome": "Campinas"})

    def test_resultado_da_uf_inteira_nao_traz_municipio(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(DADOS, 200, 0)):
            self.assertIsNone(rotas.resultado({"uf": ["sp"]})[1]["municipio"])

    def test_codigo_que_o_tse_nao_lista_nao_chega_ao_tse(self):
        config, _ = self.urls()
        pedidos = []

        def obter(url, ttl=INTERVALO_TSE):
            pedidos.append(url)
            return (CONFIG_MUNICIPIOS, 200, 0) if url == config else (DADOS, 200, 0)

        with mock.patch.object(estado.CACHE, "obter", side_effect=obter):
            status, _ = rotas.resultado({"uf": ["sp"], "municipio": ["99999"]})
        self.assertEqual(status, 400)
        self.assertEqual(pedidos, [config])  # só a lista; nenhuma URL de resultado inventada

    def test_cidade_de_outra_uf_e_recusada(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            self.assertEqual(rotas.resultado({"uf": ["sp"], "municipio": ["97012"]})[0], 400)  # Brasília

    def test_cidade_sem_resultado_publicado_e_404(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            self.assertEqual(rotas.resultado({"uf": ["sp"], "municipio": ["62910"]})[0], 404)

    def test_cidade_com_lista_indisponivel(self):
        with self.cache_falso({}):
            self.assertEqual(rotas.resultado({"uf": ["sp"], "municipio": ["62910"]})[0], 404)


class Resultado(unittest.TestCase):
    def test_sem_dados_404(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(None, 404, 0)):
            self.assertEqual(rotas.resultado({})[0], 404)

    def test_com_dados(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(DADOS, 200, 0)):
            status, corpo = rotas.resultado({"top": ["1"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["candidatos"]), 1)
        self.assertNotIn("aviso", corpo)

    def test_aviso_quando_tse_falha_com_dado_antigo(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(DADOS, 500, 0)):
            self.assertIn("aviso", rotas.resultado({})[1])
