import time
import unittest
from unittest import mock

import contador
import mapa
import servidor

AGORA = 1_000_000.0


def arquivo(candidatos, final=False, secoes=(1000, 500)):
    """Arquivo do TSE só com o que o mapa lê. candidatos: (número, nome, partido, votos, "pct", situação)."""
    total, apuradas = secoes
    return {
        "tf": "s" if final else "n",
        "s": {"ts": str(total), "st": str(apuradas), "pst": f"{100 * apuradas / total:.2f}".replace(".", ",")},
        "carg": [{"agr": [
            {"par": [{"sg": partido, "cand": [
                {"n": numero, "nm": nome.upper(), "nmu": nome.upper(), "vap": str(votos), "pvap": pct, "st": situacao}
            ]}]}
            for numero, nome, partido, votos, pct, situacao in candidatos
        ]}],
    }


DOIS = [("13", "Ana", "PT", 600, "60,00", ""), ("22", "Bia", "PL", 400, "40,00", "")]


class Fonte:
    """Faz de conta de CACHE.obter: responde por URL e anota o que foi pedido (404 para o resto)."""

    def __init__(self, respostas=None):
        self.respostas, self.pedidos = respostas or {}, []

    def __call__(self, url, ttl=None):
        self.pedidos.append(url)
        return self.respostas.get(url, (None, 404, 0))


def url(cargo, uf, turno=1, ambiente="oficial"):
    return contador.montar_url(ambiente, cargo, uf, turno)


def fonte_com(cargo, turno, dados_por_uf, br=None):
    respostas = {url(cargo, uf, turno): (dados, 200, AGORA) for uf, dados in dados_por_uf.items()}
    if br is not None:
        respostas[url(cargo, "br", turno)] = (br, 200, AGORA)
    return Fonte(respostas)


