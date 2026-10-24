"""Testes de `contador/varredor.py`."""
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from contador import varredor
from contador.tse import cliente
from contador.varredor import Trabalho, Varredor


R = cliente.Resposta


def fabrica(urls, intervalo=60, resumir=lambda dados, chave: {"x": dados["x"]}):
    return lambda: ({c: Trabalho(c, u) for c, u in urls.items()}, resumir, lambda resumo: intervalo)


def criar_varredor(respostas, **kw):
    relogio = Relogio()
    return Varredor(kw.pop("por_segundo", 2), buscar=Fonte(respostas), relogio=relogio, dormir=lambda s: None), relogio


class Relogio:
    def __init__(self, agora=1000.0):
        self.agora = agora

    def __call__(self):
        return self.agora


class Fonte:
    """Faz de conta de `cliente.buscar`: responde por URL, uma lista de respostas por vez, e anota os pedidos."""

    def __init__(self, respostas):
        self.respostas, self.pedidos = {u: list(r) if isinstance(r, list) else [r] for u, r in respostas.items()}, []

    def __call__(self, url, etag=None):
        self.pedidos.append((url, etag))
        fila = self.respostas.get(url, [R(404, None, etag)])
        return fila.pop(0) if len(fila) > 1 else fila[0]


class Passo(unittest.TestCase):
    def test_desligado_nao_cria_grupo_nem_thread(self):
        v = Varredor(0)
        self.assertFalse(v.ligado)
        self.assertIsNone(v.pedir("g", fabrica({"a": "u"})))
        self.assertIsNone(v._thread)

    def test_guarda_o_resumo_e_a_hora(self):
        v, relogio = criar_varredor({"ua": R(200, {"x": 1}, '"e1"')})
        grupo = self.pedir_sem_thread(v, "g", fabrica({"a": "ua"}))
        self.assertTrue(v.passo())
        self.assertEqual(v.resumos(grupo), {"a": ({"x": 1}, 1000.0, 200)})
        self.assertFalse(v.passo())  # nada vencido ainda
        relogio.agora += 61
        self.assertTrue(v.passo())

    def pedir_sem_thread(self, v, nome, f):
        with mock.patch.object(threading.Thread, "start"):
            return v.pedir(nome, f)

    def test_etag_vai_na_busca_seguinte_e_304_mantem_o_resumo(self):
        v, relogio = criar_varredor({"ua": [R(200, {"x": 1}, '"e1"'), R(304, None, '"e1"')]})
        grupo = self.pedir_sem_thread(v, "g", fabrica({"a": "ua"}))
        v.passo()
        relogio.agora += 61
        v.passo()
        self.assertEqual(v.buscar.pedidos, [("ua", None), ("ua", '"e1"')])
        self.assertEqual(v.resumos(grupo)["a"], ({"x": 1}, 1061.0, 304))

    def test_busca_primeiro_o_mais_atrasado_ou_nunca_buscado(self):
        v, relogio = criar_varredor({f"u{i}": R(200, {"x": i}, None) for i in range(3)})
        self.pedir_sem_thread(v, "g", fabrica({f"c{i}": f"u{i}" for i in range(3)}))
        for _ in range(3):
            v.passo()
        self.assertEqual([u for u, _ in v.buscar.pedidos], ["u0", "u1", "u2"])
        relogio.agora += 100
        v.passo()
        self.assertEqual(v.buscar.pedidos[-1][0], "u0")  # o que venceu há mais tempo

    def test_intervalo_vem_do_resumo(self):
        v, relogio = criar_varredor({"ua": R(200, {"x": 1}, None)})
        grupo = self.pedir_sem_thread(v, "g", lambda: ({"a": Trabalho("a", "ua")}, lambda d, c: {"x": d["x"]}, lambda resumo: 1800 if resumo["x"] else 5))
        v.passo()
        self.assertEqual(grupo.trabalhos["a"].proxima, 1000.0 + 1800)

    def test_arquivo_fora_do_formato_nao_derruba(self):
        def resumir(dados, chave):
            return dados["falta"]

        v, _ = criar_varredor({"ua": R(200, {"x": 1}, None)})
        grupo = self.pedir_sem_thread(v, "g", fabrica({"a": "ua"}, resumir=resumir))
        self.assertTrue(v.passo())
        self.assertEqual(v.resumos(grupo)["a"][0], None)

    def test_so_grupos_com_pedido_recente(self):
        v, relogio = criar_varredor({"ua": R(200, {"x": 1}, None), "ub": R(200, {"x": 2}, None)})
        self.pedir_sem_thread(v, "a", fabrica({"a": "ua"}))
        relogio.agora += varredor.OCIOSO_S + 1
        self.pedir_sem_thread(v, "b", fabrica({"b": "ub"}))
        v.passo()
        v.passo()
        self.assertEqual([u for u, _ in v.buscar.pedidos], ["ub"])  # "a" ficou ocioso

    def test_grupo_e_reaproveitado(self):
        v, _ = criar_varredor({})
        chamadas = []
        f = lambda: (chamadas.append(1), ({"a": Trabalho("a", "u")}, lambda d, c: d, lambda r: 1))[1]
        a = self.pedir_sem_thread(v, "g", f)
        b = self.pedir_sem_thread(v, "g", f)
        self.assertIs(a, b)
        self.assertEqual(len(chamadas), 1)

    def test_numero_de_grupos_tem_teto(self):
        v, _ = criar_varredor({})
        with mock.patch.object(varredor, "MAX_GRUPOS", 3):
            for i in range(6):
                self.pedir_sem_thread(v, f"g{i}", fabrica({"a": "u"}))
        self.assertEqual(list(v._grupos), ["g3", "g4", "g5"])


