"""Testes de `contador/servidor/rotas/compartilhamento.py`, inclusive com o servidor HTTP de verdade."""
import gzip
import http.client
import json
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from contador.caminhos import WEB
from contador.divulgacao import compartilhar, imagem
from contador.servidor import estado, rotas
from contador.servidor.handler import Handler
from contador.servidor.rotas import compartilhamento
from contador.tse import catalogo
from tests.dados import CONFIG_MUNICIPIOS, ler_png, tse


class Pagina(unittest.TestCase):
    def setUp(self):
        compartilhamento._CARTOES.clear()
        self.addCleanup(compartilhamento._CARTOES.clear)

    def html(self, consulta, host="127.0.0.1:8000"):
        return compartilhamento.pagina(consulta, {"Host": host}).decode()

    def test_incorporada_ja_nasce_enxuta_e_fora_dos_buscadores(self):
        incorporada = self.html({"embed": ["1"]})
        self.assertIn('<html lang="pt-BR" class="embed">', incorporada)
        self.assertIn('<meta name="robots" content="noindex">', incorporada)
        comum = self.html({})
        self.assertNotIn('class="embed"', comum)
        self.assertNotIn("noindex", comum)

    def test_sem_selecao_usa_o_padrao(self):
        pagina = self.html({})
        self.assertNotIn(compartilhamento.MARCA_DO_HEAD, pagina)
        self.assertIn('property="og:image" content="http://127.0.0.1:8000/og.png"', pagina)
        self.assertIn(compartilhar.DESCRICAO_PADRAO, pagina)

    def test_a_selecao_do_link_vai_para_o_titulo_e_a_imagem(self):
        pagina = self.html({"cargo": ["governador"], "uf": ["sp"], "turno": ["2"], "ambiente": ["simulado"]})
        self.assertIn("Governador · São Paulo · 2º turno · Contador de votos 2026", pagina)
        self.assertIn("og.png?cargo=governador&amp;uf=sp&amp;turno=2&amp;ambiente=simulado", pagina)

    def test_descricao_usa_so_o_que_ja_esta_no_cache(self):
        url = catalogo.montar_url("oficial", "presidente", "br", 1)
        with mock.patch.object(estado.CACHE, "obter", side_effect=AssertionError("não pode consultar o TSE")):
            self.assertIn(compartilhar.DESCRICAO_PADRAO, self.html({"cargo": ["presidente"]}))
            with mock.patch.object(estado.CACHE, "espiar", return_value=tse([700, 300], apuradas=500)) as espiar:
                self.assertIn("ANA LIMA 70,00%", self.html({"cargo": ["presidente"]}))
        self.assertEqual(espiar.call_args.args[0], url)

    def test_consulta_invalida_nao_aparece_na_pagina(self):
        pagina = self.html({"cargo": ['"><script>alert(1)</script>'], "uf": ["x"]})
        self.assertNotIn("alert(1)", pagina)
        self.assertIn('og:image" content="http://127.0.0.1:8000/og.png"', pagina)

    def test_host_estranho_nao_vira_url(self):
        pagina = self.html({}, host='evil.com"><script>')
        self.assertNotIn("evil.com", pagina)
        self.assertNotIn("og:image", pagina)

    def test_cidade_so_com_nome_quando_a_lista_ja_esta_no_cache(self):
        config = catalogo.url_municipios("oficial", "governador", 1)
        consulta = {"cargo": ["governador"], "uf": ["sp"], "municipio": ["62910"]}
        with mock.patch.object(estado.CACHE, "espiar", side_effect=lambda url: CONFIG_MUNICIPIOS if url == config else None):
            self.assertIn("Governador · Campinas (SP) · 1º turno", self.html(consulta))
        with mock.patch.object(estado.CACHE, "espiar", return_value=None):
            self.assertIn("Governador · São Paulo · 1º turno", self.html(consulta))


