import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

import contador
import historico
import servidor
from historico import Historico
from test_contador import CONFIG_MUNICIPIOS

CHAVE = ("simulado", "presidente", "br", 1, "")
LULA, JAIR = ("13", "Ana Lima", "PT"), ("22", "Bruno Castro", "PL")


def tse(votos, apuradas=250, dt="21/10/2026", ht="20:00:00", final=False, situacoes=None, candidatos=(LULA, JAIR)):
    """Arquivo do TSE no formato real, com um candidato por partido. `votos` segue a ordem de `candidatos`."""
    total, validos = 1000, sum(votos) or 1
    situacoes = situacoes or {}
    return {
        "tf": "s" if final else "n", "dt": dt, "ht": ht, "dg": dt, "hg": ht or "16:59:00",
        "s": {"ts": str(total), "st": str(apuradas), "pst": f"{100 * apuradas / total:.2f}".replace(".", ",")},
        "e": {"te": "5000", "c": "900", "pc": "90,00", "a": "100", "pa": "2,00"},
        "v": {"tv": str(sum(votos)), "vb": "20", "pvb": "2,22", "tvn": "30", "ptvn": "3,33"},
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [{
                "n": numero, "nm": nome.upper(), "nmu": nome.upper(), "vap": str(v),
                "pvap": f"{100 * v / validos:.2f}".replace(".", ","), "st": situacoes.get(numero, ""),
            }]}]}
            for (numero, nome, partido), v in zip(candidatos, votos)
        ]}],
    }


class Ponto(unittest.TestCase):
    def test_traz_tudo_que_o_replay_usa(self):
        ponto, nomes = historico.ponto_de(tse([300, 600], apuradas=250))
        self.assertEqual(ponto, {
            "totalizacao": "21/10/2026 20:00:00", "percentual": 25.0, "apuradas": 250, "secoes": 1000,
            "final": False, "placar": [["22", 600, 66.67, ""], ["13", 300, 33.33, ""]],
        })
        self.assertEqual(nomes, {"13": ["ANA LIMA", "PT"], "22": ["BRUNO CASTRO", "PL"]})

    def test_codigo_da_situacao(self):
        casos = {"Eleito": "e", "Eleito por QP": "e", "2º turno": "2", "Não eleito": "", "": ""}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(historico.codigo_situacao({"st": texto}), esperado)
        self.assertEqual(historico.codigo_situacao({}), "")

    def test_no_maximo_doze_candidatos_os_mais_votados(self):
        candidatos = [(str(10 + i), f"Candidato {i}", "XYZ") for i in range(15)]
        ponto, nomes = historico.ponto_de(tse(list(range(100, 115)), candidatos=candidatos))
        self.assertEqual(len(ponto["placar"]), historico.MAX_CANDIDATOS)
        self.assertEqual(ponto["placar"][0][1], 114)
        self.assertEqual(min(linha[1] for linha in ponto["placar"]), 103)
        self.assertEqual(len(nomes), historico.MAX_CANDIDATOS)

    def test_estado_zerado(self):
        ponto, _ = historico.ponto_de(tse([0, 0], apuradas=0, dt="", ht=""))
        self.assertEqual(ponto["totalizacao"], "")
        self.assertTrue(historico.zerado(ponto))
        self.assertFalse(historico.zerado(historico.ponto_de(tse([1, 0]))[0]))

    def test_situacoes_no_ponto(self):
        dados = tse([300, 600], final=True, situacoes={"22": "2º turno", "13": "Eleito"})
        ponto, _ = historico.ponto_de(dados)
        self.assertEqual([linha[3] for linha in ponto["placar"]], ["2", "e"])
        self.assertTrue(ponto["final"])


class Reduzir(unittest.TestCase):
    def test_pouco_item_vai_inteiro(self):
        self.assertEqual(historico.reduzir([1, 2, 3], 5), [1, 2, 3])

    def test_mantem_primeiro_e_ultimo_e_espalha_por_igual(self):
        for total in (121, 300, 600, 1000):
            itens = list(range(total))
            with self.subTest(total=total):
                reduzido = historico.reduzir(itens, 120)
                self.assertEqual(len(reduzido), 120)
                self.assertEqual((reduzido[0], reduzido[-1]), (0, total - 1))
                self.assertEqual(sorted(set(reduzido)), reduzido)  # crescente e sem repetição
                saltos = {b - a for a, b in zip(reduzido, reduzido[1:])}
                self.assertLessEqual(max(saltos) - min(saltos), 1)

    def test_maximo_dois(self):
        self.assertEqual(historico.reduzir(list(range(50)), 2), [0, 49])


