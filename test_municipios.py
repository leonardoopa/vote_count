import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import contador
import municipios
import servidor
import tse_falso
from test_mapa import DOIS, arquivo
from varredura import Varredor

CONFIG = {"abr": [
    {"cd": "sp", "mu": [{"cd": "71072", "cdi": "3550308", "nm": "SÃO PAULO", "c": "s"}, {"cd": "62910", "cdi": "3509502", "nm": "CAMPINAS", "c": "n"},
                        {"cd": "11111", "nm": "SEM CODIGO IBGE", "c": "n"}]},
    {"cd": "df", "mu": [{"cd": "97012", "cdi": "5300108", "nm": "BRASÍLIA", "c": "s"}]},
]}


class ResumirCidade(unittest.TestCase):
    def test_lider_compacto(self):
        resumo = municipios.resumir_cidade(arquivo(DOIS, secoes=(100, 80)))
        self.assertEqual(resumo, {
            "situacao": "lider", "apurado": 80.0, "final": False, "margem": 20.0, "margem_votos": 200,
            "lider": {"nome": "ANA", "partido": "PT", "percentual": 60.0, "eleito": False, "segundo_turno": False},
        })

    def test_zerado_e_empate(self):
        zerado = municipios.resumir_cidade(arquivo([("13", "Ana", "PT", 0, "0,00", ""), ("22", "Bia", "PL", 0, "0,00", "")]))
        self.assertEqual(zerado, {"situacao": "zerado", "apurado": 50.0, "final": False})
        empate = municipios.resumir_cidade(arquivo([("13", "Ana", "PT", 500, "50,00", ""), ("22", "Bia", "PL", 500, "50,00", "")]))
        self.assertEqual((empate["situacao"], [c["partido"] for c in empate["empatados"]]), ("empate", ["PT", "PL"]))
        self.assertNotIn("lider", empate)

    def test_eleito_e_final_vem_do_arquivo(self):
        dados = arquivo([("13", "Ana", "PT", 600, "60,00", "Eleito"), ("22", "Bia", "PL", 400, "40,00", "")], final=True)
        resumo = municipios.resumir_cidade(dados)
        self.assertTrue(resumo["final"] and resumo["lider"]["eleito"])

    def test_arquivo_fora_do_formato_levanta_para_o_varredor_tratar(self):
        with self.assertRaises((KeyError, TypeError, IndexError)):
            municipios.resumir_cidade({})

    def test_intervalo(self):
        self.assertEqual(municipios.intervalo(None), municipios.INTERVALO_APURANDO_S)
        self.assertEqual(municipios.intervalo({"final": True}), municipios.INTERVALO_FINAL_S)


class Montar(unittest.TestCase):
    def test_ibge_das_cidades(self):
        self.assertEqual(municipios.ibge_das_cidades(CONFIG, "sp"), {"71072": "3550308", "62910": "3509502"})  # sem código IBGE, sem desenho
        self.assertEqual(municipios.ibge_das_cidades(CONFIG, "xx"), {})
        self.assertEqual(municipios.ibge_das_cidades({}, "sp"), {})

    def test_so_traz_o_que_ja_foi_buscado_e_tem_desenho(self):
        cidades = contador.municipios(CONFIG, "sp")
        ibge = municipios.ibge_das_cidades(CONFIG, "sp")
        fotos = {"71072": ({"situacao": "zerado", "apurado": 0.0, "final": False}, 990.0, 200), "62910": (None, 0.0, 0),
                 "11111": ({"situacao": "zerado", "apurado": 0.0, "final": False}, 980.0, 200)}
        corpo = municipios.montar("sp", cidades, ibge, fotos, 1000.0)
        self.assertEqual(list(corpo["cidades"]), ["3550308"])
        self.assertEqual(corpo["cidades"]["3550308"]["nome"], "São Paulo")
        self.assertEqual(corpo["cidades"]["3550308"]["codigo"], "71072")
        self.assertEqual((corpo["uf"], corpo["total"], corpo["carregadas"], corpo["idade_s"]), ("sp", 3, 2, 20))

    def test_sem_nada_buscado(self):
        corpo = municipios.montar("sp", contador.municipios(CONFIG, "sp"), {}, {}, 1000.0)
        self.assertEqual((corpo["cidades"], corpo["carregadas"], corpo["idade_s"]), ({}, 0, None))


class Relogio:
    agora = 1000.0

    def __call__(self):
        return self.agora