class SituacaoDoCandidato(unittest.TestCase):
    def test_marcas_do_tse(self):
        for texto, esperado in (
            ("Eleito", "eleito"), ("Não eleito", "nao_eleito"), ("2º turno", "segundo_turno"),
            ("2° turno", "segundo_turno"), ("2o turno", "segundo_turno"), ("", ""), (None, ""),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(mapa.situacao_do_candidato({"st": texto}), esperado)
        self.assertEqual(mapa.situacao_do_candidato({}), "")


class ResumirUf(unittest.TestCase):
    def test_lider_segundo_e_margem(self):
        resumo = mapa.resumir_uf(arquivo(DOIS))
        self.assertEqual(resumo["situacao"], "lider")
        self.assertEqual((resumo["lider"]["partido"], resumo["segundo"]["partido"]), ("PT", "PL"))
        self.assertEqual((resumo["margem"], resumo["margem_votos"]), (20.0, 200))
        self.assertEqual(resumo["secoes"], {"total": 1000, "apuradas": 500, "percentual": 50.0})
        self.assertFalse(resumo["final"])
        self.assertNotIn("votos", resumo)

    def test_ordem_do_arquivo_nao_importa(self):
        resumo = mapa.resumir_uf(arquivo(DOIS[::-1]))
        self.assertEqual(resumo["lider"]["numero"], "13")

    def test_votos_zerados_nao_tem_lider(self):
        zerado = [("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")]
        resumo = mapa.resumir_uf(arquivo(zerado, secoes=(1000, 0)))
        self.assertEqual(resumo["situacao"], "zerado")
        self.assertIsNone(resumo["lider"])
        self.assertIsNone(resumo["segundo"])

    def test_zero_secoes_apuradas_nao_tem_lider_mesmo_com_voto(self):
        self.assertEqual(mapa.resumir_uf(arquivo(DOIS, secoes=(1000, 0)))["situacao"], "zerado")

    def test_empate_no_topo_nao_escolhe_lider(self):
        empate = [("13", "Ana", "PT", 500, "50,00", ""), ("22", "Bia", "PL", 500, "50,00", "")]
        resumo = mapa.resumir_uf(arquivo(empate))
        self.assertEqual(resumo["situacao"], "empate")
        self.assertIsNone(resumo["lider"])
        self.assertEqual(sorted(c["numero"] for c in resumo["empatados"]), ["13", "22"])
        self.assertEqual(resumo["margem"], 0.0)

    def test_empate_fora_do_topo_nao_atrapalha(self):
        tres = DOIS + [("55", "Caio", "PSD", 400, "40,00", "")]
        self.assertEqual(mapa.resumir_uf(arquivo(tres))["situacao"], "lider")

    def test_um_candidato_so(self):
        resumo = mapa.resumir_uf(arquivo([("13", "Ana", "PT", 600, "100,00", "")]))
        self.assertEqual(resumo["lider"]["partido"], "PT")
        self.assertIsNone(resumo["segundo"])
        self.assertEqual(resumo["margem"], 100.0)

    def test_eleito_e_segundo_turno(self):
        eleito = [("13", "Ana", "PT", 600, "60,00", "Eleito"), ("22", "Bia", "PL", 400, "40,00", "Não eleito")]
        resumo = mapa.resumir_uf(arquivo(eleito, final=True))
        self.assertTrue(resumo["lider"]["eleito"] and resumo["final"])
        vao = [("13", "Ana", "PT", 450, "45,00", "2º turno"), ("22", "Bia", "PL", 400, "40,00", "2º turno")]
        resumo = mapa.resumir_uf(arquivo(vao + [("55", "Caio", "PSD", 150, "15,00", "Não eleito")]))
        self.assertTrue(resumo["lider"]["segundo_turno"])
        self.assertFalse(resumo["lider"]["eleito"])

    def test_votos_de_todos_quando_pedido(self):
        resumo = mapa.resumir_uf(arquivo(DOIS + [("55", "Caio", "PSD", 10, "1,00", "")]), com_votos=True)
        self.assertEqual(resumo["votos"], {"13": 600, "22": 400, "55": 10})

    def test_arquivo_real_zerado_do_segundo_turno(self):
        # como o TSE publica antes da apuração: votos "0", pvap "0,00", st vazio e sem dvt
        zerado = {
            "tf": "n", "dt": "", "ht": "", "s": {"ts": "499248", "st": "0", "pst": "0,00"},
            "carg": [{"agr": [{"par": [{"sg": "PL", "cand": [{"n": "22", "nm": "FLAVIO", "nmu": "FLAVIO", "vap": "0", "pvap": "0,00", "st": ""}]}]},
                              {"par": [{"sg": "PT", "cand": [{"n": "13", "nm": "LULA", "nmu": "LULA", "vap": "0", "pvap": "0,00", "st": ""}]}]}]}],
        }
        self.assertEqual(mapa.resumir_uf(zerado)["situacao"], "zerado")


class Consultar(unittest.TestCase):
    def urls(self, quantas=8):
        return {f"u{i}": f"url{i}" for i in range(quantas)}

    def test_sentinela_sem_dados_poupa_as_outras(self):
        fonte = Fonte()
        resultados = mapa.consultar(fonte, self.urls(), pausa=0)
        self.assertEqual(fonte.pedidos, ["url0"])
        self.assertEqual(list(resultados), ["u0"])

    def test_sentinela_bloqueada_poupa_as_outras(self):
        fonte = Fonte({"url0": (None, 429, 0)})
        mapa.consultar(fonte, self.urls(), pausa=0)
        self.assertEqual(fonte.pedidos, ["url0"])

    def test_sentinela_boa_libera_todas(self):
        fonte = Fonte({f"url{i}": ({"x": i}, 200, AGORA) for i in range(8)})
        resultados = mapa.consultar(fonte, self.urls(), pausa=0)
        self.assertEqual(sorted(resultados), sorted(self.urls()))
        self.assertEqual(sorted(fonte.pedidos), sorted(self.urls().values()))

    def test_para_depois_de_alguns_404(self):
        fonte = Fonte({"url0": ({"x": 0}, 200, AGORA)})  # o resto dá 404
        with mock.patch.object(mapa, "TRABALHADORES", 1):
            mapa.consultar(fonte, self.urls(20), pausa=0)
        self.assertEqual(len(fonte.pedidos), 1 + mapa.LIMITE_404)

    def test_para_ao_ver_bloqueio(self):
        fonte = Fonte({"url0": ({"x": 0}, 200, AGORA), "url1": (None, 429, 0)})
        with mock.patch.object(mapa, "TRABALHADORES", 1):
            mapa.consultar(fonte, self.urls(20), pausa=0)
        self.assertEqual(fonte.pedidos, ["url0", "url1"])

    def test_erro_numa_uf_nao_derruba_as_outras(self):
        def obter(url, ttl=None):
            if url == "url3":
                raise OSError("conexão caiu")
            return {"x": url}, 200, AGORA

        resultados = mapa.consultar(obter, self.urls(), pausa=0)
        self.assertEqual(resultados["u3"][0], None)
        self.assertEqual(resultados["u4"][0], {"x": "url4"})

    def test_nao_espera_alem_do_prazo(self):
        def obter(url, ttl=None):
            if url != "url0":
                time.sleep(0.6)
            return {"x": url}, 200, AGORA

        inicio = time.monotonic()
        resultados = mapa.consultar(obter, self.urls(4), pausa=0, prazo=0.1)
        self.assertLess(time.monotonic() - inicio, 0.5)
        self.assertEqual(list(resultados), ["u0"])

    def test_pausa_so_depois_do_que_foi_a_rede(self):
        def devagar(url, ttl=None):  # espera ocupada: `time.sleep` está trocado neste teste
            fim = time.monotonic() + 0.02
            while time.monotonic() < fim:
                pass
            return {"x": url}, 200, AGORA

        rapido = lambda url, ttl=None: ({"x": url}, 200, AGORA)
        with mock.patch.object(mapa.time, "sleep") as dormir:
            mapa.consultar(rapido, self.urls(5), pausa=0.5)
            dormir.assert_not_called()  # veio do cache: sem pausa
            mapa.consultar(devagar, self.urls(5), pausa=0.5)
        self.assertEqual(dormir.call_args_list, [mock.call(0.5)] * 4)  # as 4 que não eram a sentinela

    def test_pausa_quando_o_cache_acabou_de_renovar_mesmo_sendo_instantaneo(self):
        renovado = lambda url, ttl=None: ({"x": url}, 200, time.time())  # TSE de mentira: responde na hora
        with mock.patch.object(mapa.time, "sleep") as dormir:
            mapa.consultar(renovado, self.urls(5), pausa=0.5)
        self.assertEqual(dormir.call_count, 4)


class ResumoPorUf(unittest.TestCase):
    def uf_com(self, partido_lider, pct=60, final=False):
        outro = "PL" if partido_lider == "PT" else "PT"
        return arquivo(
            [("13", "Ana", partido_lider, 600, f"{pct},00", ""), ("22", "Bia", outro, 400, f"{100 - pct},00", "")],
            final=final,
        )

    def pedir(self, fonte, cargo="presidente", turno=1):
        return mapa.resumo_por_uf(fonte, "oficial", cargo, turno, pausa=0, agora=lambda: AGORA + 3)

    def test_presidente_comeca_pelo_arquivo_nacional(self):
        fonte = Fonte()
        corpo, falha = self.pedir(fonte)
        self.assertIsNone(corpo)
        self.assertEqual(falha[0], 404)
        self.assertEqual(fonte.pedidos, [url("presidente", "br")])  # nenhuma UF foi consultada

    def test_presidente_pede_nacional_e_as_27_ufs(self):
        fonte = fonte_com("presidente", 1, {uf: self.uf_com("PT") for uf in contador.UFS}, br=self.uf_com("PT"))
        fonte.respostas[url("presidente", "zz")] = (arquivo([("13", "Ana", "PT", 100, "25,00", ""), ("22", "Bia", "PL", 300, "75,00", "")]), 200, AGORA)
        corpo, falha = self.pedir(fonte)
        self.assertIsNone(falha)
        self.assertEqual(len(fonte.pedidos), 29)
        self.assertEqual(fonte.pedidos[0], url("presidente", "br"))
        self.assertIn(url("presidente", "zz"), fonte.pedidos)
        self.assertEqual(corpo["exterior"]["lider"]["partido"], "PL")
        self.assertEqual(list(corpo["ufs"]), list(contador.UFS))
        self.assertEqual(corpo["ufs"]["sp"]["lider"]["partido"], "PT")
        self.assertEqual(corpo["ufs"]["sp"]["votos"], {"13": 600, "22": 400})
        self.assertEqual(corpo["partidos"], ["PL", "PT"])
        self.assertEqual([c["numero"] for c in corpo["candidatos"]], ["13", "22"])
        self.assertEqual(corpo["candidatos"][0], {"numero": "13", "nome": "ANA", "partido": "PT", "votos": 600 * 27 + 100})
        self.assertFalse(corpo["final"])
        self.assertNotIn("aviso", corpo)
        self.assertEqual(corpo["idade_s"], 3)

    def test_final_so_quando_todas_as_ufs_estao_finais(self):
        dados = {uf: self.uf_com("PT", final=True) for uf in contador.UFS}
        corpo, _ = self.pedir(fonte_com("presidente", 1, dados, br=self.uf_com("PT", final=True)))
        self.assertTrue(corpo["final"])
        dados["ac"] = self.uf_com("PT", final=False)
        corpo, _ = self.pedir(fonte_com("presidente", 1, dados, br=self.uf_com("PT", final=True)))
        self.assertFalse(corpo["final"])

    def test_segundo_turno_zerado_nao_inventa_lider(self):
        zerado = arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")], secoes=(1000, 0))
        fonte = fonte_com("presidente", 2, {uf: zerado for uf in contador.UFS}, br=zerado)
        corpo, _ = self.pedir(fonte, turno=2)
        self.assertEqual({u["situacao"] for u in corpo["ufs"].values()}, {"zerado"})
        self.assertEqual(corpo["partidos"], [])
        self.assertFalse(corpo["final"])

    def test_uf_sem_dados_nao_derruba_o_mapa(self):
        dados = {uf: self.uf_com("PT") for uf in contador.UFS if uf != "rj"}
        corpo, falha = self.pedir(fonte_com("presidente", 1, dados, br=self.uf_com("PT")))
        self.assertIsNone(falha)
        self.assertEqual(corpo["ufs"]["rj"], {"situacao": "sem_dados"})
        self.assertEqual(corpo["ufs"]["sp"]["situacao"], "lider")
        self.assertIn("1 estado ", corpo["aviso"])
        self.assertFalse(corpo["final"])

    def test_aviso_quando_o_dado_esta_velho(self):
        dados = {uf: self.uf_com("PT") for uf in contador.UFS}
        fonte = fonte_com("presidente", 1, dados, br=self.uf_com("PT"))
        corpo, _ = mapa.resumo_por_uf(fonte, "oficial", "presidente", 1, pausa=0, agora=lambda: AGORA + 300)
        self.assertIn("últimos dados", corpo["aviso"])

    def test_governador_primeiro_turno_nao_consulta_nacional(self):
        fonte = fonte_com("governador", 1, {uf: self.uf_com("PL") for uf in contador.UFS})
        corpo, _ = self.pedir(fonte, cargo="governador")
        self.assertEqual(len(fonte.pedidos), 27)
        self.assertNotIn(url("governador", "br"), fonte.pedidos)
        self.assertNotIn("candidatos", corpo)  # cada UF tem os seus candidatos
        self.assertNotIn("votos", corpo["ufs"]["sp"])

    def test_governador_segundo_turno_so_consulta_quem_foi_ao_segundo(self):
        vao = arquivo([("13", "Ana", "PT", 450, "45,00", "2º turno"), ("22", "Bia", "PL", 400, "40,00", "2º turno")], final=True)
        ganhou = arquivo([("10", "Cris", "REPUBLICANOS", 700, "70,00", "Eleito"), ("13", "Ana", "PT", 300, "30,00", "Não eleito")], final=True)
        primeiro = {uf: ganhou for uf in contador.UFS}
        primeiro.update(mg=vao, rj=vao)
        respostas = {url("governador", uf, 1): (dados, 200, AGORA) for uf, dados in primeiro.items()}
        respostas[url("governador", "mg", 2)] = (self.uf_com("PT"), 200, AGORA)
        respostas[url("governador", "rj", 2)] = (self.uf_com("PL"), 200, AGORA)
        fonte = Fonte(respostas)
        corpo, falha = self.pedir(fonte, cargo="governador", turno=2)
        self.assertIsNone(falha)
        segundo_turno = [p for p in fonte.pedidos if "/6260/" in p]
        self.assertEqual(sorted(segundo_turno), sorted([url("governador", "mg", 2), url("governador", "rj", 2)]))
        self.assertEqual(corpo["ufs"]["mg"]["lider"]["partido"], "PT")
        self.assertEqual(corpo["ufs"]["sp"]["situacao"], "sem_segundo_turno")
        self.assertEqual(corpo["ufs"]["sp"]["primeiro_turno"]["partido"], "REPUBLICANOS")
        self.assertTrue(corpo["ufs"]["sp"]["primeiro_turno"]["eleito"])

    def test_governador_segundo_turno_sem_primeiro_turno_nao_consulta_ninguem(self):
        fonte = Fonte()
        corpo, falha = self.pedir(fonte, cargo="governador", turno=2)
        self.assertIsNone(corpo)
        self.assertEqual(falha[0], 404)
        self.assertEqual(len(fonte.pedidos), 1)
        self.assertFalse([p for p in fonte.pedidos if "/6260/" in p])

    def test_governador_segundo_turno_uf_sem_primeiro_turno_nao_e_consultada(self):
        vao = arquivo([("13", "Ana", "PT", 450, "45,00", "2º turno"), ("22", "Bia", "PL", 400, "40,00", "2º turno")], final=True)
        primeiro = {uf: vao for uf in contador.UFS if uf != "ba"}  # a Bahia não tem o 1º turno agora
        respostas = {url("governador", uf, 1): (dados, 200, AGORA) for uf, dados in primeiro.items()}
        respostas.update({url("governador", uf, 2): (self.uf_com("PT"), 200, AGORA) for uf in contador.UFS})
        fonte = Fonte(respostas)
        corpo, _ = self.pedir(fonte, cargo="governador", turno=2)
        self.assertNotIn(url("governador", "ba", 2), fonte.pedidos)
        self.assertEqual(corpo["ufs"]["ba"], {"situacao": "sem_dados"})

    def test_governador_segundo_turno_ainda_nao_publicado_gasta_um_404(self):
        vao = arquivo([("13", "Ana", "PT", 450, "45,00", "2º turno"), ("22", "Bia", "PL", 400, "40,00", "2º turno")], final=True)
        respostas = {url("governador", uf, 1): (vao, 200, AGORA) for uf in contador.UFS}
        fonte = Fonte(respostas)  # nenhum arquivo do 2º turno existe ainda
        corpo, falha = self.pedir(fonte, cargo="governador", turno=2)
        self.assertIsNone(corpo)
        self.assertEqual(falha[0], 404)
        self.assertEqual(len([p for p in fonte.pedidos if "/6260/" in p]), 1)


class RotaMapa(unittest.TestCase):
    def setUp(self):
        servidor._PRONTAS.clear()
        self.addCleanup(servidor._PRONTAS.clear)

    def obter(self, respostas):
        return mock.patch.object(servidor.CACHE, "obter", side_effect=lambda url, ttl=None: respostas.get(url, (None, 404, 0)))

    def test_so_presidente_e_governador(self):
        for consulta in ({"cargo": ["senador"]}, {"cargo": ["deputado-federal"]}, {"cargo": ["x"]}, {"turno": ["3"]},
                         {"ambiente": ["https://exemplo.com"]}, {"cargo": ["presidente"], "turno": ["1;2"]}):
            with self.subTest(consulta=consulta):
                with mock.patch.object(servidor.CACHE, "obter") as obter:
                    self.assertEqual(servidor.mapa_por_uf(consulta)[0], 400)
                obter.assert_not_called()

    def test_uf_do_visitante_e_ignorada(self):
        with self.obter({}):
            self.assertEqual(servidor.mapa_por_uf({"cargo": ["governador"], "uf": ["../etc"]})[0], 404)

    def test_tse_ainda_nao_publicou(self):
        with self.obter({}):
            status, corpo = servidor.mapa_por_uf({})
        self.assertEqual(status, 404)
        self.assertIn("ainda não publicou", corpo["erro"])

    def test_tse_fora_do_ar(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(None, 503, 0)):
            self.assertEqual(servidor.mapa_por_uf({})[0], 503)

    def test_bloqueio_vira_503(self):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(None, 429, 0)):
            self.assertEqual(servidor.mapa_por_uf({})[0], 503)

    def test_resposta_completa(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*contador.UFS, "br", "zz")}
        with self.obter(dados):
            status, corpo = servidor.mapa_por_uf({"cargo": ["presidente"], "turno": ["1"], "ambiente": ["oficial"]})
        self.assertEqual(status, 200)
        self.assertEqual((corpo["cargo"], corpo["turno"], corpo["ambiente"]), ("presidente", 1, "oficial"))
        self.assertEqual(len(corpo["ufs"]), 27)

    def test_visitantes_dividem_a_mesma_rodada(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*contador.UFS, "br", "zz")}
        with self.obter(dados) as obter:
            servidor.mapa_por_uf({})
            primeira = obter.call_count
            servidor.mapa_por_uf({})
        self.assertEqual(primeira, 29)
        self.assertEqual(obter.call_count, 29)  # a segunda veio pronta

    def test_selecoes_diferentes_nao_se_misturam(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*contador.UFS, "br", "zz")}
        with self.obter(dados):
            self.assertEqual(servidor.mapa_por_uf({"turno": ["1"]})[0], 200)
            self.assertEqual(servidor.mapa_por_uf({"turno": ["2"]})[0], 404)
            self.assertEqual(servidor.mapa_por_uf({"ambiente": ["simulado"]})[0], 404)

    def test_resposta_pronta_vence(self):
        chamadas = []
        construir = lambda: (chamadas.append(1) or 200, {})
        servidor.lembrar("longa", construir, ttl=100)
        servidor.lembrar("longa", construir, ttl=100)
        self.assertEqual(len(chamadas), 1)
        servidor.lembrar("curta", construir, ttl=0)
        servidor.lembrar("curta", construir, ttl=0)
        self.assertEqual(len(chamadas), 3)