class Registro(unittest.TestCase):
    def test_so_guarda_quando_algo_mudou(self):
        h = Historico()
        self.assertTrue(h.registrar(CHAVE, tse([300, 600])))
        self.assertFalse(h.registrar(CHAVE, tse([300, 600])))  # o mesmo arquivo, de novo
        self.assertTrue(h.registrar(CHAVE, tse([310, 600])))   # votos
        self.assertTrue(h.registrar(CHAVE, tse([310, 600], apuradas=260)))  # seções
        self.assertTrue(h.registrar(CHAVE, tse([310, 600], apuradas=260, ht="20:01:00")))  # horário
        self.assertEqual(len(h.consultar(CHAVE)["pontos"]), 4)

    def test_mudar_so_a_situacao_tambem_conta(self):
        h = Historico()
        h.registrar(CHAVE, tse([300, 600]))
        self.assertTrue(h.registrar(CHAVE, tse([300, 600], situacoes={"22": "Eleito"})))

    def test_zerado_e_guardado_como_origem(self):
        h = Historico()
        self.assertTrue(h.registrar(CHAVE, tse([0, 0], apuradas=0, dt="", ht="")))
        h.registrar(CHAVE, tse([100, 90], apuradas=10))
        pontos = h.consultar(CHAVE)["pontos"]
        self.assertTrue(historico.zerado(pontos[0]))
        self.assertFalse(historico.zerado(pontos[1]))

    def test_so_presidente_governador_e_senador(self):
        h = Historico()
        for cargo in ("deputado-federal", "deputado-estadual", "deputado-distrital"):
            self.assertFalse(h.registrar(("simulado", cargo, "sp", 1, ""), tse([1, 2])))
            self.assertEqual(h.consultar(("simulado", cargo, "sp", 1, ""))["pontos"], [])
        for cargo in historico.CARGOS:
            self.assertTrue(h.registrar(("simulado", cargo, "sp", 1, ""), tse([1, 2])))

    def test_arquivo_fora_do_formato_nao_derruba(self):
        self.assertFalse(Historico().registrar(CHAVE, {"s": {}}))
        self.assertFalse(Historico().registrar(CHAVE, None))

    def test_selecoes_diferentes_sao_series_diferentes(self):
        h = Historico()
        h.registrar(CHAVE, tse([1, 2]))
        h.registrar(("simulado", "presidente", "sp", 1, ""), tse([3, 4]))
        h.registrar(("simulado", "presidente", "sp", 1, "62910"), tse([5, 6]))
        h.registrar(("simulado", "presidente", "br", 2, ""), tse([7, 8]))
        h.registrar(("oficial", "presidente", "br", 1, ""), tse([9, 10]))
        for chave, votos in ((CHAVE, 2), (("simulado", "presidente", "sp", 1, ""), 4), (("simulado", "presidente", "sp", 1, "62910"), 6),
                             (("simulado", "presidente", "br", 2, ""), 8), (("oficial", "presidente", "br", 1, ""), 10)):
            pontos = h.consultar(chave)["pontos"]
            self.assertEqual((len(pontos), pontos[0]["placar"][0][1]), (1, votos))

    def test_candidatos_da_resposta_trazem_nome_e_partido(self):
        h = Historico()
        h.registrar(CHAVE, tse([300, 600]))
        self.assertEqual(h.consultar(CHAVE)["candidatos"], [
            {"numero": "22", "nome": "BRUNO CASTRO", "partido": "PL"},
            {"numero": "13", "nome": "ANA LIMA", "partido": "PT"},
        ])

    def test_candidato_que_saiu_do_top_continua_com_nome(self):
        h = Historico()
        candidatos = [(str(10 + i), f"Candidato {i}", "XYZ") for i in range(13)]
        h.registrar(CHAVE, tse([101] + list(range(102, 113)) + [100], candidatos=candidatos))  # o 0 é o 12º, o 12 fica de fora
        h.registrar(CHAVE, tse([99] + list(range(102, 113)) + [100], candidatos=candidatos))   # agora o 0 cai e o 12 entra
        numeros = [c["numero"] for c in h.consultar(CHAVE)["candidatos"]]
        self.assertEqual((numeros[-1], len(numeros)), ("10", 13))  # quem saiu do top 12 fica no fim, com o nome


