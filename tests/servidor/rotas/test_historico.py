"""Testes de `contador/servidor/rotas/historico.py`."""
import unittest
from unittest import mock

from contador.recursos import historico
from contador.recursos.historico import Historico
from contador.servidor import estado, rotas
from contador.tse import catalogo, cliente
from contador.tse.cache import INTERVALO_TSE
from tests.dados import CONFIG_MUNICIPIOS, tse


class RotaDoHistorico(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(estado, "HISTORICO", Historico())
        patch.start()
        self.addCleanup(patch.stop)

    def resultado(self, dados, **consulta):
        padrao = {"ambiente": ["simulado"], "cargo": ["presidente"], "uf": ["br"]}
        padrao.update({k: [v] for k, v in consulta.items()})
        with mock.patch.object(estado.CACHE, "obter", return_value=(dados, 200, 0)):
            return rotas.resultado(padrao), padrao

    def test_resultado_registra_e_a_api_devolve(self):
        (status, _), consulta = self.resultado(tse([300, 600]))
        self.assertEqual(status, 200)
        self.resultado(tse([310, 650], apuradas=300))
        status, corpo = rotas.historico_da_selecao(consulta)
        self.assertEqual(status, 200)
        self.assertEqual([p["apuradas"] for p in corpo["pontos"]], [250, 300])
        self.assertEqual([c["numero"] for c in corpo["candidatos"]], ["22", "13"])

    def test_cada_ponto_traz_tudo_que_o_replay_usa(self):
        (_, _), consulta = self.resultado(tse([300, 600], final=True, situacoes={"22": "Eleito"}))
        _, corpo = rotas.historico_da_selecao(consulta)
        nomes = {c["numero"]: c for c in corpo["candidatos"]}
        for ponto in corpo["pontos"]:
            self.assertEqual(set(ponto), {"totalizacao", "percentual", "apuradas", "secoes", "final", "placar"})
            for numero, votos, percentual, situacao in ponto["placar"]:  # o ranking do replay sai daqui
                self.assertIn(numero, nomes)
                self.assertTrue(nomes[numero]["nome"] and nomes[numero]["partido"])
                self.assertIsInstance(votos, int)
                self.assertIsInstance(percentual, float)
                self.assertIn(situacao, ("", "e", "2"))
        self.assertEqual(corpo["pontos"][0]["placar"][0], ["22", 600, 66.67, "e"])

    def test_cidade_e_serie_propria(self):
        config = catalogo.url_municipios("simulado", "governador", 1)
        cidade = catalogo.montar_url("simulado", "governador", "sp", 1, municipio="62910")
        respostas = {config: (CONFIG_MUNICIPIOS, 200, 0), cidade: (tse([300, 600]), 200, 0)}
        da_cidade = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"], "municipio": ["62910"]}
        da_uf = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"]}
        with mock.patch.object(estado.CACHE, "obter", side_effect=lambda url, ttl=INTERVALO_TSE: respostas[url]):
            self.assertEqual(rotas.resultado(da_cidade)[0], 200)
        self.assertEqual(len(rotas.historico_da_selecao(da_cidade)[1]["pontos"]), 1)
        self.assertEqual(rotas.historico_da_selecao(da_uf)[1]["pontos"], [])

    def test_serie_vazia_nao_e_erro(self):
        status, corpo = rotas.historico_da_selecao({"ambiente": ["simulado"]})
        self.assertEqual((status, corpo), (200, {"candidatos": [], "pontos": []}))

    def test_cargos_sem_historico_dao_400(self):
        for consulta in (
            {"cargo": ["deputado-federal"], "uf": ["sp"]},
            {"cargo": ["deputado-estadual"], "uf": ["sp"]},
            {"cargo": ["deputado-distrital"], "uf": ["df"]},
        ):
            with self.subTest(consulta=consulta):
                self.assertEqual(rotas.historico_da_selecao(consulta)[0], 400)

    def test_deputado_nao_registra(self):
        self.resultado(tse([300, 600]), cargo="deputado-federal", uf="sp")
        self.assertEqual(estado.HISTORICO.consultar(("simulado", "deputado-federal", "sp", 1, "")), {"candidatos": [], "pontos": []})

    def test_parametros_invalidos_dao_400(self):
        for consulta in (
            {"cargo": ["x"]}, {"uf": ["sp"], "cargo": ["senador"], "turno": ["2"]}, {"ambiente": ["../x"]},
            {"turno": ["3"]}, {"uf": ["br"], "municipio": ["62910"]}, {"uf": ["sp"], "municipio": ["abc"]},
            {"uf": ["sp"], "municipio": ["../../"]},
        ):
            with self.subTest(consulta=consulta):
                self.assertEqual(rotas.historico_da_selecao(consulta)[0], 400)

    def test_a_api_nunca_toca_o_tse(self):
        recusa = AssertionError("o histórico não pode consultar o TSE")
        with mock.patch.object(cliente, "buscar", side_effect=recusa), mock.patch.object(estado.CACHE, "obter", side_effect=recusa):
            for consulta in ({}, {"uf": ["sp"], "cargo": ["governador"], "municipio": ["62910"]}, {"cargo": ["senador"], "uf": ["mg"], "turno": ["1"]}):
                self.assertEqual(rotas.historico_da_selecao(consulta)[0], 200)

    def test_rota_registrada_na_tabela(self):
        self.assertIs(rotas.ROTAS_API["/api/historico"], rotas.historico_da_selecao)
        self.assertIs(rotas.ROTAS_API["/api/resultado"], rotas.resultado)


class Atualizacoes(unittest.TestCase):
    """Feed: cada totalização é comparada com a anterior."""

    def ponto(self, *args, **kw):
        return historico.ponto_de(tse(*args, **kw))

    def feed(self, *dados):
        pontos, nomes = [], {}
        for d in dados:
            ponto, novos = historico.ponto_de(d)
            pontos.append(ponto)
            nomes.update(novos)
        return historico.eventos(pontos, nomes)

    def test_serie_zerada_nao_tem_evento(self):
        self.assertEqual(self.feed(tse([0, 0], apuradas=0, ht="")), [])

    def test_primeira_totalizacao_diz_que_nao_viu_o_comeco(self):
        [evento] = self.feed(tse([300, 600], apuradas=250))
        self.assertEqual(evento["tipo"], "inicio")
        self.assertIn("Primeira totalização registrada", evento["texto"])
        self.assertIn("25,00% das seções", evento["texto"])

    def test_apuracao_que_comeca_depois_do_zerado(self):
        feed = self.feed(tse([0, 0], apuradas=0, ht=""), tse([300, 600], apuradas=250))
        self.assertEqual([e["tipo"] for e in feed], ["inicio"])
        self.assertTrue(feed[0]["texto"].startswith("A apuração começou"))

    def test_resumo_traz_secoes_novas_e_variacao_dos_dois_primeiros(self):
        feed = self.feed(tse([300, 600], apuradas=250, ht="20:00:00"), tse([500, 600], apuradas=500, ht="20:05:00"))
        self.assertEqual(len(feed), 2)
        resumo = feed[0]
        self.assertEqual((resumo["tipo"], resumo["hora"]), ("totalizacao", "21/10/2026 20:05:00"))
        self.assertIn("+250 seções apuradas (50,00% do total)", resumo["texto"])
        self.assertIn("BRUNO CASTRO 54,55% (−12,12)", resumo["texto"])
        self.assertIn("ANA LIMA 45,45% (+12,12)", resumo["texto"])

    def test_mudanca_de_lider(self):
        feed = self.feed(tse([300, 600]), tse([700, 600], apuradas=500, ht="20:05:00"))
        self.assertEqual([e["tipo"] for e in feed], ["lider", "totalizacao", "inicio"])
        self.assertEqual(feed[0]["texto"], "ANA LIMA passou à frente de BRUNO CASTRO.")

    def test_eleito_e_segundo_turno_e_final_aparecem_uma_vez(self):
        a = tse([700, 600], apuradas=900)
        b = tse([700, 600], apuradas=1000, final=True, ht="20:30:00", situacoes={"13": "2º turno", "22": "2º turno"})
        c = tse([700, 600], apuradas=1000, final=True, ht="20:31:00", situacoes={"13": "2º turno", "22": "2º turno"})
        tipos = [e["tipo"] for e in self.feed(a, b, c)]
        self.assertEqual(tipos.count("segundo_turno"), 2)
        self.assertEqual(tipos.count("final"), 1)
        eleito = self.feed(a, tse([700, 600], apuradas=1000, final=True, situacoes={"13": "Eleito"}))
        self.assertIn("ANA LIMA foi eleito.", [e["texto"] for e in eleito])

    def test_final_vem_antes_do_resumo_no_mesmo_horario(self):
        feed = self.feed(tse([700, 600], apuradas=900), tse([700, 600], apuradas=1000, final=True, ht="20:30:00"))
        self.assertEqual([e["tipo"] for e in feed], ["final", "totalizacao", "inicio"])

    def test_no_maximo_quarenta_eventos_do_mais_novo_ao_mais_antigo(self):
        dados = [tse([100 + i, 50], apuradas=10 + i, ht=f"20:{i:02d}:00") for i in range(60)]
        feed = self.feed(*dados)
        self.assertEqual(len(feed), historico.MAX_EVENTOS)
        self.assertEqual(feed[0]["hora"], "21/10/2026 20:59:00")

    def test_rota_devolve_o_feed_e_valida_a_selecao(self):
        with mock.patch.object(estado, "HISTORICO", Historico()):
            self.assertEqual(rotas.atualizacoes_da_selecao({"ambiente": ["simulado"]}), (200, {"eventos": []}))
            with mock.patch.object(estado.CACHE, "obter", return_value=(tse([300, 600]), 200, 0)):
                rotas.resultado({"ambiente": ["simulado"]})
            status, corpo = rotas.atualizacoes_da_selecao({"ambiente": ["simulado"]})
            self.assertEqual((status, len(corpo["eventos"])), (200, 1))
            self.assertEqual(rotas.atualizacoes_da_selecao({"cargo": ["deputado-federal"], "uf": ["sp"]})[0], 400)
        self.assertIs(rotas.ROTAS_API["/api/atualizacoes"], rotas.atualizacoes_da_selecao)