class Protecoes(unittest.TestCase):
    def montar(self, respostas, quantos=6):
        v, relogio = criar_varredor(respostas)
        with mock.patch.object(threading.Thread, "start"):
            grupo = v.pedir("g", fabrica({f"c{i}": f"u{i}" for i in range(quantos)}))
        return v, relogio, grupo

    def test_403_pausa_tudo_por_dez_minutos(self):
        v, relogio, grupo = self.montar({"u0": R(403, None, None)})
        self.assertTrue(v.passo())
        self.assertFalse(v.passo())
        relogio.agora += varredor.PAUSA_BLOQUEIO_S - 1
        self.assertFalse(v.passo())
        relogio.agora += 2
        grupo.ultimo_pedido = relogio.agora  # alguém continua olhando
        self.assertTrue(v.passo())

    def test_429_tambem_pausa(self):
        v, relogio, _ = self.montar({"u0": R(429, None, None)})
        v.passo()
        self.assertFalse(v.passo())

    def test_tres_404_seguidos_pausam_por_um_minuto(self):
        v, relogio, grupo = self.montar({})  # tudo 404
        self.assertEqual([v.passo() for _ in range(4)], [True, True, True, False])
        relogio.agora += varredor.PAUSA_404_S + 1
        self.assertTrue(v.passo())

    def test_um_200_zera_a_conta_de_404(self):
        v, relogio, grupo = self.montar({"u1": R(200, {"x": 1}, None)})
        v.passo()  # u0: 404
        v.passo()  # u1: 200
        v.passo()  # u2: 404
        v.passo()  # u3: 404
        self.assertTrue(v.passo())  # só dois 404 seguidos até aqui

    def test_404_nao_repete_o_mesmo_arquivo_logo(self):
        v, relogio, grupo = self.montar({}, quantos=1)
        v.passo()
        self.assertFalse(v.passo())
        self.assertEqual(grupo.trabalhos["c0"].proxima, 1000.0 + varredor.PAUSA_404_S)

    def test_erro_de_rede_espera_um_pouco(self):
        v, relogio, grupo = self.montar({"u0": R(0, None, None)}, quantos=1)
        v.passo()
        self.assertEqual(grupo.trabalhos["c0"].proxima, 1000.0 + varredor.ESPERA_FALHA_S)


class Thread(unittest.TestCase):
    class Parar(Exception):
        pass

    def test_respeita_o_limite_por_segundo(self):
        v, relogio = criar_varredor({f"u{i}": R(200, {"x": i}, None) for i in range(5)}, por_segundo=4)
        with mock.patch.object(threading.Thread, "start"):
            v.pedir("g", fabrica({f"c{i}": f"u{i}" for i in range(5)}))
        esperas = []

        def dormir(segundos):
            esperas.append(segundos)
            if len(esperas) == 6:
                raise self.Parar

        v.dormir = dormir
        with self.assertRaises(self.Parar):
            v._rodar()
        self.assertEqual(esperas, [0.25] * 5 + [1.0])  # 5 buscas a 4 por segundo; depois não há o que fazer

    def test_encerra_quando_ninguem_pede(self):
        v, relogio = criar_varredor({"u0": R(200, {"x": 0}, None)})
        with mock.patch.object(threading.Thread, "start"):
            v.pedir("g", fabrica({"c0": "u0"}))
        relogio.agora += varredor.OCIOSO_S + 1
        v._thread = object()
        v._rodar()  # volta sozinho, sem buscar nada
        self.assertIsNone(v._thread)
        self.assertEqual(v.buscar.pedidos, [])

    def test_thread_de_verdade_busca_e_depois_encerra(self):
        feito = threading.Event()

        def buscar(url, etag=None):
            feito.set()
            return R(200, {"x": 1}, None)

        v = Varredor(1000, buscar=buscar)
        grupo = v.pedir("g", fabrica({"a": "u"}, intervalo=3600))
        self.assertTrue(feito.wait(5))
        for _ in range(100):
            if v.resumos(grupo)["a"][0]:
                break
            threading.Event().wait(0.02)
        self.assertEqual(v.resumos(grupo)["a"][0], {"x": 1})
        self.assertTrue(v._thread.is_alive() or v._thread is None)