class Disputa(unittest.TestCase):
    TRES = [("13", "Ana", "PT", 500, "50,00", ""), ("22", "Bia", "PL", 300, "30,00", ""), ("55", "Caio", "PSD", 200, "20,00", "")]

    def test_governo_e_entre_o_primeiro_e_o_segundo(self):
        disputa = mapa.resumir_uf(arquivo(self.TRES))["disputa"]
        self.assertEqual([c["numero"] for c in disputa["entre"]], ["13", "22"])
        self.assertEqual((disputa["margem"], disputa["margem_votos"], disputa["situacao"]), (20.0, 200, "apurando"))

    def test_senado_com_duas_vagas_e_entre_o_segundo_e_o_terceiro(self):
        disputa = mapa.resumir_uf(arquivo(self.TRES), vagas=2)["disputa"]
        self.assertEqual([c["numero"] for c in disputa["entre"]], ["22", "55"])
        self.assertEqual((disputa["margem"], disputa["margem_votos"]), (10.0, 100))

    def test_sem_disputa_quando_nao_ha_mais_candidatos_que_vagas(self):
        self.assertIsNone(mapa.resumir_uf(arquivo(DOIS), vagas=2)["disputa"])
        self.assertIsNone(mapa.resumir_uf(arquivo(DOIS[:1]))["disputa"])

    def test_situacoes(self):
        marcar = lambda *marcas: arquivo([(n, nm, pt, v, pc, m) for (n, nm, pt, v, pc, _), m in zip(self.TRES, marcas)])
        casos = {
            "eleito": (marcar("Eleito", "", ""), 1),
            "segundo_turno": (marcar("2º turno", "2º turno", ""), 1),
            "apurando": (marcar("", "", ""), 1),
        }
        for esperado, (dados, vagas) in casos.items():
            with self.subTest(esperado=esperado):
                self.assertEqual(mapa.resumir_uf(dados, vagas=vagas)["disputa"]["situacao"], esperado)
        self.assertEqual(mapa.resumir_uf(marcar("Eleito", "Eleito", ""), vagas=2)["disputa"]["situacao"], "eleito")
        self.assertEqual(mapa.resumir_uf(marcar("Eleito", "", ""), vagas=2)["disputa"]["situacao"], "apurando")

    def test_zerado_nao_tem_situacao_de_disputa(self):
        zerados = arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")])
        self.assertEqual(mapa.resumir_uf(zerados)["disputa"]["situacao"], "zerado")


