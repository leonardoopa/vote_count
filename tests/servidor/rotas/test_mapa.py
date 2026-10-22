"""Testes de `contador/servidor/rotas/mapa.py`."""
import time
import unittest
from unittest import mock

from contador.recursos import mapa
from contador.servidor import estado, respostas, rotas
from contador.tse import catalogo
from tests.dados import AGORA, DOIS, TRES, arquivo, fonte_com, url


class RotaMapa(unittest.TestCase):
    def setUp(self):
        respostas._PRONTAS.clear()
        self.addCleanup(respostas._PRONTAS.clear)

    def obter(self, respostas):
        return mock.patch.object(estado.CACHE, "obter", side_effect=lambda url, ttl=None: respostas.get(url, (None, 404, 0)))

    def test_so_presidente_e_governador(self):
        for consulta in ({"cargo": ["senador"]}, {"cargo": ["deputado-federal"]}, {"cargo": ["x"]}, {"turno": ["3"]},
                         {"ambiente": ["https://exemplo.com"]}, {"cargo": ["presidente"], "turno": ["1;2"]}):
            with self.subTest(consulta=consulta):
                with mock.patch.object(estado.CACHE, "obter") as obter:
                    self.assertEqual(rotas.mapa_por_uf(consulta)[0], 400)
                obter.assert_not_called()

    def test_uf_do_visitante_e_ignorada(self):
        with self.obter({}):
            self.assertEqual(rotas.mapa_por_uf({"cargo": ["governador"], "uf": ["../etc"]})[0], 404)

    def test_tse_ainda_nao_publicou(self):
        with self.obter({}):
            status, corpo = rotas.mapa_por_uf({})
        self.assertEqual(status, 404)
        self.assertIn("ainda não publicou", corpo["erro"])

    def test_tse_fora_do_ar(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(None, 503, 0)):
            self.assertEqual(rotas.mapa_por_uf({})[0], 503)

    def test_bloqueio_vira_503(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(None, 429, 0)):
            self.assertEqual(rotas.mapa_por_uf({})[0], 503)

    def test_resposta_completa(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*catalogo.UFS, "br", "zz")}
        with self.obter(dados):
            status, corpo = rotas.mapa_por_uf({"cargo": ["presidente"], "turno": ["1"], "ambiente": ["oficial"]})
        self.assertEqual(status, 200)
        self.assertEqual((corpo["cargo"], corpo["turno"], corpo["ambiente"]), ("presidente", 1, "oficial"))
        self.assertEqual(len(corpo["ufs"]), 27)

    def test_visitantes_dividem_a_mesma_rodada(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*catalogo.UFS, "br", "zz")}
        with self.obter(dados) as obter:
            rotas.mapa_por_uf({})
            primeira = obter.call_count
            rotas.mapa_por_uf({})
        self.assertEqual(primeira, 29)
        self.assertEqual(obter.call_count, 29)  # a segunda veio pronta

    def test_selecoes_diferentes_nao_se_misturam(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*catalogo.UFS, "br", "zz")}
        with self.obter(dados):
            self.assertEqual(rotas.mapa_por_uf({"turno": ["1"]})[0], 200)
            self.assertEqual(rotas.mapa_por_uf({"turno": ["2"]})[0], 404)
            self.assertEqual(rotas.mapa_por_uf({"ambiente": ["simulado"]})[0], 404)

    def test_resposta_pronta_vence(self):
        chamadas = []
        construir = lambda: (chamadas.append(1) or 200, {})
        respostas.lembrar("longa", construir, ttl=100)
        respostas.lembrar("longa", construir, ttl=100)
        self.assertEqual(len(chamadas), 1)
        respostas.lembrar("curta", construir, ttl=0)
        respostas.lembrar("curta", construir, ttl=0)
        self.assertEqual(len(chamadas), 3)


class RotasDerivadas(unittest.TestCase):
    def setUp(self):
        respostas._PRONTAS.clear()
        self.addCleanup(respostas._PRONTAS.clear)

    def obter(self, respostas):
        return mock.patch.object(estado.CACHE, "obter", side_effect=lambda url, ttl=None: respostas.get(url, (None, 404, 0)))

    def test_regioes_e_mapa_dividem_a_mesma_rodada(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*catalogo.UFS, "br", "zz")}
        with self.obter(dados) as obter:
            self.assertEqual(rotas.mapa_por_uf({})[0], 200)
            status, corpo = rotas.regioes_do_pais({})
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["regioes"]), 6)
        self.assertEqual(obter.call_count, 29)

    def test_regioes_so_do_presidente_mesmo_que_peçam_outro_cargo(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*catalogo.UFS, "br", "zz")}
        with self.obter(dados):
            self.assertEqual(rotas.regioes_do_pais({"cargo": ["governador"]})[0], 200)

    def test_disputas_de_governador_e_senador(self):
        for cargo in ("governador", "senador"):
            dados = {url(cargo, uf): (arquivo(TRES), 200, time.time()) for uf in catalogo.UFS}
            with self.subTest(cargo=cargo), self.obter(dados):
                status, corpo = rotas.disputas_apertadas({"cargo": [cargo]})
                self.assertEqual(status, 200)
                self.assertEqual(len(corpo["disputas"]), 27)
                self.assertEqual(corpo["cargo"], cargo)

    def test_disputas_e_regioes_validam_a_selecao(self):
        for rota, consulta in (
            (rotas.disputas_apertadas, {}), (rotas.disputas_apertadas, {"cargo": ["presidente"]}),
            (rotas.disputas_apertadas, {"cargo": ["senador"], "turno": ["2"]}),
            (rotas.disputas_apertadas, {"cargo": ["governador"], "ambiente": ["../x"]}),
            (rotas.regioes_do_pais, {"turno": ["9"]}),
        ):
            with self.subTest(rota=rota.__name__, consulta=consulta), mock.patch.object(estado.CACHE, "obter") as obter:
                self.assertEqual(rota(consulta)[0], 400)
                obter.assert_not_called()

    def test_erro_do_tse_passa_adiante(self):
        with self.obter({}):
            self.assertEqual(rotas.regioes_do_pais({})[0], 404)
            self.assertEqual(rotas.disputas_apertadas({"cargo": ["governador"]})[0], 404)

    def test_rotas_na_tabela(self):
        for caminho, funcao in (("/api/mapa", rotas.mapa_por_uf), ("/api/regioes", rotas.regioes_do_pais), ("/api/disputas", rotas.disputas_apertadas)):
            self.assertIs(rotas.ROTAS_API[caminho], funcao)


