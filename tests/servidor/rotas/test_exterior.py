"""Testes de `contador/servidor/rotas/exterior.py`."""
import json
import threading
import unittest
from unittest import mock

from contador.servidor import estado, estaticos, respostas, rotas
from contador.tse import catalogo, cliente
from contador.tse.cache import Cache
from contador.varredor import Varredor
from tests.dados import ANA, BRUNO, tse


class Rota(unittest.TestCase):
    """A rota de verdade com varredor e cache de verdade, sem thread e com um TSE de mentira no lugar da rede."""

    def setUp(self):
        config = {"abr": [{"cd": "zz", "mu": [{"cd": "10", "nm": "LISBOA"}, {"cd": "11", "nm": "PORTO"}, {"cd": "20", "nm": "PARIS"}]}]}
        self.pedidos = []

        def buscar(url, etag=None):
            self.pedidos.append(url)
            if url == catalogo.url_municipios("oficial", "presidente", 1):
                return cliente.Resposta(200, config, "c")
            votos = {"zz10": [30, 10], "zz11": [20, 20], "zz20": [1, 9]}
            for chave, v in votos.items():
                if f"/zz/{chave}-" in url:
                    return cliente.Resposta(200, tse(v, candidatos=(ANA, BRUNO), final=True), "e")
            if "/zz/zz-" in url:
                return cliente.Resposta(200, tse([51, 49], candidatos=(ANA, BRUNO)), "e")
            return cliente.Resposta(404, None, None)

        mapa_dos_estados = {"ufs": {"sp": {"votos": {"13": 5, "22": 4}, "secoes": {"total": 10, "apuradas": 10}, "final": True}},
                            "candidatos": [{"numero": "13", "nome": "ANA LIMA", "partido": "PT"}, {"numero": "22", "nome": "BRUNO CASTRO", "partido": "PL"}]}
        patches = [
            mock.patch.object(estado, "VARREDOR", Varredor(100, buscar=buscar, relogio=lambda: 1000.0, dormir=lambda s: None)),
            mock.patch.object(estado, "CACHE", Cache()),
            mock.patch.object(cliente, "buscar", side_effect=buscar),
            mock.patch.object(respostas, "resumo_do_cargo", return_value=(200, mapa_dos_estados)),
            mock.patch.object(threading.Thread, "start"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_comeca_vazio_e_enche_conforme_o_varredor_busca(self):
        status, corpo = rotas.mundo({"pais": ["pt"]})
        self.assertEqual((status, corpo["total"], corpo["carregadas"], corpo["paises"], corpo["turno"], corpo["ambiente"]), (200, 3, 0, {}, 1, "oficial"))
        self.assertEqual(corpo["brasil"]["lider"]["nome"], "ANA LIMA")
        while estado.VARREDOR.passo():
            pass
        corpo = rotas.mundo({"pais": ["PT"]})[1]
        self.assertEqual((corpo["carregadas"], sorted(corpo["paises"])), (3, ["FR", "PT"]))
        self.assertEqual((corpo["paises"]["PT"]["votos"], corpo["paises"]["PT"]["lider"]["nome"], corpo["paises"]["PT"]["final"]), (80, "ANA LIMA", True))
        self.assertEqual([c["nome"] for c in corpo["detalhe"]["cidades"]], ["Lisboa", "Porto"])

    def test_so_busca_arquivos_de_cidade_do_exterior(self):
        rotas.mundo({})
        antes = len(self.pedidos)
        while estado.VARREDOR.passo():
            pass
        esperadas = {catalogo.montar_url("oficial", "presidente", "zz", 1, municipio=c) for c in ("10", "11", "20")}
        self.assertEqual(set(self.pedidos[antes:]), esperadas)

    def test_parametros_invalidos(self):
        for consulta in ({"ambiente": ["../x"]}, {"turno": ["3"]}, {"pais": ["BRA"]}, {"pais": ["1\n"]}, {"pais": ["../"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(rotas.mundo(consulta)[0], 400)
        self.assertEqual(self.pedidos, [])

    def test_varredor_desligado_da_503(self):
        with mock.patch.object(estado, "VARREDOR", Varredor(0)):
            self.assertEqual(rotas.mundo({}), respostas.RECURSO_DESLIGADO)

    def test_sem_arquivo_do_exterior_nao_varre_nada(self):
        with mock.patch.object(cliente, "buscar", return_value=cliente.Resposta(404, None, None)), mock.patch.object(estado, "CACHE", Cache()):
            self.assertEqual(rotas.mundo({})[0], 404)
        self.assertEqual(estado.VARREDOR._grupos, {})

    def test_desenho_do_mundo_pelo_servidor(self):
        status, tipo, corpo, extras = estaticos.desenho_dos_municipios("/geo/mundo.json")
        self.assertEqual((status, tipo), (200, "application/json; charset=utf-8"))
        self.assertEqual(set(json.loads(corpo)), {"w", "h", "m", "n"})
        self.assertIsNone(estaticos.desenho_dos_municipios("/geo/Mundo.json"))
        self.assertIsNone(estaticos.desenho_dos_municipios("/geo/mundo.txt"))