class Rota(unittest.TestCase):
    """A rota de verdade com varredor e cache de verdade, sem thread e com o TSE falso no lugar da rede."""

    def setUp(self):
        self.pedidos = []

        def buscar(url, etag=None):
            self.pedidos.append(url)
            return tse_falso.buscar_falso(url, etag)

        patches = [
            mock.patch.object(servidor, "VARREDOR", Varredor(100, buscar=buscar, relogio=Relogio(), dormir=lambda s: None)),
            mock.patch.object(servidor, "CACHE", servidor.Cache()),
            mock.patch.object(contador, "buscar", side_effect=buscar),
            mock.patch.object(threading.Thread, "start"),
            mock.patch.object(tse_falso, "progresso", return_value=(150, 0.5)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.consulta = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["ac"]}

    def test_comeca_vazio_e_enche_conforme_o_varredor_busca(self):
        status, corpo = servidor.mapa_municipal(self.consulta)
        total = len(tse_falso.cidades_da_uf("ac"))
        self.assertEqual((status, corpo["total"], corpo["carregadas"], corpo["cidades"]), (200, total, 0, {}))
        for _ in range(4):
            servidor.VARREDOR.passo()
        corpo = servidor.mapa_municipal(self.consulta)[1]
        self.assertEqual(corpo["carregadas"], 4)
        ibge = {ibge for _, ibge, _ in tse_falso.cidades_da_uf("ac")}
        self.assertTrue(set(corpo["cidades"]) <= ibge and len(corpo["cidades"]) == 4)
        primeira = next(iter(corpo["cidades"].values()))
        self.assertEqual(primeira["situacao"], "lider")
        self.assertEqual((corpo["cargo"], corpo["turno"], corpo["ambiente"], corpo["uf"]), ("governador", 1, "simulado", "ac"))

    def test_o_varredor_so_pede_arquivos_de_cidade_da_uf(self):
        servidor.mapa_municipal(self.consulta)
        antes = len(self.pedidos)
        while servidor.VARREDOR.passo():
            pass
        cidades = {contador.montar_url("simulado", "governador", "ac", 1, municipio=tse) for tse, _, _ in tse_falso.cidades_da_uf("ac")}
        self.assertEqual(set(self.pedidos[antes:]), cidades)

    def test_cidades_so_depois_do_arquivo_da_uf_existir(self):
        # governador no 2º turno numa UF decidida no 1º: o TSE não tem arquivo, então nenhuma cidade é varrida
        uf = next(uf for uf in contador.UFS if tse_falso.base_do_turno("governador", uf, 2) is None)
        status, corpo = servidor.mapa_municipal({"ambiente": ["simulado"], "cargo": ["governador"], "uf": [uf], "turno": ["2"]})
        self.assertEqual(status, 404)
        self.assertEqual(servidor.VARREDOR._grupos, {})

    def test_so_presidente_e_governador_dentro_de_um_estado(self):
        for consulta in ({"cargo": ["senador"], "uf": ["sp"]}, {"cargo": ["presidente"], "uf": ["br"]}, {"cargo": ["x"]},
                         {"cargo": ["governador"], "uf": ["sp"], "ambiente": ["../x"]}, {"cargo": ["governador"], "uf": ["sp"], "turno": ["7"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(servidor.mapa_municipal(consulta)[0], 400)
        self.assertEqual(self.pedidos, [])

    def test_presidente_em_uma_uf_funciona(self):
        status, corpo = servidor.mapa_municipal({"ambiente": ["simulado"], "cargo": ["presidente"], "uf": ["ac"]})
        self.assertEqual((status, corpo["cargo"]), (200, "presidente"))

    def test_varredor_desligado_da_503(self):
        with mock.patch.object(servidor, "VARREDOR", Varredor(0)):
            self.assertEqual(servidor.mapa_municipal(self.consulta), servidor.RECURSO_DESLIGADO)

    def test_tse_sem_a_lista_de_cidades(self):
        with mock.patch.object(servidor, "CACHE", servidor.Cache()), mock.patch.object(contador, "buscar", return_value=contador.Resposta(404, None, None)):
            self.assertEqual(servidor.mapa_municipal(self.consulta)[0], 404)

    def test_rota_na_tabela(self):
        self.assertIs(servidor.ROTAS_API["/api/mapa-municipal"], servidor.mapa_municipal)


class Desenhos(unittest.TestCase):
    def test_todas_as_ufs_tem_desenho_e_ele_bate_com_o_codigo_do_tse(self):
        for uf in contador.UFS:
            status, tipo, corpo, extras = servidor.desenho_dos_municipios(f"/geo/{uf}.json")
            self.assertEqual((status, tipo, extras["Cache-Control"]), (200, "application/json; charset=utf-8", "no-cache"))
            self.assertTrue(extras["ETag"].startswith('W/"'))
            desenho = json.loads(corpo)
            self.assertEqual(set(desenho), {"w", "h", "m"})
            self.assertTrue(all(d.startswith("M") and d.endswith("z") for d in desenho["m"].values()))
            self.assertTrue(all(len(c) == 7 and c.isdigit() for c in desenho["m"]))  # código IBGE do município

    def test_o_desenho_cobre_os_municipios_do_tse_menos_os_muito_novos(self):
        # em 2026 o desenho do IBGE ainda não traz 1 município de MT; os demais têm todos o seu contorno
        for uf in ("sp", "ac", "df", "rj"):
            desenho = json.loads(servidor.desenho_dos_municipios(f"/geo/{uf}.json")[2])["m"]
            self.assertGreater(len(desenho), 0)

    def test_caminhos_que_nao_sao_desenho(self):
        for caminho in ("/geo/xx.json", "/geo/sp.txt", "/geo/", "/geo/../servidor.py", "/geo/sp.json/x", "/outra/sp.json", "/geo/SP.json"):
            with self.subTest(caminho=caminho):
                self.assertIsNone(servidor.desenho_dos_municipios(caminho))

    def test_desenho_que_falta_da_404(self):
        with mock.patch.object(servidor, "GEO", Path("/nao/existe")):
            self.assertEqual(servidor.desenho_dos_municipios("/geo/sp.json")[0], 404)


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def pedir(self, caminho):
        conexao = http.client.HTTPConnection("127.0.0.1", self.http.server_address[1], timeout=10)
        conexao.request("GET", caminho)
        resposta = conexao.getresponse()
        corpo = resposta.read()
        conexao.close()
        return resposta, corpo

    def test_desenho_pelo_http(self):
        resposta, corpo = self.pedir("/geo/sp.json")
        self.assertEqual((resposta.status, resposta.getheader("Cache-Control")), (200, "no-cache"))
        self.assertGreater(len(json.loads(corpo)["m"]), 600)
        self.assertEqual(self.pedir("/geo/zz.json")[0].status, 404)
        self.assertEqual(self.pedir("/geo/..%2Fservidor.py")[0].status, 404)


if __name__ == "__main__":
    unittest.main()