class Limites(unittest.TestCase):
    def test_pontos_por_serie(self):
        h = Historico()
        with mock.patch.object(historico, "MAX_PONTOS", 5):
            for i in range(12):
                h.registrar(CHAVE, tse([100 + i, 50], apuradas=i))
        pontos = h.consultar(CHAVE)["pontos"]
        self.assertEqual(len(pontos), 5)
        self.assertEqual([p["apuradas"] for p in pontos], [7, 8, 9, 10, 11])  # ficam os mais recentes

    def test_series_descarta_a_menos_usada_recentemente(self):
        h = Historico()
        chave = lambda uf: ("simulado", "governador", uf, 1, "")
        with mock.patch.object(historico, "MAX_SERIES", 3):
            for uf in ("ac", "al", "am"):
                h.registrar(chave(uf), tse([1, 2]))
            h.consultar(chave("ac"))  # ler também conta como uso
            h.registrar(chave("ba"), tse([1, 2]))
        vivas = [uf for uf in ("ac", "al", "am", "ba") if h.consultar(chave(uf))["pontos"]]
        self.assertEqual(vivas, ["ac", "am", "ba"])

    def test_limites_de_verdade_cabem_na_memoria(self):
        self.assertEqual((historico.MAX_PONTOS, historico.MAX_SERIES), (600, 120))

    def test_resposta_reduzida_a_cento_e_vinte_pontos(self):
        h = Historico()
        for i in range(300):
            h.registrar(CHAVE, tse([100 + i, 50], apuradas=i, ht=f"20:{i // 60:02d}:{i % 60:02d}"))
        pontos = h.consultar(CHAVE)["pontos"]
        self.assertEqual(len(pontos), historico.MAX_PONTOS_API)
        self.assertEqual((pontos[0]["apuradas"], pontos[-1]["apuradas"]), (0, 299))