class Prioridade(unittest.TestCase):
    URLS = {c: f"http://tse/{c}" for c in "abcd"}

    def preparar(self):
        v, relogio = criar_varredor({u: R(200, {"x": 1}, "e") for u in self.URLS.values()})
        with mock.patch.object(threading.Thread, "start"):   # sem a thread de verdade: o teste chama `passo` à mão
            return v, relogio, v.pedir("g", fabrica(self.URLS))

    def buscados(self, v, n=4):
        for _ in range(n):
            v.passo()
        return [u[-1] for u, _ in v.buscar.pedidos]

    def test_sem_foco_vale_a_ordem_do_grupo(self):
        v, _, _ = self.preparar()
        self.assertEqual(self.buscados(v), list("abcd"))

    def test_foco_fura_a_fila_na_ordem_pedida(self):
        v, _, grupo = self.preparar()
        v.priorizar(grupo, ["c", "a", "inexistente"])
        self.assertEqual(self.buscados(v), list("cabd"))

    def test_nova_lista_troca_a_anterior(self):
        v, _, grupo = self.preparar()
        v.priorizar(grupo, ["a", "b"])
        v.priorizar(grupo, ["d"])
        self.assertEqual(self.buscados(v), list("dabc"))

    def test_foco_vence_depois_de_foco_s(self):
        v, relogio, grupo = self.preparar()
        v.priorizar(grupo, ["d"])
        relogio.agora += varredor.FOCO_S + 1
        self.assertEqual(self.buscados(v), list("abcd"))

    def test_o_teto_de_buscas_nao_muda(self):
        v, _, grupo = self.preparar()
        v.priorizar(grupo, ["a", "b", "c", "d"])
        self.assertEqual(v.por_segundo, 2)
        self.assertEqual(len(self.buscados(v, 10)), 4)


class Trabalhadores(unittest.TestCase):
    def test_uma_thread_ate_cinco_por_segundo_e_mais_acima_disso_com_teto(self):
        quantas = {por_segundo: Varredor(por_segundo).trabalhadores for por_segundo in (1, 2, 5, 6, 15, 30, 100)}
        self.assertEqual(quantas, {1: 1, 2: 1, 5: 1, 6: 2, 15: 5, 30: 8, 100: 8})

    def test_pedir_cria_as_threads_ajudantes_e_nao_repete(self):
        v, _ = criar_varredor({"u0": R(200, {"x": 0}, None)}, por_segundo=12)
        with mock.patch.object(threading.Thread, "start"):
            v.pedir("g", fabrica({"c0": "u0"}))
        self.assertEqual(len(v._ajudantes), 3)   # 12 por segundo: 4 threads no total, uma é a principal

    def test_cada_thread_espera_o_que_cabe_a_ela_do_teto(self):
        v, _ = criar_varredor({f"u{i}": R(200, {"x": i}, None) for i in range(3)}, por_segundo=12)
        with mock.patch.object(threading.Thread, "start"):
            v.pedir("g", fabrica({f"c{i}": f"u{i}" for i in range(3)}))
        esperas = []

        def dormir(segundos):
            esperas.append(segundos)
            if len(esperas) == 4:
                raise Thread.Parar

        v.dormir = dormir
        with self.assertRaises(Thread.Parar):
            v._rodar()
        self.assertEqual(esperas, [4 / 12] * 3 + [1.0])   # 4 threads dividem o teto: cada uma espera 4/12 s

    def test_o_arquivo_que_uma_thread_buscou_fica_reservado_para_as_outras(self):
        v, _ = criar_varredor({}, por_segundo=10)
        pedidos = []

        def buscar(url, etag=None):
            pedidos.append(url)
            if url == "ua":
                v.passo()   # outra thread, enquanto a rede de "ua" ainda não respondeu
            return R(200, {"x": 1}, None)

        v.buscar = buscar
        with mock.patch.object(threading.Thread, "start"):
            v.pedir("g", fabrica({"a": "ua", "b": "ub"}))
        v.passo()
        self.assertEqual(pedidos, ["ua", "ub"])   # sem a reserva, a segunda thread buscaria "ua" de novo


