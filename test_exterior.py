import json
import threading
import unittest
from pathlib import Path
from unittest import mock

import contador
import exterior
import servidor
from test_historico import tse
from varredura import Varredor

MUNDO = json.loads((Path(__file__).with_name("web") / "geo" / "mundo.json").read_text(encoding="utf-8"))
ANA, BRUNO = ("13", "ANA LIMA", "PT"), ("22", "BRUNO CASTRO", "PL")


def cidade(votos, apuradas=1000, final=True):
    """Resumo de uma cidade, como o varredor o guarda."""
    return exterior.resumir_cidade(tse(votos, apuradas=apuradas, final=final, candidatos=(ANA, BRUNO)))


class Tabela(unittest.TestCase):
    def test_todo_pais_da_tabela_tem_forma_no_mapa(self):
        self.assertEqual(sorted(pais for pais in exterior.PAISES if pais not in MUNDO["m"]), [])
        self.assertTrue(all(pais in MUNDO["n"] for pais in exterior.PAISES))

    def test_uma_cidade_so_pertence_a_um_pais(self):
        self.assertEqual(len(exterior.PAIS_DA_CIDADE), sum(len(c) for c in exterior.PAISES.values()))

    def test_cidades_conhecidas(self):
        for nome, pais in (("LISBOA", "PT"), ("NOVA YORK", "US"), ("CAIENA", "FR"), ("TÓQUIO", "JP"), ("CIDADE DO CABO", "ZA"), ("RIO BRANCO", "UY")):
            with self.subTest(cidade=nome):
                self.assertEqual(exterior.PAIS_DA_CIDADE[nome], pais)

    def test_cidades_do_arquivo_de_configuracao(self):
        config = {"abr": [
            {"cd": "sp", "mu": [{"cd": "71072", "nm": "SÃO PAULO"}]},
            {"cd": "zz", "mu": [{"cd": "1", "nm": "LISBOA"}, {"cd": "2", "nm": "Porto "}, {"cd": "3", "nm": "CIDADE NOVA"}]},
        ]}
        self.assertEqual(exterior.cidades_do_exterior(config), [
            {"codigo": "1", "nome": "LISBOA", "pais": "PT"}, {"codigo": "2", "nome": "Porto ", "pais": "PT"}, {"codigo": "3", "nome": "CIDADE NOVA", "pais": None}])
        self.assertEqual(exterior.cidades_do_exterior({"abr": []}), [])


class Soma(unittest.TestCase):
    def test_soma_as_cidades_do_pais_e_acha_o_lider(self):
        pais = exterior.pais_do_resumo([cidade([300, 100]), cidade([100, 250])], 2)
        self.assertEqual((pais["situacao"], pais["votos"], pais["apurado"], pais["final"], pais["locais"], pais["carregados"]), ("lider", 750, 100.0, True, 2, 2))
        self.assertEqual((pais["lider"]["nome"], pais["lider"]["votos"], pais["lider"]["percentual"]), ("ANA LIMA", 400, 53.33))
        self.assertEqual((pais["segundo"]["nome"], pais["margem"], pais["margem_votos"]), ("BRUNO CASTRO", 6.66, 50))

    def test_empate_e_zerado_nao_escolhem_lider(self):
        empate = exterior.pais_do_resumo([cidade([100, 100])], 1)
        self.assertEqual((empate["situacao"], empate["lider"], empate["margem"]), ("empate", None, 0.0))
        zerado = exterior.pais_do_resumo([cidade([0, 0])], 1)
        self.assertEqual((zerado["situacao"], zerado["lider"]), ("zerado", None))
        sem_secao = exterior.pais_do_resumo([cidade([5, 1], apuradas=0)], 1)
        self.assertEqual(sem_secao["situacao"], "zerado")

    def test_pais_sem_nenhuma_cidade_buscada_e_sem_dados(self):
        self.assertEqual(exterior.resumir_territorio({}, {}, 0, 0, 3, 0, True)["situacao"], "sem_dados")

    def test_final_so_com_todas_as_cidades_buscadas_e_finais(self):
        self.assertFalse(exterior.pais_do_resumo([cidade([3, 1])], 2)["final"])                       # falta uma cidade
        self.assertFalse(exterior.pais_do_resumo([cidade([3, 1]), cidade([3, 1], final=False)], 2)["final"])
        self.assertTrue(exterior.pais_do_resumo([cidade([3, 1]), cidade([3, 1])], 2)["final"])

    def test_resumo_da_cidade_e_compacto(self):
        resumo = cidade([30, 10], apuradas=500, final=False)
        self.assertEqual(resumo, {"votos": {"13": 30, "22": 10}, "secoes": [500, 1000], "final": False, "nomes": {"13": ["ANA LIMA", "PT"], "22": ["BRUNO CASTRO", "PL"]}})