class CartaoDoPlacar(unittest.TestCase):
    def setUp(self):
        compartilhamento._CARTOES.clear()
        self.addCleanup(compartilhamento._CARTOES.clear)

    def pedir(self, consulta, dados=None, status=200):
        with mock.patch.object(estado.CACHE, "obter", return_value=(dados, status, 0)):
            return rotas.cartao_do_placar(consulta)

    def test_devolve_png_com_cache_publico(self):
        status, tipo, corpo, extras = self.pedir({"ambiente": ["simulado"]}, tse([700, 300]))
        self.assertEqual((status, tipo, extras), (200, "image/png", {"Cache-Control": "public, max-age=60"}))
        self.assertEqual(ler_png(corpo)[:2], (imagem.LARGURA_OG, imagem.ALTURA_OG))

    def test_sem_dados_ainda_devolve_imagem(self):
        status, tipo, corpo, _ = self.pedir({}, None, status=404)
        self.assertEqual((status, tipo), (200, "image/png"))
        ler_png(corpo)

    def test_selecao_invalida_da_400(self):
        for consulta in ({"cargo": ["x"]}, {"uf": ["../x"]}, {"turno": ["7"]}, {"ambiente": ["http://x"]}, {"municipio": ["62910"]}):
            with self.subTest(consulta=consulta):
                self.assertEqual(self.pedir(consulta, tse([1, 1]))[0], 400)

    def test_cidade_fora_da_lista_do_tse_da_400_sem_consultar_a_cidade(self):
        config = catalogo.url_municipios("simulado", "governador", 1)
        pedidos = []

        def obter(url, ttl=None):
            pedidos.append(url)
            return (CONFIG_MUNICIPIOS, 200, 0) if url == config else (None, 404, 0)

        consulta = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"], "municipio": ["99999"]}
        with mock.patch.object(estado.CACHE, "obter", side_effect=obter):
            self.assertEqual(rotas.cartao_do_placar(consulta)[0], 400)
        self.assertEqual(pedidos, [config])

    def test_mesma_totalizacao_reaproveita_a_imagem(self):
        with mock.patch.object(compartilhar, "cartao", wraps=compartilhar.cartao) as desenhar:
            self.pedir({}, tse([700, 300], apuradas=500))
            self.pedir({}, tse([700, 300], apuradas=500))
            self.assertEqual(desenhar.call_count, 1)
            self.pedir({}, tse([710, 310], apuradas=600))
            self.assertEqual(desenhar.call_count, 2)

    def test_guarda_no_maximo_alguns_cartoes(self):
        with mock.patch.object(compartilhamento, "MAX_CARTOES", 3), mock.patch.object(compartilhar, "cartao", return_value=b"png"):
            for i in range(6):
                self.pedir({"uf": ["br"]}, tse([700, 300], apuradas=100 + i))
        self.assertEqual(len(compartilhamento._CARTOES), 3)