class Persistencia(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = os.path.join(self.pasta.name, historico.ARQUIVO)

    def alimentar(self, h, n=3):
        for i in range(n):
            h.registrar(CHAVE, tse([100 + i, 50], apuradas=10 * i))

    def test_sem_pasta_nao_cria_arquivo(self):
        self.alimentar(Historico())
        self.assertEqual(os.listdir(self.pasta.name), [])

    def test_sobrevive_a_reinicio(self):
        antes = Historico(self.pasta.name)
        self.alimentar(antes)
        depois = Historico(self.pasta.name)
        self.assertEqual(depois.consultar(CHAVE), antes.consultar(CHAVE))
        self.assertEqual(len(depois.consultar(CHAVE)["pontos"]), 3)
        self.assertFalse(depois.registrar(CHAVE, tse([102, 50], apuradas=20)))  # o último ponto já era esse

    def test_cria_a_pasta_se_nao_existir(self):
        sub = os.path.join(self.pasta.name, "a", "b")
        self.alimentar(Historico(sub))
        self.assertTrue(os.path.exists(os.path.join(sub, historico.ARQUIVO)))

    def test_so_grava_nomes_novos(self):
        self.alimentar(Historico(self.pasta.name))
        with open(self.arquivo, encoding="utf-8") as arquivo:
            registros = [json.loads(linha) for linha in arquivo]
        self.assertEqual([bool(r["n"]) for r in registros], [True, False, False])

    def test_linhas_corrompidas_sao_ignoradas(self):
        h = Historico(self.pasta.name)
        self.alimentar(h, 2)
        ponto = h.consultar(CHAVE)["pontos"][0]
        lixo = [
            "isto não é json",
            "[1, 2, 3]",
            "{}",
            json.dumps({"k": list(CHAVE), "p": {"percentual": "x"}}),
            json.dumps({"k": ["oficial", "deputado-federal", "sp", 1, ""], "p": ponto}),
            json.dumps({"k": list(CHAVE), "p": ponto, "n": {"13": "errado"}}),
            json.dumps({"k": list(CHAVE), "p": dict(ponto, final="talvez")}),
            json.dumps({"k": list(CHAVE), "p": dict(ponto, intruso=1)}),
        ]
        with open(self.arquivo, "ab") as arquivo:
            arquivo.write(b"\xff\xfe nem utf-8\n")
            arquivo.write(("\n".join(lixo) + "\n").encode())
        depois = Historico(self.pasta.name)
        self.assertEqual(len(depois.consultar(CHAVE)["pontos"]), 2)

    def test_ultima_linha_cortada_nao_estraga_a_proxima(self):
        h = Historico(self.pasta.name)
        self.alimentar(h, 2)
        with open(self.arquivo, "ab") as arquivo:
            arquivo.write(b'{"k":["simulado","presidente","br",1,""],"p":{"totalizacao":"21/10')  # queda de energia
        depois = Historico(self.pasta.name)
        self.assertEqual(len(depois.consultar(CHAVE)["pontos"]), 2)
        depois.registrar(CHAVE, tse([500, 50], apuradas=90))
        terceira = Historico(self.pasta.name)
        self.assertEqual(len(terceira.consultar(CHAVE)["pontos"]), 3)

    def test_pasta_impossivel_avisa_uma_vez_e_segue_em_memoria(self):
        arquivo_no_lugar_da_pasta = os.path.join(self.pasta.name, "ocupado")
        open(arquivo_no_lugar_da_pasta, "w").close()
        erro = io.StringIO()
        with redirect_stderr(erro):
            h = Historico(os.path.join(arquivo_no_lugar_da_pasta, "dentro"))
            self.alimentar(h, 4)
        self.assertEqual(len(h.consultar(CHAVE)["pontos"]), 4)
        self.assertEqual(erro.getvalue().count("Histórico"), 1)

    def test_erro_de_gravacao_avisa_uma_vez_e_segue_em_memoria(self):
        h = Historico(self.pasta.name)
        erro = io.StringIO()
        with redirect_stderr(erro), mock.patch("historico.open", side_effect=OSError("disco cheio"), create=True) as abrir:
            self.alimentar(h, 4)
        self.assertEqual(len(h.consultar(CHAVE)["pontos"]), 4)
        self.assertEqual(erro.getvalue().count("Histórico"), 1)
        self.assertIn("disco cheio", erro.getvalue())
        self.assertEqual(abrir.call_count, 1)  # depois do primeiro erro nem tenta mais

    def test_erro_de_leitura_avisa_e_segue(self):
        Historico(self.pasta.name).registrar(CHAVE, tse([1, 2]))
        erro = io.StringIO()
        with redirect_stderr(erro), mock.patch("historico.open", side_effect=PermissionError("sem permissão"), create=True):
            h = Historico(self.pasta.name)
        self.assertEqual(h.consultar(CHAVE)["pontos"], [])
        self.assertEqual(erro.getvalue().count("Histórico"), 1)

    def test_arquivo_grande_demais_para_de_gravar(self):
        erro = io.StringIO()
        with redirect_stderr(erro), mock.patch.object(historico, "MAX_ARQUIVO", 400):
            h = Historico(self.pasta.name)
            self.alimentar(h, 6)
        self.assertLess(os.path.getsize(self.arquivo), 1200)
        self.assertEqual(len(h.consultar(CHAVE)["pontos"]), 6)
        self.assertEqual(erro.getvalue().count("grande demais"), 1)

    def test_o_limite_vale_tambem_na_carga(self):
        h = Historico(self.pasta.name)
        self.alimentar(h, 8)
        with mock.patch.object(historico, "MAX_PONTOS", 3):
            depois = Historico(self.pasta.name)
        self.assertEqual([p["apuradas"] for p in depois.consultar(CHAVE)["pontos"]], [50, 60, 70])


class RotaDoHistorico(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(servidor, "HISTORICO", Historico())
        patch.start()
        self.addCleanup(patch.stop)

    def resultado(self, dados, **consulta):
        padrao = {"ambiente": ["simulado"], "cargo": ["presidente"], "uf": ["br"]}
        padrao.update({k: [v] for k, v in consulta.items()})
        with mock.patch.object(servidor.CACHE, "obter", return_value=(dados, 200, 0)):
            return servidor.resultado(padrao), padrao

    def test_resultado_registra_e_a_api_devolve(self):
        (status, _), consulta = self.resultado(tse([300, 600]))
        self.assertEqual(status, 200)
        self.resultado(tse([310, 650], apuradas=300))
        status, corpo = servidor.historico_da_selecao(consulta)
        self.assertEqual(status, 200)
        self.assertEqual([p["apuradas"] for p in corpo["pontos"]], [250, 300])
        self.assertEqual([c["numero"] for c in corpo["candidatos"]], ["22", "13"])

    def test_cada_ponto_traz_tudo_que_o_replay_usa(self):
        (_, _), consulta = self.resultado(tse([300, 600], final=True, situacoes={"22": "Eleito"}))
        _, corpo = servidor.historico_da_selecao(consulta)
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
        config = contador.url_municipios("simulado", "governador", 1)
        cidade = contador.montar_url("simulado", "governador", "sp", 1, municipio="62910")
        respostas = {config: (CONFIG_MUNICIPIOS, 200, 0), cidade: (tse([300, 600]), 200, 0)}
        da_cidade = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"], "municipio": ["62910"]}
        da_uf = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"]}
        with mock.patch.object(servidor.CACHE, "obter", side_effect=lambda url, ttl=servidor.INTERVALO_TSE: respostas[url]):
            self.assertEqual(servidor.resultado(da_cidade)[0], 200)
        self.assertEqual(len(servidor.historico_da_selecao(da_cidade)[1]["pontos"]), 1)
        self.assertEqual(servidor.historico_da_selecao(da_uf)[1]["pontos"], [])

    def test_serie_vazia_nao_e_erro(self):
        status, corpo = servidor.historico_da_selecao({"ambiente": ["simulado"]})
        self.assertEqual((status, corpo), (200, {"candidatos": [], "pontos": []}))

    def test_cargos_sem_historico_dao_400(self):
        for consulta in (
            {"cargo": ["deputado-federal"], "uf": ["sp"]},
            {"cargo": ["deputado-estadual"], "uf": ["sp"]},
            {"cargo": ["deputado-distrital"], "uf": ["df"]},
        ):
            with self.subTest(consulta=consulta):
                self.assertEqual(servidor.historico_da_selecao(consulta)[0], 400)

    def test_deputado_nao_registra(self):
        self.resultado(tse([300, 600]), cargo="deputado-federal", uf="sp")
        self.assertEqual(servidor.HISTORICO.consultar(("simulado", "deputado-federal", "sp", 1, "")), {"candidatos": [], "pontos": []})

    def test_parametros_invalidos_dao_400(self):
        for consulta in (
            {"cargo": ["x"]}, {"uf": ["sp"], "cargo": ["senador"], "turno": ["2"]}, {"ambiente": ["../x"]},
            {"turno": ["3"]}, {"uf": ["br"], "municipio": ["62910"]}, {"uf": ["sp"], "municipio": ["abc"]},
            {"uf": ["sp"], "municipio": ["../../"]},
        ):
            with self.subTest(consulta=consulta):
                self.assertEqual(servidor.historico_da_selecao(consulta)[0], 400)

    def test_a_api_nunca_toca_o_tse(self):
        recusa = AssertionError("o histórico não pode consultar o TSE")
        with mock.patch.object(contador, "buscar", side_effect=recusa), mock.patch.object(servidor.CACHE, "obter", side_effect=recusa):
            for consulta in ({}, {"uf": ["sp"], "cargo": ["governador"], "municipio": ["62910"]}, {"cargo": ["senador"], "uf": ["mg"], "turno": ["1"]}):
                self.assertEqual(servidor.historico_da_selecao(consulta)[0], 200)

    def test_rota_registrada_na_tabela(self):
        self.assertIs(servidor.ROTAS_API["/api/historico"], servidor.historico_da_selecao)
        self.assertIs(servidor.ROTAS_API["/api/resultado"], servidor.resultado)

if __name__ == "__main__":
    unittest.main()