class Brasil(unittest.TestCase):
    def test_soma_as_ufs_sem_o_exterior(self):
        corpo = {
            "ufs": {
                "sp": {"votos": {"13": 600, "22": 300}, "secoes": {"total": 100, "apuradas": 50}, "final": False},
                "rj": {"votos": {"13": 100, "22": 500}, "secoes": {"total": 100, "apuradas": 100}, "final": True},
                "ac": {"situacao": "sem_dados"},
            },
            "candidatos": [{"numero": "13", "nome": "ANA LIMA", "partido": "PT", "votos": 750}, {"numero": "22", "nome": "BRUNO CASTRO", "partido": "PL", "votos": 700}],
        }
        brasil = exterior.brasil(corpo)
        self.assertEqual((brasil["situacao"], brasil["votos"], brasil["lider"]["nome"], brasil["lider"]["votos"], brasil["apurado"], brasil["final"]), ("lider", 1500, "BRUNO CASTRO", 800, 75.0, False))
        self.assertIsNone(exterior.brasil({"ufs": {"ac": {"situacao": "sem_dados"}}}))


class Montar(unittest.TestCase):
    CIDADES = [{"codigo": "1", "nome": "LISBOA", "pais": "PT"}, {"codigo": "2", "nome": "FARO", "pais": "PT"}, {"codigo": "3", "nome": "PARIS", "pais": "FR"},
               {"codigo": "4", "nome": "CIDADE NOVA", "pais": None}]

    def fotos(self):
        return {"1": (cidade([30, 10]), 90.0, 200), "2": (None, 0.0, 0), "3": (cidade([5, 50]), 80.0, 200), "4": (None, 0.0, 0)}

    def test_resumo_por_pais_so_com_cidade_buscada(self):
        corpo = exterior.montar(self.CIDADES, self.fotos(), 100.0)
        self.assertEqual((corpo["total"], corpo["carregadas"], corpo["sem_pais"], corpo["idade_s"]), (4, 2, 1, 20))
        self.assertEqual(sorted(corpo["paises"]), ["FR", "PT"])
        self.assertEqual(corpo["locais"], {"PT": 2, "FR": 1})
        self.assertEqual((corpo["paises"]["PT"]["locais"], corpo["paises"]["PT"]["carregados"], corpo["paises"]["PT"]["lider"]["nome"]), (2, 1, "ANA LIMA"))
        self.assertEqual(corpo["paises"]["FR"]["lider"]["nome"], "BRUNO CASTRO")
        self.assertNotIn("detalhe", corpo)

    def test_detalhe_do_pais_traz_candidatos_e_cidades(self):
        detalhe = exterior.montar(self.CIDADES, self.fotos(), 100.0, pais="PT")["detalhe"]
        self.assertEqual(detalhe["pais"], "PT")
        self.assertEqual([(c["nome"], c["votos"], c["percentual"]) for c in detalhe["candidatos"]], [("ANA LIMA", 30, 75.0), ("BRUNO CASTRO", 10, 25.0)])
        faro, lisboa = detalhe["cidades"]
        self.assertEqual((faro["nome"], faro["situacao"]), ("Faro", "sem_dados"))        # ainda não buscada: só o nome
        self.assertEqual((lisboa["nome"], lisboa["situacao"], lisboa["lider"]["nome"], lisboa["votos"]), ("Lisboa", "lider", "ANA LIMA", 40))

    def test_pais_desconhecido_ou_sem_cidade_nao_tem_detalhe(self):
        for pais in ("BR", "ZZ", "JP"):
            self.assertNotIn("detalhe", exterior.montar(self.CIDADES, self.fotos(), 100.0, pais=pais))


