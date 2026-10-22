import gzip
import http.client
import json
import re
import struct
import threading
import unittest
import zlib
from http.server import ThreadingHTTPServer
from unittest import mock

import compartilhar
import contador
import imagem
import servidor
from test_contador import CONFIG_MUNICIPIOS
from test_historico import tse


def ler_png(dados):
    """(largura, altura, pixels RGB) de um PNG de 8 bits RGB sem entrelaçamento, conferindo assinatura e CRC."""
    assert dados[:8] == b"\x89PNG\r\n\x1a\n", "assinatura"
    posicao, blocos = 8, {}
    while posicao < len(dados):
        tamanho, tipo = struct.unpack(">I4s", dados[posicao:posicao + 8])
        corpo = dados[posicao + 8:posicao + 8 + tamanho]
        crc = struct.unpack(">I", dados[posicao + 8 + tamanho:posicao + 12 + tamanho])[0]
        assert crc == zlib.crc32(tipo + corpo) & 0xFFFFFFFF, f"CRC de {tipo}"
        blocos.setdefault(tipo, []).append(corpo)
        posicao += 12 + tamanho
    largura, altura, profundidade, tipo_cor, _, _, entrelacado = struct.unpack(">IIBBBBB", blocos[b"IHDR"][0])
    assert (profundidade, tipo_cor, entrelacado) == (8, 2, 0)
    bruto = zlib.decompress(b"".join(blocos[b"IDAT"]))
    assert len(bruto) == altura * (1 + 3 * largura)
    linhas = [bruto[i * (1 + 3 * largura) + 1:(i + 1) * (1 + 3 * largura)] for i in range(altura)]
    assert all(bruto[i * (1 + 3 * largura)] == 0 for i in range(altura)), "filtro 0"
    assert b"IEND" in blocos
    return largura, altura, linhas


