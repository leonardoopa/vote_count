import time
import unittest
from unittest import mock

import contador
import servidor
from test_contador import CONFIG_MUNICIPIOS, DADOS


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


class ValidarMunicipio(unittest.TestCase):
    def test_sem_municipio(self):
        self.assertEqual(servidor.validar_municipio({}, "sp"), "")

    def test_codigo_valido(self):
        self.assertEqual(servidor.validar_municipio({"municipio": ["71072"]}, "sp"), "71072")

    def test_recusa_formato_estranho_antes_de_virar_url(self):
        for codigo in ("7107", "710723", "7107a", "../../", "７１０７２"):
            with self.subTest(codigo=codigo), self.assertRaises(ValueError):
                servidor.validar_municipio({"municipio": [codigo]}, "sp")

    def test_brasil_inteiro_nao_tem_cidade(self):
        with self.assertRaises(ValueError):
            servidor.validar_municipio({"municipio": ["71072"]}, "br")


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


class Limites(unittest.TestCase):
    def resposta(self, status, dados=None):
        return contador.Resposta(status, dados, '"etag"')

    def test_cache_nao_cresce_sem_limite(self):
        cache = servidor.Cache()
        with mock.patch.object(servidor, "MAX_ENTRADAS", 3), mock.patch.object(
            contador, "buscar", return_value=self.resposta(200, DADOS)
        ):
            for i in range(10):
                cache.obter(f"u{i}")
        self.assertEqual(list(cache._entradas), ["u7", "u8", "u9"])

    def test_uso_recente_protege_da_remocao(self):
        cache = servidor.Cache()
        with mock.patch.object(servidor, "MAX_ENTRADAS", 2), mock.patch.object(
            contador, "buscar", return_value=self.resposta(200, DADOS)
        ):
            cache.obter("a")
            cache.obter("b")
            cache.obter("a")
            cache.obter("c")
        self.assertEqual(list(cache._entradas), ["a", "c"])

    def test_varredura_de_cidades_nao_passa_do_limite_do_tse(self):
        cache = servidor.Cache()
        with mock.patch.object(contador, "buscar", return_value=self.resposta(200, DADOS)) as buscar:
            for i in range(servidor.LIMITE_BUSCAS_POR_SEGUNDO * 3):
                cache.obter(f"cidade{i}")
        self.assertEqual(buscar.call_count, servidor.LIMITE_BUSCAS_POR_SEGUNDO)
        self.assertEqual(cache.obter("outra")[1], 429)

    def test_limite_nao_marca_o_tse_como_fora_do_ar_para_sempre(self):
        cache = servidor.Cache()
        with mock.patch.object(contador, "buscar", return_value=self.resposta(200, DADOS)):
            for i in range(servidor.LIMITE_BUSCAS_POR_SEGUNDO + 1):
                cache.obter(f"u{i}")
            barrada = cache._entradas[f"u{servidor.LIMITE_BUSCAS_POR_SEGUNDO}"]
            self.assertLessEqual(barrada.valido_ate - time.time(), 1.5)

    def test_ttl_longo_para_a_lista_de_cidades(self):
        cache = servidor.Cache()
        with mock.patch.object(contador, "buscar", return_value=self.resposta(200, CONFIG_MUNICIPIOS)) as buscar:
            cache.obter("config", ttl=servidor.TTL_MUNICIPIOS)
            cache.obter("config", ttl=servidor.TTL_MUNICIPIOS)
        self.assertEqual(buscar.call_count, 1)
        self.assertGreater(cache._entradas["config"].valido_ate - time.time(), 3600)


class Cidades(unittest.TestCase):
    def cache_falso(self, resultados_por_url):
        def obter(url, ttl=servidor.INTERVALO_TSE):
            return resultados_por_url.get(url, (None, 404, 0))

        return mock.patch.object(servidor.CACHE, "obter", side_effect=obter)

    def urls(self):
        config = contador.url_municipios("oficial", "presidente", 1)
        cidade = contador.montar_url("oficial", "presidente", "sp", 1, municipio="62910")
        return config, cidade

    def test_lista_para_o_seletor(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            status, corpo = servidor.municipios_da_uf({"cargo": ["presidente"], "uf": ["sp"]})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["uf"], "sp")
        self.assertEqual(corpo["municipios"][0], {"codigo": "62910", "nome": "Campinas", "capital": False})

    def test_lista_exige_uf(self):
        self.assertEqual(servidor.municipios_da_uf({})[0], 400)  # presidente, Brasil

    def test_lista_com_tse_fora_do_ar(self):
        with self.cache_falso({}):
            self.assertEqual(servidor.municipios_da_uf({"uf": ["sp"]})[0], 404)

    def test_resultado_da_cidade(self):
        config, cidade = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0), cidade: (DADOS, 200, 0)}):
            status, corpo = servidor.resultado({"uf": ["sp"], "municipio": ["62910"]})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["municipio"], {"codigo": "62910", "nome": "Campinas"})

    def test_resultado_da_uf_inteira_nao_traz_municipio(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(DADOS, 200, 0)):
            self.assertIsNone(servidor.resultado({"uf": ["sp"]})[1]["municipio"])

    def test_codigo_que_o_tse_nao_lista_nao_chega_ao_tse(self):
        config, _ = self.urls()
        pedidos = []

        def obter(url, ttl=servidor.INTERVALO_TSE):
            pedidos.append(url)
            return (CONFIG_MUNICIPIOS, 200, 0) if url == config else (DADOS, 200, 0)

        with mock.patch.object(servidor.CACHE, "obter", side_effect=obter):
            status, _ = servidor.resultado({"uf": ["sp"], "municipio": ["99999"]})
        self.assertEqual(status, 400)
        self.assertEqual(pedidos, [config])  # só a lista; nenhuma URL de resultado inventada

    def test_cidade_de_outra_uf_e_recusada(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            self.assertEqual(servidor.resultado({"uf": ["sp"], "municipio": ["97012"]})[0], 400)  # Brasília

    def test_cidade_sem_resultado_publicado_e_404(self):
        config, _ = self.urls()
        with self.cache_falso({config: (CONFIG_MUNICIPIOS, 200, 0)}):
            self.assertEqual(servidor.resultado({"uf": ["sp"], "municipio": ["62910"]})[0], 404)

    def test_cidade_com_lista_indisponivel(self):
        with self.cache_falso({}):
            self.assertEqual(servidor.resultado({"uf": ["sp"], "municipio": ["62910"]})[0], 404)


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