class Senado(unittest.TestCase):
    def corpo(self, eleitos=(), zeradas=(), faltando=()):
        def dados(uf):
            marca = "Eleito" if uf in eleitos else ""
            zero = uf in zeradas
            votos = (0, 0, 0) if zero else (500, 300, 200)
            return arquivo([("13", "Ana", "PT", votos[0], "50,00", marca), ("22", "Bia", "PL", votos[1], "30,00", marca), ("55", "Caio", "PSD", votos[2], "20,00", "")],
                           secoes=(1000, 0 if zero else 500))

        dados_por_uf = {uf: dados(uf) for uf in catalogo.UFS if uf not in faltando}
        fonte = fonte_com("senador", 1, dados_por_uf)
        return mapa.resumo_por_uf(fonte, "oficial", "senador", 1, pausa=0, agora=lambda: AGORA)[0]

    def test_cinquenta_e_quatro_cadeiras_duas_por_uf(self):
        senado = mapa.senado(self.corpo())
        self.assertEqual((senado["casa"], senado["total"], senado["em_disputa"], senado["fora_da_disputa"]), ("senado", 81, 54, 27))
        self.assertEqual(len(senado["cadeiras"]), 54)
        self.assertEqual([c["uf"] for c in senado["cadeiras"]][:4], ["ac", "ac", "al", "al"])

    def test_eleito_liderando_e_indefinida(self):
        senado = mapa.senado(self.corpo(eleitos=("sp",), zeradas=("rj",)))
        por_uf = {}
        for c in senado["cadeiras"]:
            por_uf.setdefault(c["uf"], []).append(c)
        self.assertEqual([(c["partido"], c["situacao"]) for c in por_uf["sp"]], [("PT", "eleito"), ("PL", "eleito")])
        self.assertEqual([(c["partido"], c["situacao"]) for c in por_uf["mg"]], [("PT", "liderando"), ("PL", "liderando")])
        self.assertEqual([(c["partido"], c["nome"], c["situacao"]) for c in por_uf["rj"]], [(None, None, "indefinida")] * 2)

    def test_partidos_contam_eleitos_e_liderando(self):
        senado = mapa.senado(self.corpo(eleitos=("sp", "mg"), zeradas=("rj",)))
        self.assertEqual(senado["partidos"], [
            {"partido": "PL", "eleitos": 2, "liderando": 24}, {"partido": "PT", "eleitos": 2, "liderando": 24},
        ])

    def test_uf_sem_dados_tambem_fica_indefinida(self):
        corpo = self.corpo(faltando=("sp", "rj", "mg"))  # 3 UFs sem arquivo: a rodada para nos 404 e o que não foi buscado fica sem dados
        senado = mapa.senado(corpo)
        self.assertEqual(len(senado["cadeiras"]), 54)
        self.assertEqual(sum(1 for c in senado["cadeiras"] if c["situacao"] == "indefinida") % 2, 0)
        self.assertIn("aviso", senado)

    def test_nao_mexe_no_corpo_e_leva_o_que_importa(self):
        corpo = self.corpo(eleitos=("sp",))
        antes = repr(corpo)
        senado = mapa.senado(corpo)
        self.assertEqual(repr(corpo), antes)
        self.assertEqual((senado["ambiente"], senado["final"], senado["idade_s"]), ("oficial", False, 0))

    def test_rota(self):
        respostas._PRONTAS.clear()
        self.addCleanup(respostas._PRONTAS.clear)
        dados = {url("senador", uf): (arquivo(TRES), 200, time.time()) for uf in catalogo.UFS}
        with mock.patch.object(estado.CACHE, "obter", side_effect=lambda u, ttl=None: dados.get(u, (None, 404, 0))):
            status, corpo = rotas.senado_em_disputa({"ambiente": ["oficial"], "cargo": ["presidente"]})  # o cargo do visitante é ignorado
        self.assertEqual((status, corpo["casa"], len(corpo["cadeiras"])), (200, "senado", 54))
        self.assertEqual(rotas.senado_em_disputa({"ambiente": ["../x"]})[0], 400)