class Rota(unittest.TestCase):
    """A rota de verdade com varredor e cache de verdade, sem thread e com um TSE de mentira no lugar da rede."""

    def setUp(self):
        config = {"abr": [{"cd": "zz", "mu": [{"cd": "10", "nm": "LISBOA"}, {"cd": "11", "nm": "PORTO"}, {"cd": "20", "nm": "PARIS"}]}]}
        self.pedidos = []

        def buscar(url, etag=None):
            self.pedidos.append(url)
            if url == contador.url_municipios("oficial", "presidente", 1):
                return contador.Resposta(200, config, "c")
            votos = {"zz10": [30, 10], "zz11": [20, 20], "zz20": [1, 9]}
            for chave, v in votos.items():
                if f"/zz/{chave}-" in url:
                    return contador.Resposta(200, tse(v, candidatos=(ANA, BRUNO), final=True), "e")
            if "/zz/zz-" in url:
                return contador.Resposta(200, tse([51, 49], candidatos=(ANA, BRUNO)), "e")
            return contador.Resposta(404, None, None)

        mapa_dos_estados = {"ufs": {"sp": {"votos": {"13": 5, "22": 4}, "secoes": {"total": 10, "apuradas": 10}, "final": True}},
                            "candidatos": [{"numero": "13", "nome": "ANA LIMA", "partido": "PT"}, {"numero": "22", "nome": "BRUNO CASTRO", "partido": "PL"}]}
        patches = [
            mock.patch.object(servidor, "VARREDOR", Varredor(100, buscar=buscar, relogio=lambda: 1000.0, dormir=lambda s: None)),
            mock.patch.object(servidor, "CACHE", servidor.Cache()),
            mock.patch.object(contador, "buscar", side_effect=buscar),
            mock.patch.object(servidor, "resumo_do_cargo", return_value=(200, mapa_dos_estados)),
            mock.patch.object(threading.Thread, "start"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_comeca_vazio_e_enche_conforme_o_varredor_busca(self):
        status, corpo = servidor.mundo({"pais": ["pt"]})
        self.assertEqual((status, corpo["total"], corpo["carregadas"], corpo["paises"], corpo["turno"], corpo["ambiente"]), (200, 3, 0, {}, 1, "oficial"))
        self.assertEqual(corpo["brasil"]["lider"]["nome"], "ANA LIMA")
        while servidor.VARREDOR.passo():
            pass
        corpo = servidor.mundo({"pais": ["PT"]})[1]
        self.assertEqual((corpo["carregadas"], sorted(corpo["paises"])), (3, ["FR", "PT"]))
        self.assertEqual((corpo["paises"]["PT"]["votos"], corpo["paises"]["PT"]["lider"]["nome"], corpo["paises"]["PT"]["final"]), (80, "ANA LIMA", True))
        self.assertEqual([c["nome"] for c in corpo["detalhe"]["cidades"]], ["Lisboa", "Porto"])

    def test_so_busca_arquivos_de_cidade_do_exterior(self):
        servidor.mundo({})
        antes = len(self.pedidos)
        while servidor.VARREDOR.passo():
            pass
        esperadas = {contador.montar_url("oficial", "presidente", "zz", 1, municipio=c) for c in ("10", "11", "20")}
        self.assertEqual(set(self.pedidos[antes:]), esperadas)

    def test_parametros_invalidos(self):
        for consulta in ({"ambiente": ["../x"]}, {"turno": ["3"]}, {"pais": ["BRA"]}, {"pais": ["1\n"]}, {"pais": ["../"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(servidor.mundo(consulta)[0], 400)
        self.assertEqual(self.pedidos, [])

    def test_varredor_desligado_da_503(self):
        with mock.patch.object(servidor, "VARREDOR", Varredor(0)):
            self.assertEqual(servidor.mundo({}), servidor.RECURSO_DESLIGADO)

    def test_sem_arquivo_do_exterior_nao_varre_nada(self):
        with mock.patch.object(contador, "buscar", return_value=contador.Resposta(404, None, None)), mock.patch.object(servidor, "CACHE", servidor.Cache()):
            self.assertEqual(servidor.mundo({})[0], 404)
        self.assertEqual(servidor.VARREDOR._grupos, {})

    def test_desenho_do_mundo_pelo_servidor(self):
        status, tipo, corpo, extras = servidor.desenho_dos_municipios("/geo/mundo.json")
        self.assertEqual((status, tipo), (200, "application/json; charset=utf-8"))
        self.assertEqual(set(json.loads(corpo)), {"w", "h", "m", "n"})
        self.assertIsNone(servidor.desenho_dos_municipios("/geo/Mundo.json"))
        self.assertIsNone(servidor.desenho_dos_municipios("/geo/mundo.txt"))


if __name__ == "__main__":
    unittest.main()