class Imagem(unittest.TestCase):
    def test_png_valido(self):
        tela = imagem.Tela(40, 20, (1, 2, 3))
        tela.retangulo(5, 5, 10, 4, (255, 0, 0))
        largura, altura, linhas = ler_png(tela.png())
        self.assertEqual((largura, altura), (40, 20))
        self.assertEqual(linhas[0][:3], bytes((1, 2, 3)))
        self.assertEqual(linhas[5][5 * 3:5 * 3 + 3], bytes((255, 0, 0)))
        self.assertEqual(linhas[5][15 * 3:15 * 3 + 3], bytes((1, 2, 3)))  # fora do retângulo

    def test_retangulo_fora_da_tela_e_cortado(self):
        tela = imagem.Tela(10, 10)
        tela.retangulo(-5, -5, 8, 8, (9, 9, 9))
        tela.retangulo(8, 8, 50, 50, (7, 7, 7))
        tela.retangulo(20, 20, 5, 5, (1, 1, 1))
        _, _, linhas = ler_png(tela.png())
        self.assertEqual(linhas[0][:3], bytes((9, 9, 9)))
        self.assertEqual(linhas[9][27:30], bytes((7, 7, 7)))

    def test_fonte_bem_formada(self):
        for letra, linhas in imagem.FONTE.items():
            with self.subTest(letra=letra):
                self.assertEqual(len(linhas), imagem.ALTURA_GLIFO)
                self.assertTrue(all(len(linha) == imagem.LARGURA_GLIFO and set(linha) <= {".", "#"} for linha in linhas))

    def test_tem_todas_as_letras_numeros_e_a_pontuacao_usada(self):
        esperado = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:;-+%/()·º!?'")
        self.assertEqual(esperado - set(imagem.FONTE), set())

    def test_acentos_viram_marcas_sobre_a_letra(self):
        self.assertEqual(imagem.glifos("Ação"), [("A", []), ("C", ["̧"]), ("A", ["̃"]), ("O", [])])
        self.assertEqual(imagem.glifos("é"), [("E", ["́"])])

    def test_o_que_a_fonte_nao_tem_vira_interrogacao(self):
        self.assertEqual([letra for letra, _ in imagem.glifos("a☃b")], ["A", "?", "B"])

    def test_texto_desenha_a_letra_e_o_acento_acima(self):
        tela = imagem.Tela(40, 40)
        tela.texto(10, 20, "Á", (255, 255, 255), 2)
        _, _, linhas = ler_png(tela.png())
        branco = bytes((255, 255, 255))
        acesos = {(x, y) for y, linha in enumerate(linhas) for x in range(40) if linha[x * 3:x * 3 + 3] == branco}
        self.assertTrue(any(y >= 20 for _, y in acesos))      # a letra
        self.assertTrue(any(16 <= y < 20 for _, y in acesos))  # o acento: duas linhas de escala 2 acima
        self.assertFalse(any(y < 16 for _, y in acesos))

    def test_larguras_e_alinhamento(self):
        self.assertEqual(imagem.largura_do_texto("AB", 2), (5 + 1 + 5) * 2)
        self.assertEqual(imagem.largura_do_texto("", 3), 0)
        tela = imagem.Tela(100, 20)
        usada = tela.texto(90, 0, "AB", (255, 255, 255), 2, "direita")
        self.assertEqual(usada, 22)
        _, _, linhas = ler_png(tela.png())
        self.assertTrue(any(linha[(90 - 22) * 3 + i] for linha in linhas for i in range(66)))
        self.assertFalse(any(linha[91 * 3 + i] for linha in linhas for i in range(27)))

    def test_texto_que_cabe_diminui_e_depois_corta(self):
        self.assertEqual(imagem.texto_que_cabe("OI", 1000), (6, "OI"))
        escala, texto = imagem.texto_que_cabe("A" * 20, imagem.largura_do_texto("A" * 20, 4))
        self.assertEqual((escala, texto), (4, "A" * 20))
        escala, texto = imagem.texto_que_cabe("PALAVRA" * 10, 200)
        self.assertEqual(escala, 2)
        self.assertTrue(texto.endswith("...") and imagem.largura_do_texto(texto, 2) <= 200)

    def test_icones_nos_tamanhos_pedidos(self):
        for lado, mascara in ((192, False), (512, False), (512, True)):
            with self.subTest(lado=lado, mascara=mascara):
                largura, altura, linhas = ler_png(imagem.icone(lado, mascara))
                self.assertEqual((largura, altura), (lado, lado))
                self.assertIn(bytes((255, 255, 255)), linhas[lado // 2] + linhas[int(lado * 0.6)])  # o visto
        _, _, linhas = ler_png(imagem.icone(192))
        self.assertEqual(linhas[0][:3], bytes((13, 13, 13)))  # canto arredondado fica transparente-ish (fundo da página)


class Compartilhar(unittest.TestCase):
    def test_cor_segue_o_partido(self):
        self.assertEqual(compartilhar.cor_do_partido("PT"), imagem.hex_rgb("#e66767"))
        self.assertEqual(compartilhar.cor_do_partido("PL"), imagem.hex_rgb("#3987e5"))
        self.assertEqual(compartilhar.cor_do_partido("União"), imagem.hex_rgb("#9085e9"))
        self.assertEqual(compartilhar.cor_do_partido("XYZ"), imagem.hex_rgb("#898781"))
        self.assertEqual(compartilhar.cor_do_partido(None), imagem.hex_rgb("#898781"))

    def test_titulo(self):
        self.assertEqual(compartilhar.titulo_da_selecao("presidente", "br", 1), "Presidente · Brasil · 1º turno")
        self.assertEqual(compartilhar.titulo_da_selecao("governador", "sp", 2, "Campinas"), "Governador · Campinas (SP) · 2º turno")
        self.assertEqual(compartilhar.titulo_da_selecao("senador", "mg", 1), "Senador · Minas Gerais · 1º turno")

    def test_descricao(self):
        resumo = servidor.resumir(tse([700, 300], apuradas=500), 3)
        self.assertEqual(compartilhar.descricao_do_placar(resumo), "ANA LIMA 70,00% · BRUNO CASTRO 30,00% · 50,00% das seções apuradas")
        final = servidor.resumir(tse([700, 300], final=True), 3)
        self.assertTrue(compartilhar.descricao_do_placar(final).endswith("apuração final"))
        self.assertEqual(compartilhar.descricao_do_placar(None), compartilhar.DESCRICAO_PADRAO)
        self.assertEqual(compartilhar.descricao_do_placar(servidor.resumir(tse([0, 0], apuradas=0), 3)), compartilhar.DESCRICAO_PADRAO)

    def test_base_publica(self):
        self.assertEqual(compartilhar.base_publica("https://votos.exemplo.com/", {"Host": "x"}), "https://votos.exemplo.com")
        self.assertEqual(compartilhar.base_publica("", {"Host": "127.0.0.1:8000"}), "http://127.0.0.1:8000")
        self.assertEqual(compartilhar.base_publica("", {"Host": "votos.exemplo.com", "X-Forwarded-Proto": "https"}), "https://votos.exemplo.com")
        self.assertEqual(compartilhar.base_publica("", {"Host": "votos.exemplo.com", "X-Forwarded-Proto": "javascript"}), "http://votos.exemplo.com")
        for ruim in ("", "a b", "evil.com/<script>", 'x"onload="y', "a" * 300):
            with self.subTest(host=ruim):
                self.assertEqual(compartilhar.base_publica("", {"Host": ruim}), "")

    def test_meta_tags_escapam_tudo(self):
        meta = compartilhar.meta_tags("https://x.com", "cargo=presidente", 'Ataque "><script>alert(1)</script>', "a & b <i>")
        self.assertNotIn("<script>", meta)
        self.assertIn("&quot;&gt;&lt;script&gt;", meta)
        self.assertIn("a &amp; b &lt;i&gt;", meta)
        self.assertIn('content="https://x.com/og.png?cargo=presidente"', meta)
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', meta)

    def test_sem_base_nao_ha_url_absoluta(self):
        meta = compartilhar.meta_tags("", "")
        self.assertNotIn("og:image", meta)
        self.assertIn("og:title", meta)

    def test_cartao_com_e_sem_dados(self):
        resumo = servidor.resumir(tse([700, 300], apuradas=500, situacoes={"13": "Eleito"}), 4)
        for dados in (resumo, None):
            largura, altura, linhas = ler_png(compartilhar.cartao("Presidente · Brasil · 1º turno", dados, "simulado"))
            self.assertEqual((largura, altura), (imagem.LARGURA_OG, imagem.ALTURA_OG))
        _, _, linhas = ler_png(compartilhar.cartao("Presidente · Brasil · 1º turno", resumo))
        pixels = b"".join(linhas)
        self.assertIn(bytes(compartilhar.cor_do_partido("PT")) * 50, pixels)   # a barra do PT
        self.assertIn(bytes(compartilhar.cor_do_partido("PL")) * 50, pixels)

    def test_titulo_enorme_nao_estoura(self):
        _, _, linhas = ler_png(compartilhar.cartao("X" * 500, None))
        self.assertEqual(len(linhas), imagem.ALTURA_OG)


class Pagina(unittest.TestCase):
    def setUp(self):
        servidor._CARTOES.clear()
        self.addCleanup(servidor._CARTOES.clear)

    def html(self, consulta, host="127.0.0.1:8000"):
        return servidor.pagina(consulta, {"Host": host}).decode()

    def test_sem_selecao_usa_o_padrao(self):
        pagina = self.html({})
        self.assertNotIn(servidor.MARCA_DO_HEAD, pagina)
        self.assertIn('property="og:image" content="http://127.0.0.1:8000/og.png"', pagina)
        self.assertIn(compartilhar.DESCRICAO_PADRAO, pagina)

    def test_a_selecao_do_link_vai_para_o_titulo_e_a_imagem(self):
        pagina = self.html({"cargo": ["governador"], "uf": ["sp"], "turno": ["2"], "ambiente": ["simulado"]})
        self.assertIn("Governador · São Paulo · 2º turno · Contador de votos 2026", pagina)
        self.assertIn("og.png?cargo=governador&amp;uf=sp&amp;turno=2&amp;ambiente=simulado", pagina)

    def test_descricao_usa_so_o_que_ja_esta_no_cache(self):
        url = contador.montar_url("oficial", "presidente", "br", 1)
        with mock.patch.object(servidor.CACHE, "obter", side_effect=AssertionError("não pode consultar o TSE")):
            self.assertIn(compartilhar.DESCRICAO_PADRAO, self.html({"cargo": ["presidente"]}))
            with mock.patch.object(servidor.CACHE, "espiar", return_value=tse([700, 300], apuradas=500)) as espiar:
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
        config = contador.url_municipios("oficial", "governador", 1)
        consulta = {"cargo": ["governador"], "uf": ["sp"], "municipio": ["62910"]}
        with mock.patch.object(servidor.CACHE, "espiar", side_effect=lambda url: CONFIG_MUNICIPIOS if url == config else None):
            self.assertIn("Governador · Campinas (SP) · 1º turno", self.html(consulta))
        with mock.patch.object(servidor.CACHE, "espiar", return_value=None):
            self.assertIn("Governador · São Paulo · 1º turno", self.html(consulta))


class CartaoDoPlacar(unittest.TestCase):
    def setUp(self):
        servidor._CARTOES.clear()
        self.addCleanup(servidor._CARTOES.clear)

    def pedir(self, consulta, dados=None, status=200):
        with mock.patch.object(servidor.CACHE, "obter", return_value=(dados, status, 0)):
            return servidor.cartao_do_placar(consulta)

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
        config = contador.url_municipios("simulado", "governador", 1)
        pedidos = []

        def obter(url, ttl=None):
            pedidos.append(url)
            return (CONFIG_MUNICIPIOS, 200, 0) if url == config else (None, 404, 0)

        consulta = {"ambiente": ["simulado"], "cargo": ["governador"], "uf": ["sp"], "municipio": ["99999"]}
        with mock.patch.object(servidor.CACHE, "obter", side_effect=obter):
            self.assertEqual(servidor.cartao_do_placar(consulta)[0], 400)
        self.assertEqual(pedidos, [config])

    def test_mesma_totalizacao_reaproveita_a_imagem(self):
        with mock.patch.object(compartilhar, "cartao", wraps=compartilhar.cartao) as desenhar:
            self.pedir({}, tse([700, 300], apuradas=500))
            self.pedir({}, tse([700, 300], apuradas=500))
            self.assertEqual(desenhar.call_count, 1)
            self.pedir({}, tse([710, 310], apuradas=600))
            self.assertEqual(desenhar.call_count, 2)

    def test_guarda_no_maximo_alguns_cartoes(self):
        with mock.patch.object(servidor, "MAX_CARTOES", 3), mock.patch.object(compartilhar, "cartao", return_value=b"png"):
            for i in range(6):
                self.pedir({"uf": ["br"]}, tse([700, 300], apuradas=100 + i))
        self.assertEqual(len(servidor._CARTOES), 3)


class ServidorDeVerdade(unittest.TestCase):
    """O Handler de verdade, num servidor local de porta livre: nada sai da máquina."""

    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Handler)
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
        self.assertEqual(corpo, (servidor.WEB / "estilo.css").read_bytes())
        resposta, corpo = self.pedir("/js/base.js")
        self.assertEqual((resposta.status, resposta.getheader("Content-Type")), (200, "text/javascript; charset=utf-8"))
        self.assertEqual(corpo, (servidor.WEB / "js" / "base.js").read_bytes())
        for caminho in ("/js/nao-existe.js", "/js/../servidor.py", "/js/%2e%2e/servidor.py", "/js/Base.js", "/js/base.js/x", "/js/", "/estilo.css.map", "/web/estilo.css", "/web/js/base.js"):
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
        with mock.patch.object(servidor.CACHE, "obter", return_value=(tse([700, 300]), 200, 0)):
            resposta, corpo = self.pedir("/og.png?ambiente=simulado&cargo=presidente&uf=br")
        self.assertEqual((resposta.status, resposta.getheader("Content-Type")), (200, "image/png"))
        ler_png(corpo)
        self.assertEqual(self.pedir("/og.png?cargo=x")[0].status, 400)


if __name__ == "__main__":
    unittest.main()
