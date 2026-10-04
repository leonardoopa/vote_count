import unittest
from argparse import Namespace

import contador

DADOS = {
    "tf": "n",
    "dt": "04/10/2026",
    "ht": "18:01:02",
    "dg": "04/10/2026",
    "hg": "18:01:30",
    "s": {"ts": "1000", "st": "250", "pst": "25,00"},
    "e": {"te": "5000", "c": "900", "pc": "90,00", "a": "100", "pa": "2,00"},
    "v": {"tv": "900", "vb": "20", "pvb": "2,22", "tvn": "30", "ptvn": "3,33"},
    "carg": [
        {
            "agr": [
                {
                    "par": [
                        {
                            "sg": "AAA",
                            "cand": [
                                {"n": "11", "nm": "ANA", "nmu": "ANA", "vap": "100", "pvap": "20,00"},
                                {"n": "12", "nm": "BIA", "nmu": "BIA", "vap": "400", "pvap": "80,00", "st": "2º turno"},
                            ],
                        }
                    ]
                }
            ]
        }
    ],
}

ARGS = Namespace(cargo="presidente", uf="br", turno=1, ambiente="oficial", top=10, intervalo=10)

CONFIG_MUNICIPIOS = {
    "abr": [
        {
            "cd": "sp",
            "mu": [
                {"cd": "71072", "nm": "SÃO PAULO", "c": "s"},
                {"cd": "62910", "nm": "CAMPINAS", "c": "n"},
                {"cd": "70670", "nm": "SÃO JOÃO DA BOA VISTA", "c": "n"},
                {"cd": "70750", "nm": "SÃO JOÃO DEL REI", "c": "n"},
            ],
        },
        {"cd": "df", "mu": [{"cd": "97012", "nm": "BRASÍLIA", "c": "s"}]},
    ]
}


class MontarUrl(unittest.TestCase):
    def test_presidente_oficial(self):
        self.assertEqual(
            contador.montar_url("oficial", "presidente", "br", 1),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json",
        )

    def test_governador_segundo_turno(self):
        self.assertEqual(
            contador.montar_url("oficial", "governador", "sp", 2),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/dados/sp/sp-c0003-e006260-u.json",
        )

    def test_cidade_usa_uf_mais_codigo_no_nome_do_arquivo(self):
        self.assertEqual(
            contador.montar_url("oficial", "presidente", "sp", 1, municipio="71072"),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/sp/sp71072-c0001-e006257-u.json",
        )

    def test_cidade_de_cargo_estadual_no_segundo_turno(self):
        self.assertEqual(
            contador.montar_url("oficial", "governador", "sp", 2, municipio="62910"),
            "https://resultados.tse.jus.br/oficial/ele2026/6260/dados/sp/sp62910-c0003-e006260-u.json",
        )

    def test_lista_de_cidades_e_por_eleicao(self):
        self.assertEqual(
            contador.url_municipios("oficial", "presidente", 1),
            "https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json",
        )
        self.assertIn("/6259/config/mun-e006259-cm.json", contador.url_municipios("oficial", "senador", 1))

    def test_simulado(self):
        self.assertIn("resultados-sim.tse.jus.br/simulado/simulado2026/ele2026/21272/", contador.montar_url("simulado", "senador", "ac", 1))


class Candidatos(unittest.TestCase):
    def test_ordem_por_votos(self):
        self.assertEqual([c["nm"] for c in contador.candidatos(DADOS)], ["BIA", "ANA"])

    def test_partido_anexado(self):
        self.assertEqual(contador.candidatos(DADOS)[0]["partido"], "AAA")