class SenadoPorUf(unittest.TestCase):
    def test_senador_resume_com_duas_vagas(self):
        dados = arquivo(Disputa.TRES)
        fonte = fonte_com("senador", 1, {uf: dados for uf in contador.UFS})
        corpo, falha = mapa.resumo_por_uf(fonte, "oficial", "senador", 1, pausa=0, agora=lambda: AGORA)
        self.assertIsNone(falha)
        self.assertEqual(len(fonte.pedidos), 27)  # sem arquivo nacional nem exterior
        self.assertNotIn("exterior", corpo)
        self.assertEqual([c["numero"] for c in corpo["ufs"]["sp"]["disputa"]["entre"]], ["22", "55"])


class ExteriorEDisputas(unittest.TestCase):
    def corpo_do_presidente(self, exterior=True):
        fonte = fonte_com("presidente", 1, {uf: arquivo(DOIS) for uf in contador.UFS}, br=arquivo(DOIS))
        if exterior:
            fonte.respostas[url("presidente", "zz")] = (arquivo([("13", "Ana", "PT", 100, "25,00", ""), ("22", "Bia", "PL", 300, "75,00", "")]), 200, AGORA)
        return mapa.resumo_por_uf(fonte, "oficial", "presidente", 1, pausa=0, agora=lambda: AGORA)[0]

    def test_exterior_fora_do_ar_nao_vira_aviso_nem_derruba(self):
        corpo = self.corpo_do_presidente(exterior=False)
        self.assertEqual(corpo["exterior"], {"situacao": "sem_dados"})
        self.assertNotIn("aviso", corpo)
        self.assertEqual(corpo["candidatos"][0]["votos"], 600 * 27)

    def test_disputas_ordenadas_pela_menor_margem_em_votos(self):
        def uf(vencedor, perdedor):
            return arquivo([("13", "Ana", "PT", vencedor, "50,00", ""), ("22", "Bia", "PL", perdedor, "40,00", "")])
        dados = {uf_: arquivo(DOIS[:1]) for uf_ in contador.UFS}  # candidatura única: sem disputa
        dados.update({"sp": uf(500, 490), "rj": uf(500, 100), "mg": uf(500, 499),
                      "ba": arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")])})
        fonte = fonte_com("governador", 1, dados)
        corpo, _ = mapa.resumo_por_uf(fonte, "oficial", "governador", 1, pausa=0, agora=lambda: AGORA)
        lista = mapa.disputas(corpo)["disputas"]
        self.assertEqual([d["uf"] for d in lista], ["mg", "sp", "rj"])  # sem BA (zerada) e sem as de candidato único
        self.assertEqual(lista[0]["margem_votos"], 1)
        self.assertEqual(set(lista[0]), {"uf", "situacao", "entre", "margem", "margem_votos", "secoes", "final"})
        self.assertEqual([d["uf"] for d in mapa.disputas(corpo, limite=2)["disputas"]], ["mg", "sp"])

    def test_disputas_nao_mexem_no_resumo(self):
        corpo = self.corpo_do_presidente()
        antes = repr(corpo)
        mapa.disputas(corpo)
        mapa.regioes(corpo)
        self.assertEqual(repr(corpo), antes)

    def test_regioes_somam_as_ufs_e_o_exterior(self):
        corpo = self.corpo_do_presidente()
        por_nome = {r["regiao"]: r for r in mapa.regioes(corpo)["regioes"]}
        self.assertEqual(list(por_nome), ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"])
        sul = por_nome["Sul"]
        self.assertEqual((sul["ufs_com_dados"], sul["votos"]), (3, 3000))
        self.assertEqual(sul["lider"], {"numero": "13", "nome": "ANA", "partido": "PT", "votos": 1800, "percentual": 60.0})
        self.assertEqual(sul["secoes"], {"total": 3000, "apuradas": 1500, "percentual": 50.0})
        exterior = por_nome["Exterior"]
        self.assertEqual((exterior["lider"]["partido"], exterior["lider"]["percentual"]), ("PL", 75.0))
        self.assertEqual(len(por_nome["Nordeste"]["ufs"]), 9)

    def test_regiao_sem_dados_fica_sem_lider(self):
        corpo = self.corpo_do_presidente(exterior=False)
        exterior = {r["regiao"]: r for r in mapa.regioes(corpo)["regioes"]}["Exterior"]
        self.assertEqual((exterior["lider"], exterior["ufs_com_dados"], exterior["votos"]), (None, 0, 0))
        self.assertEqual(exterior["secoes"]["percentual"], 0.0)
        self.assertEqual(exterior["candidatos"], [])

    def test_regiao_com_apuracao_zerada_nao_inventa_lider(self):
        zerado = arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")], secoes=(1000, 0))
        fonte = fonte_com("presidente", 1, {uf: zerado for uf in contador.UFS}, br=zerado)
        corpo, _ = mapa.resumo_por_uf(fonte, "oficial", "presidente", 1, pausa=0, agora=lambda: AGORA)
        self.assertTrue(all(r["lider"] is None for r in mapa.regioes(corpo)["regioes"]))


class RotasDerivadas(unittest.TestCase):
    def setUp(self):
        servidor._PRONTAS.clear()
        self.addCleanup(servidor._PRONTAS.clear)

    def obter(self, respostas):
        return mock.patch.object(servidor.CACHE, "obter", side_effect=lambda url, ttl=None: respostas.get(url, (None, 404, 0)))

    def test_regioes_e_mapa_dividem_a_mesma_rodada(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*contador.UFS, "br", "zz")}
        with self.obter(dados) as obter:
            self.assertEqual(servidor.mapa_por_uf({})[0], 200)
            status, corpo = servidor.regioes_do_pais({})
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["regioes"]), 6)
        self.assertEqual(obter.call_count, 29)

    def test_regioes_so_do_presidente_mesmo_que_peçam_outro_cargo(self):
        dados = {url("presidente", uf): (arquivo(DOIS), 200, time.time()) for uf in (*contador.UFS, "br", "zz")}
        with self.obter(dados):
            self.assertEqual(servidor.regioes_do_pais({"cargo": ["governador"]})[0], 200)

    def test_disputas_de_governador_e_senador(self):
        for cargo in ("governador", "senador"):
            dados = {url(cargo, uf): (arquivo(Disputa.TRES), 200, time.time()) for uf in contador.UFS}
            with self.subTest(cargo=cargo), self.obter(dados):
                status, corpo = servidor.disputas_apertadas({"cargo": [cargo]})
                self.assertEqual(status, 200)
                self.assertEqual(len(corpo["disputas"]), 27)
                self.assertEqual(corpo["cargo"], cargo)

    def test_disputas_e_regioes_validam_a_selecao(self):
        for rota, consulta in (
            (servidor.disputas_apertadas, {}), (servidor.disputas_apertadas, {"cargo": ["presidente"]}),
            (servidor.disputas_apertadas, {"cargo": ["senador"], "turno": ["2"]}),
            (servidor.disputas_apertadas, {"cargo": ["governador"], "ambiente": ["../x"]}),
            (servidor.regioes_do_pais, {"turno": ["9"]}),
        ):
            with self.subTest(rota=rota.__name__, consulta=consulta), mock.patch.object(servidor.CACHE, "obter") as obter:
                self.assertEqual(rota(consulta)[0], 400)
                obter.assert_not_called()

    def test_erro_do_tse_passa_adiante(self):
        with self.obter({}):
            self.assertEqual(servidor.regioes_do_pais({})[0], 404)
            self.assertEqual(servidor.disputas_apertadas({"cargo": ["governador"]})[0], 404)

    def test_rotas_na_tabela(self):
        for caminho, funcao in (("/api/mapa", servidor.mapa_por_uf), ("/api/regioes", servidor.regioes_do_pais), ("/api/disputas", servidor.disputas_apertadas)):
            self.assertIs(servidor.ROTAS_API[caminho], funcao)


if __name__ == "__main__":
    unittest.main()