class Persistencia(unittest.TestCase):
    """Com uma `pasta`, os resumos sobrevivem a uma reinicialização: o mapa nasce preenchido e cada arquivo espera a hora dele."""

    def criar(self, pasta, respostas):
        relogio = Relogio()
        return Varredor(2, buscar=Fonte(respostas), relogio=relogio, dormir=lambda s: None, pasta=pasta), relogio

    def pedir(self, v, f):
        with mock.patch.object(threading.Thread, "start"):
            return v.pedir(("cidades", "oficial", "1"), f)

    def test_o_resumo_volta_do_disco_com_o_etag_e_nao_busca_antes_da_hora(self):
        with tempfile.TemporaryDirectory() as pasta:
            v, relogio = self.criar(pasta, {"ua": R(200, {"x": 1}, '"e1"')})
            self.pedir(v, fabrica({"a": "ua", "b": "ub"}, intervalo=600))
            self.assertTrue(v.passo())
            v.salvar()
            self.assertEqual([n for n in os.listdir(pasta) if n.endswith(".json")].__len__(), 1)

            novo, relogio2 = self.criar(pasta, {"ua": R(304, None, '"e1"'), "ub": R(200, {"x": 2}, '"e2"')})
            relogio2.agora = relogio.agora + 100   # o servidor ficou parado por 100 s
            grupo = self.pedir(novo, fabrica({"a": "ua", "b": "ub"}, intervalo=600))
            self.assertEqual(novo.resumos(grupo)["a"], ({"x": 1}, 1000.0, 200))   # já está no mapa, sem nenhuma busca
            self.assertEqual(novo.resumos(grupo)["b"][0], None)                    # o que nunca chegou segue pendente
            novo.passo()
            self.assertEqual(novo.buscar.pedidos, [("ub", None)])                  # "a" ainda não venceu; só o pendente é buscado
            relogio2.agora += 600
            self.pedir(novo, fabrica({"a": "ua", "b": "ub"}, intervalo=600))   # alguém voltou a olhar (sem pedido, o grupo fica ocioso)
            novo.passo()
            self.assertEqual(novo.buscar.pedidos[-1], ("ua", '"e1"'))              # na hora dele, revalida com o ETag guardado

    def test_arquivo_estragado_ou_de_outra_forma_e_ignorado(self):
        with tempfile.TemporaryDirectory() as pasta:
            v, _ = self.criar(pasta, {"ua": R(200, {"x": 1}, None)})
            self.pedir(v, fabrica({"a": "ua"}))
            v.passo()
            v.salvar()
            arquivo = os.path.join(pasta, os.listdir(pasta)[0])
            for conteudo in ("não é json", json.dumps({"resumos": {"a": "lixo"}}), json.dumps([1, 2]), json.dumps({"resumos": {"a": [1, 2, 3]}})):
                with open(arquivo, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                novo, _ = self.criar(pasta, {})
                grupo = self.pedir(novo, fabrica({"a": "ua"}))
                self.assertEqual(novo.resumos(grupo)["a"][0], None)

    def test_sem_pasta_nada_vai_para_o_disco_e_pasta_sem_permissao_nao_derruba(self):
        v, _ = self.criar(None, {"ua": R(200, {"x": 1}, None)})
        self.pedir(v, fabrica({"a": "ua"}))
        v.passo()
        v.salvar()   # sem pasta: não faz nada
        with tempfile.NamedTemporaryFile() as arquivo:   # "pasta" que é um arquivo: criar a pasta falha
            v, _ = self.criar(arquivo.name, {"ua": R(200, {"x": 1}, None)})
            self.pedir(v, fabrica({"a": "ua"}))
            v.passo()
            v.salvar()   # o erro de disco não sobe
            self.assertTrue(v._sujos)   # e fica marcado para tentar de novo

    def test_a_thread_grava_ao_ficar_ociosa(self):
        with tempfile.TemporaryDirectory() as pasta:
            v, relogio = self.criar(pasta, {"ua": R(200, {"x": 1}, None)})
            self.pedir(v, fabrica({"a": "ua"}))
            v.passo()
            relogio.agora += varredor.OCIOSO_S + 1   # ninguém olha há muito tempo
            v._rodar()
            self.assertEqual(len([n for n in os.listdir(pasta) if n.endswith(".json")]), 1)