class ServidorDeVerdade(unittest.TestCase):
    """O Handler de verdade, num servidor local de porta livre: nada sai da máquina."""

    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.porta = cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def pedir(self, caminho, metodo="GET", cabecalhos=None):
        conexao = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        conexao.request(metodo, caminho, headers=cabecalhos or {})
        resposta = conexao.getresponse()
        corpo = resposta.read()
        conexao.close()
        return resposta, corpo

    def test_pagina_e_saude(self):
        resposta, corpo = self.pedir("/")
        self.assertEqual((resposta.status, resposta.getheader("Cache-Control")), (200, "no-store"))
        self.assertIn(b"<title>Contador de votos 2026</title>", corpo)
        self.assertIn(f"http://127.0.0.1:{self.porta}/og.png".encode(), corpo)
        self.assertEqual(self.pedir("/saude")[1], b"ok")
        self.assertEqual(self.pedir("/nada")[0].status, 404)

    def test_head_responde_como_get_sem_corpo(self):
        get, corpo = self.pedir("/")
        head, vazio = self.pedir("/", "HEAD")
        self.assertEqual((head.status, vazio), (200, b""))
        self.assertEqual(head.getheader("Content-Length"), str(len(corpo)))
        self.assertEqual(self.pedir("/saude", "HEAD")[0].status, 200)

    def test_manifesto_icones_e_service_worker(self):
        resposta, corpo = self.pedir("/manifest.webmanifest")
        self.assertEqual(resposta.getheader("Content-Type"), "application/manifest+json; charset=utf-8")
        manifesto = json.loads(corpo)
        self.assertEqual((manifesto["display"], manifesto["start_url"]), ("standalone", "/"))
        for icone in manifesto["icons"]:
            png = self.pedir(icone["src"])[1]
            self.assertEqual(ler_png(png)[0], int(icone["sizes"].split("x")[0]))
        resposta, corpo = self.pedir("/sw.js")
        self.assertEqual(resposta.getheader("Content-Type"), "text/javascript; charset=utf-8")
        self.assertIn(b'addEventListener("fetch"', corpo)

    def test_service_worker_nunca_guarda_dados(self):
        sw = self.pedir("/sw.js")[1].decode()
        self.assertIn('pedido.mode === "navigate" && url.pathname === "/"', sw)      # a abertura da página passa pelo cache
        self.assertIn(r"const ARQUIVOS_DA_PAGINA = /^\/(estilo\.css|js\/[a-z0-9-]+\.js)$/;", sw)   # e só estes arquivos; /api nunca casa
        self.assertEqual(sw.count(".put("), 1)                 # a única cópia guardada é da própria página ou de um destes arquivos
        self.assertIn(".put(chave, copia)", sw)

    def test_estilo_e_scripts_saem_da_pasta_web(self):
        resposta, corpo = self.pedir("/estilo.css")
        self.assertEqual((resposta.status, resposta.getheader("Content-Type")), (200, "text/css; charset=utf-8"))
        self.assertEqual(corpo, (WEB / "estilo.css").read_bytes())
        resposta, corpo = self.pedir("/js/base.js")
        self.assertEqual((resposta.status, resposta.getheader("Content-Type")), (200, "text/javascript; charset=utf-8"))
        self.assertEqual(corpo, (WEB / "js" / "base.js").read_bytes())
        for caminho in ("/js/nao-existe.js", "/js/../app.py", "/js/%2e%2e/app.py", "/js/Base.js", "/js/base.js/x", "/js/", "/estilo.css.map", "/web/estilo.css", "/web/js/base.js"):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.pedir(caminho)[0].status, 404)

    def test_pagina_so_aponta_para_arquivos_que_existem(self):
        html = self.pedir("/")[1].decode()
        caminhos = re.findall(r'(?:src|href)="(/(?:js/|estilo)[^"]+)"', html)
        self.assertGreater(len(caminhos), 10)
        for caminho in caminhos:
            with self.subTest(caminho=caminho):
                self.assertEqual(self.pedir(caminho)[0].status, 200)

    def test_arquivos_da_web_revalidam_com_etag_e_aceitam_gzip(self):
        resposta, corpo = self.pedir("/js/painel.js")
        etag = resposta.getheader("ETag")
        self.assertEqual((resposta.getheader("Cache-Control"), resposta.getheader("Content-Encoding")), ("no-cache", None))
        igual, vazio = self.pedir("/js/painel.js", cabecalhos={"If-None-Match": etag})
        self.assertEqual((igual.status, vazio), (304, b""))
        outro, _ = self.pedir("/js/painel.js", cabecalhos={"If-None-Match": 'W/"outro"'})
        self.assertEqual(outro.status, 200)
        zip_, comprimido = self.pedir("/js/painel.js", cabecalhos={"Accept-Encoding": "gzip, deflate"})
        self.assertEqual((zip_.getheader("Content-Encoding"), zip_.getheader("Vary")), ("gzip", "Accept-Encoding"))
        self.assertEqual(gzip.decompress(comprimido), corpo)
        self.assertLess(len(comprimido), len(corpo))
        self.assertEqual(self.pedir("/geo/sp.json", cabecalhos={"Accept-Encoding": "gzip"})[0].getheader("Content-Encoding"), "gzip")

    def test_og_png_pelo_http(self):
        with mock.patch.object(estado.CACHE, "obter", return_value=(tse([700, 300]), 200, 0)):
            resposta, corpo = self.pedir("/og.png?ambiente=simulado&cargo=presidente&uf=br")
        self.assertEqual((resposta.status, resposta.getheader("Content-Type")), (200, "image/png"))
        ler_png(corpo)
        self.assertEqual(self.pedir("/og.png?cargo=x")[0].status, 400)