class Cidades(unittest.TestCase):
    def test_nome_proprio(self):
        self.assertEqual(contador.nome_proprio("SÃO PAULO"), "São Paulo")
        self.assertEqual(contador.nome_proprio("SÃO JOÃO DEL REI"), "São João del Rei")
        self.assertEqual(contador.nome_proprio("SANTA BÁRBARA D'OESTE"), "Santa Bárbara D'Oeste")
        self.assertEqual(contador.nome_proprio("DE"), "De")  # a primeira palavra nunca fica minúscula

    def test_lista_da_uf_em_ordem_alfabetica_sem_acento(self):
        nomes = [m["nome"] for m in contador.municipios(CONFIG_MUNICIPIOS, "sp")]
        self.assertEqual(nomes, ["Campinas", "São João da Boa Vista", "São João del Rei", "São Paulo"])

    def test_capital_marcada(self):
        capital = [m for m in contador.municipios(CONFIG_MUNICIPIOS, "sp") if m["capital"]]
        self.assertEqual([m["codigo"] for m in capital], ["71072"])

    def test_uf_desconhecida_devolve_vazio(self):
        self.assertEqual(contador.municipios(CONFIG_MUNICIPIOS, "xx"), [])

    def test_achar_ignora_acento_e_caixa(self):
        lista = contador.municipios(CONFIG_MUNICIPIOS, "sp")
        cidade, _ = contador.achar_municipio(lista, "sao paulo")
        self.assertEqual(cidade["codigo"], "71072")

    def test_achar_por_trecho_unico(self):
        lista = contador.municipios(CONFIG_MUNICIPIOS, "sp")
        self.assertEqual(contador.achar_municipio(lista, "campi")[0]["codigo"], "62910")

    def test_achar_ambiguo_devolve_candidatas(self):
        lista = contador.municipios(CONFIG_MUNICIPIOS, "sp")
        cidade, parecidas = contador.achar_municipio(lista, "joao")
        self.assertIsNone(cidade)
        self.assertEqual(len(parecidas), 2)

    def test_achar_nome_exato_vence_trecho(self):
        lista = [{"codigo": "1", "nome": "Itu"}, {"codigo": "2", "nome": "Ituiutaba"}]
        self.assertEqual(contador.achar_municipio(lista, "itu")[0]["codigo"], "1")

    def test_achar_nada(self):
        lista = contador.municipios(CONFIG_MUNICIPIOS, "sp")
        self.assertEqual(contador.achar_municipio(lista, "xyz"), (None, []))
        self.assertEqual(contador.achar_municipio(lista, ""), (None, []))


class Renderizar(unittest.TestCase):
    def test_placar(self):
        texto = contador.renderizar(DADOS, ARGS)
        self.assertIn("Totalização PARCIAL", texto)
        self.assertIn("seções apuradas 250 de 1.000 (25,00%)", texto)
        self.assertLess(texto.index("BIA"), texto.index("ANA"))
        self.assertIn("2º turno", texto)

    def test_titulo_com_cidade(self):
        args = Namespace(**{**vars(ARGS), "uf": "sp", "cidade_nome": "Campinas"})
        self.assertIn("PRESIDENTE · SP · CAMPINAS", contador.renderizar(DADOS, args))

    def test_zero_votos_sem_divisao_por_zero(self):
        zerado = {**DADOS, "carg": [{"agr": [{"par": [{"sg": "A", "cand": [{"n": "1", "nm": "X", "vap": "0", "pvap": "0,00"}]}]}]}]}
        self.assertIn("X", contador.renderizar(zerado, ARGS))

    def test_top_limita_linhas(self):
        texto = contador.renderizar(DADOS, Namespace(**{**vars(ARGS), "top": 1}))
        self.assertNotIn("ANA", texto)


class Argumentos(unittest.TestCase):
    def test_presidente_padrao_br(self):
        self.assertEqual(contador.ler_argumentos([]).uf, "br")

    def test_governador_exige_uf(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["-c", "governador"])

    def test_cidade_precisa_de_uf(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["--cidade", "campinas"])

    def test_cidade_com_uf(self):
        args = contador.ler_argumentos(["--uf", "sp", "--cidade", "campinas"])
        self.assertEqual((args.uf, args.cidade, args.municipio), ("sp", "campinas", None))

    def test_municipio_so_com_cinco_digitos(self):
        for codigo in ("123", "abcde", "123456", "../../"):
            with self.subTest(codigo=codigo), self.assertRaises(SystemExit):
                contador.ler_argumentos(["--uf", "sp", "--municipio", codigo])

    def test_cidade_e_municipio_juntos(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["--uf", "sp", "--cidade", "campinas", "--municipio", "62910"])

    def test_intervalo_minimo(self):
        with self.assertRaises(SystemExit):
            contador.ler_argumentos(["--intervalo", "1"])


if __name__ == "__main__":
    unittest.main()
