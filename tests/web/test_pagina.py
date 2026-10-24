"""Testes de `web/ (index.html, estilo.css, scripts e service worker)`."""
import json
import re
import shutil
import subprocess
import unittest

from contador.caminhos import WEB
from contador.recursos import municipios
from contador.tse import catalogo
from tools import gerar_mapa


HTML = (WEB / "index.html").read_text(encoding="utf-8")


CSS = (WEB / "estilo.css").read_text(encoding="utf-8")


ARQUIVOS_JS = re.findall(r'<script defer src="/js/([a-z0-9-]+)\.js"></script>', HTML)


def script():
    """Os scripts da página juntos, na ordem de carga (compartilham o mesmo escopo global)."""
    return "\n".join((WEB / "js" / f"{nome}.js").read_text(encoding="utf-8") for nome in ARQUIVOS_JS)


def chaves_do_objeto(nome):
    """Chaves (siglas) do objeto JavaScript `const nome = { sp: ..., rj: ... }`, no nível de cima."""
    corpo = re.search(rf"const {nome} = \{{(.*?)\n\}};", script(), re.S).group(1)
    return re.findall(r'\b([a-z]{2}): [{"]', corpo)


class Pagina(unittest.TestCase):
    def test_todas_as_ufs_tem_nome_e_contorno(self):
        self.assertEqual(sorted(chaves_do_objeto("UFS")), sorted(catalogo.UFS))
        self.assertEqual(sorted(chaves_do_objeto("MAPA_UFS")), sorted(catalogo.UFS))

    def test_contornos_sao_caminhos_fechados(self):
        for sigla, d in re.findall(r'(?:^|\n)\s*([a-z]{2}): \{"d":"([^"]+)"', script()):
            with self.subTest(uf=sigla):
                self.assertTrue(d.startswith("M") and d.endswith("z"))
                self.assertRegex(d, r"^[Mlz0-9 .\-]+$")

    def test_sem_dependencia_externa(self):
        # Scripts e estilo vêm do próprio servidor (pasta web/), nunca de um CDN.
        self.assertEqual(sorted(re.findall(r'<script[^>]+src="([^"]+)"', HTML)), sorted(f"/js/{nome}.js" for nome in ARQUIVOS_JS))
        self.assertEqual(re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', HTML), ["/estilo.css"])
        self.assertNotRegex(HTML, r"<script>")
        self.assertNotRegex(HTML, r"<style")
        for texto in (HTML, CSS, script()):
            self.assertNotIn("@import", texto)
            self.assertNotRegex(texto, r"url\(\s*['\"]?(?:https?:)?//")
            self.assertNotRegex(texto, r"\b(?:src|action)=[\"'](?:https?:)?//")

    def test_foto_do_candidato_so_vem_de_https_e_nao_manda_referer(self):
        # A foto é baixada pelo navegador direto do TSE: só https, sem Referer, preguiçosa, e some se não carregar.
        corpo = re.search(r"function fotoDoCandidato\(c\) \{(.*?)\n\}", script(), re.S).group(1)
        for trecho in ('startsWith("https://")', 'referrerpolicy: "no-referrer"', 'loading: "lazy"', 'addEventListener("error"'):
            self.assertIn(trecho, corpo)

    def test_comparacao_no_endereco_aceita_so_o_que_a_pagina_entende(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        base = (WEB / "js" / "base.js").read_text(encoding="utf-8")
        trechos = [re.search(rf"const {nome} = \{{.*?\n\}};", base, re.S).group(0) for nome in ("CARGOS", "UFS")]
        trechos.append(re.search(r"const temChave = .*?\nconst escreverComparacao = [^\n]*", base, re.S).group(0))
        programa = "const vm = require('vm'); const c = vm.createContext({}); vm.runInContext(process.argv[1], c); process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], c)));"
        casos = ["governador:sp:1", "presidente:br:2", "governador:sp:1:62910", "xx:sp:1", "governador:xx:1", "governador:sp:3", "governador:sp:1:123", "", "constructor:sp:1", "governador:sp"]
        consulta = f"[{json.dumps(casos)}.map(lerComparacao), escreverComparacao(lerComparacao('governador:sp:1:62910'))]"
        resultado = subprocess.run([node, "-e", programa, "\n".join(trechos), consulta], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        lidas, escrita = json.loads(resultado.stdout)
        self.assertEqual(lidas[0], {"cargo": "governador", "uf": "sp", "turno": "1", "municipio": ""})
        self.assertEqual(lidas[1]["uf"], "br")
        self.assertEqual(lidas[2]["municipio"], "62910")
        self.assertEqual(lidas[3:], [None] * 7)   # cargo, UF, turno ou município inválidos, vazio, chave de protótipo e turno faltando
        self.assertEqual(escrita, "governador:sp:1:62910")

    def test_contas_do_mapa_por_municipio(self):
        """As funções puras do mapa (caixa do contorno, altura do pico, votos abreviados, votação do candidato) rodando de verdade."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")

        def funcao(nome):
            ini = script().index(f"function {nome}(")
            fundo, i = 0, script().index("{", ini)
            while True:
                fundo += {"{": 1, "}": -1}.get(script()[i], 0)
                i += 1
                if fundo == 0:
                    return script()[ini:i]

        codigo = "\n".join([funcao("caixaDoCaminho"), funcao("percentualNaUf"), re.search(r"const alturaDoPico = [^\n]*", script()).group(0), re.search(r"const abreviarVotos = [^\n]*", script()).group(0)])
        consulta = """[
          caixaDoCaminho("M10 20l5 0 0 7-5 0z"), caixaDoCaminho("M0 0l10 0 0 10-10 0zM-5 -5l1 1-1 0z"),
          alturaDoPico(0), alturaDoPico(100000), alturaDoPico(1e9), abreviarVotos(950), abreviarVotos(13500), abreviarVotos(15800000),
          percentualNaUf({situacao: "lider", lider: {numero: "13", percentual: 55}, segundo: {numero: "22", percentual: 40}}, "22"),
          percentualNaUf({situacao: "lider", lider: {numero: "13", percentual: 55}, segundo: {numero: "22", percentual: 40}}, "99"),
          percentualNaUf({situacao: "zerado"}, "13"), percentualNaUf(null, "13")]"""
        programa = "const vm = require('vm'); const c = vm.createContext({}); vm.runInContext(process.argv[1], c); process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], c)));"
        resultado = subprocess.run([node, "-e", programa, codigo, consulta], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        caixa1, caixa2, zero, cem_mil, enorme, pouco, mil, milhoes, p22, p99, zerado, nulo = json.loads(resultado.stdout)
        self.assertEqual(caixa1, [10, 20, 15, 27])
        self.assertEqual(caixa2, [-5, -5, 10, 10])    # vários anéis no mesmo caminho
        self.assertEqual((zero, round(cem_mil, 1), enorme), (0, 52.0, 230))    # raiz da vantagem, com teto
        self.assertEqual((pouco, mil.replace("\xa0", " "), milhoes), ("950", "14 mil", "15,8 mi"))
        self.assertEqual((p22, p99, zerado, nulo), (40, None, None, None))

    def test_picos_da_vantagem_sobem_do_zero_em_onda_e_o_menu_mostra_a_foto_dos_candidatos(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        fonte = script()
        ini = fonte.index("function alturaAnimada(")
        corpo = fonte[ini:fonte.index("\n}\n", ini) + 3]
        codigo = "\n".join([re.search(r"const ANIMACAO_PICO_MS = [^\n]*", fonte).group(0), re.search(r"const suavizar = [^\n]*", fonte).group(0), corpo])
        consulta = "[alturaAnimada(0, 100, 0, 0), alturaAnimada(0, 100, 300, 200), alturaAnimada(0, 100, 0, 350), alturaAnimada(0, 100, 0, 700), alturaAnimada(0, 100, 0, 5000), alturaAnimada(80, 20, 0, 5000), alturaAnimada(80, 20, 0, 350)]"
        programa = "const vm = require('vm'); const c = vm.createContext({Math}); vm.runInContext(process.argv[1], c); process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], c)));"
        resultado = subprocess.run([node, "-e", programa, codigo, consulta], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        no_inicio, esperando, no_meio, no_fim, depois, encolheu, encolhendo = json.loads(resultado.stdout)
        self.assertEqual((no_inicio, esperando, no_fim, depois, encolheu), (0, 0, 100, 100, 20))   # começa em zero, espera a vez da onda, assenta no alvo
        self.assertTrue(50 < no_meio < 110)                                                         # a meio caminho já passou da metade
        self.assertTrue(20 < encolhendo < 80)                                                       # quando a vantagem cai, desce em vez de pular
        self.assertIn("bm.picos = new Map()", fonte.split("function trocarModoDoMapa")[1].split("\n}\n")[0])   # cada entrada no modo refaz a onda
        self.assertRegex(fonte, r"class: \"com-foto\"[^\n]*\n\s*fotoDoCandidato\(c\)")                # o menu mostra a foto de quem está no duelo
        self.assertRegex(CSS, r"\.mais-mapas-menu button\.com-foto \{ display: flex; \}")

    def test_quem_entra_sem_escolher_turno_cai_no_segundo(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        base = (WEB / "js" / "base.js").read_text(encoding="utf-8")
        trechos = [re.search(rf"const {nome} = \{{.*?\n\}};", base, re.S).group(0) for nome in ("CARGOS", "UFS")]
        trechos.append(re.search(r"const TOP_INICIAL = [^\n]*", base).group(0))
        trechos.append(re.search(r"const estado = \{.*?\n\};", base, re.S).group(0))
        programa = "const vm = require('vm'); const resultado = process.argv.slice(2).map((busca) => { const c = vm.createContext({ params: new URLSearchParams(busca) }); vm.runInContext(process.argv[1], c); return vm.runInContext('[estado.turno, estado.turnoPadrao]', c); }); process.stdout.write(JSON.stringify(resultado));"
        resultado = subprocess.run([node, "-e", programa, "\n".join(trechos), "", "turno=1", "turno=2", "turno=9", "cargo=governador&uf=sp"], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        self.assertEqual(json.loads(resultado.stdout), [["2", True], ["1", False], ["2", False], ["2", False], ["2", True]])   # só o padrão pode cair para o 1º, se o cargo não tiver 2º turno ainda
        painel = (WEB / "js" / "painel.js").read_text(encoding="utf-8")
        self.assertRegex(painel, r'estado\.turnoPadrao && estado\.turno === "2"[^\n]*trocou\("turno", "1", \{ padrao: true \}\)')

    def test_tela_unica_cada_bloco_tem_sua_tela_e_a_pagina_nao_rola(self):
        telas_do_html = set(re.findall(r'data-na-tela="(\w+)"', HTML))
        telas_do_script = set(re.findall(r'\{ id: "(\w+)", rotulo', (WEB / "js" / "telas.js").read_text(encoding="utf-8")))
        self.assertEqual(telas_do_html, telas_do_script)
        self.assertEqual(telas_do_html, {"centro", "placar", "detalhes", "aovivo"})
        self.assertIn('id="barra-telas"', HTML)
        for tela in telas_do_html:   # em celular, cada tela esconde os blocos das outras
            self.assertIn(f'.pagina[data-tela="{tela}"] [data-na-tela]:not([data-na-tela="{tela}"])', CSS)
        self.assertRegex(CSS, r"html:not\(\.embed\), html:not\(\.embed\) body \{ height: 100%; overflow: hidden; \}")
        self.assertRegex(CSS, r"html:not\(\.embed\) \.pagina \{ height: 100dvh;")

    def test_svg_dos_estados_fica_por_cima_do_canvas_com_ordem_explicita(self):
        # No Safari do iPhone o canvas (opacidade animada) ia para cima do SVG e apagava siglas e contornos.
        self.assertRegex(CSS, r"\.mapa-pilha > svg \{ position: relative; z-index: 1; \}")
        self.assertRegex(CSS, r"\.mapa-pilha > \.mapa-canvas \{ position: relative; z-index: 0; \}")

    def test_siglas_dos_estados_tem_tamanho_de_tela_e_contorno_para_aparecer_sobre_as_cores(self):
        rotulos = (WEB / "js" / "mapa-brasil-rotulos.js").read_text(encoding="utf-8")
        self.assertIn('setProperty("--upp"', rotulos)   # unidades do desenho por pixel da tela, atualizado no redimensionamento e no zoom
        self.assertIn('class: "uf-cor"', rotulos)       # embaixo da sigla: o quadradinho do partido de quem lidera e o percentual
        self.assertRegex(CSS, r"text\.uf-sigla \{ font-size: calc\(var\(--upp, 1\.6\) \* 10px\)")
        self.assertRegex(CSS, r"\.mapa-svg text:is\(\.uf-sigla, \.uf-pct\) \{ fill: #fff; stroke: rgba\(0, 0, 0")

    def test_tabela_de_uf_por_codigo_ibge_e_a_mesma_no_script_no_servidor_e_na_ferramenta(self):
        js = re.search(r"const UF_DO_CODIGO_IBGE = \{(.*?)\};", script(), re.S).group(1)
        do_script = dict(re.findall(r'(\d+): "([a-z]{2})"', js))
        self.assertEqual(do_script, municipios.UF_DO_CODIGO_IBGE)
        self.assertEqual(do_script, gerar_mapa.SIGLAS)
        self.assertEqual(sorted(do_script.values()), sorted(catalogo.UFS))

    def test_canvas_dos_municipios_divide_a_celula_com_o_svg_em_vez_de_ter_posicao_propria(self):
        # Posicionar o canvas por coordenadas o deixava para trás quando o mapa descia (a legenda quebrava): os dois dividem uma célula.
        self.assertIn('criar("div", { class: "mapa-pilha" }', script())
        self.assertRegex(CSS, r"\.mapa-pilha \{[^}]*display: grid")
        self.assertRegex(CSS, r"\.mapa-pilha > \* \{ grid-area: 1 / 1; \}")
        self.assertNotRegex(CSS, r"\.mapa-canvas \{[^}]*position: absolute")

    def test_toda_vista_do_palco_existe_na_pagina_no_css_e_no_script(self):
        palco = re.search(r'<div class="coluna centro" id="palco" data-vista="brasil">(.*?)\n    </div>\n\n    <div class="coluna dir"', HTML, re.S).group(1)
        for secao in ("mapa", "mapa-mun", "mundo"):
            self.assertIn(f'id="{secao}"', palco)
        for vista in ("brasil", "uf", "mundo"):
            self.assertIn(f'data-vista="{vista}"', CSS)
            self.assertIn(f'"{vista}"', (WEB / "js" / "palco.js").read_text(encoding="utf-8"))

    def test_as_abas_levam_a_todos_os_cargos(self):
        abas = (WEB / "js" / "abas.js").read_text(encoding="utf-8")
        cargos_das_abas = set(re.findall(r'"((?:presidente|governador|senador|deputado-[a-z]+))"', abas))
        self.assertEqual(cargos_das_abas, set(re.findall(r'^  "?([a-z-]+)"?: "', re.search(r"const CARGOS = \{(.*?)\n\};", script(), re.S).group(1), re.M)))

    def test_modo_incorporado_so_mostra_o_placar(self):
        for escondido in (".abas", ".filtros", ".anuncio", ".coluna.centro", ".coluna.dir"):
            self.assertRegex(CSS, rf"html\.embed :is\([^)]*{re.escape(escondido)}")
        self.assertIn('class="so-incorporado"', HTML)

    def test_scripts_nunca_montam_html_de_texto(self):
        """Texto do anúncio, nomes e endereços entram por textContent e atributos: nada de montar HTML na mão."""
        for nome in ARQUIVOS_JS:
            with self.subTest(script=nome):
                self.assertNotRegex((WEB / "js" / f"{nome}.js").read_text(encoding="utf-8"), r"innerHTML|outerHTML|insertAdjacentHTML|document\.write")

    def test_todo_script_da_pasta_esta_na_pagina(self):
        em_disco = sorted(arquivo.stem for arquivo in (WEB / "js").glob("*.js"))
        self.assertEqual(em_disco, sorted(ARQUIVOS_JS))
        self.assertEqual((ARQUIVOS_JS[0], ARQUIVOS_JS[-1]), ("base", "iniciar"))   # base define o que os outros usam; iniciar roda por último
        self.assertEqual(len(ARQUIVOS_JS), len(set(ARQUIVOS_JS)))

    def test_scripts_carregam_na_ordem_sem_referencia_quebrada(self):
        """Roda os scripts na ordem da página num DOM de mentira: um nome usado no carregamento antes de existir é ReferenceError."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        programa = r"""
const vm = require("vm"), fs = require("fs");
process.on("unhandledRejection", () => {});
const falso = new Proxy(function () {}, {
  get: (_, chave) => (chave === Symbol.toPrimitive ? () => "" : chave === "then" ? undefined : falso),
  apply: () => falso, construct: () => falso, set: () => true,
});
const contexto = vm.createContext({
  document: falso, window: falso, navigator: falso, history: falso, MutationObserver: falso, ResizeObserver: falso, localStorage: falso, sessionStorage: falso, Notification: falso, Option: falso, Image: falso,
  location: { search: "", protocol: "http:", hostname: "localhost", href: "http://localhost/", origin: "http://localhost", pathname: "/" },
  fetch: () => new Promise(() => {}), setInterval: () => 0, setTimeout: () => 0, clearTimeout() {}, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => falso,
  console: { log() {}, error() {}, warn() {} }, URLSearchParams, URL, Blob, TextEncoder,
});
const quebrados = [];
for (const arquivo of process.argv.slice(1)) {
  try { vm.runInContext(fs.readFileSync(arquivo, "utf8"), contexto, { filename: arquivo }); }
  catch (erro) { if (erro && (erro.name === "ReferenceError" || erro.name === "SyntaxError")) quebrados.push(arquivo + ": " + erro.message); }
}
process.stdout.write(JSON.stringify(quebrados));
"""
        arquivos = [str(WEB / "js" / f"{nome}.js") for nome in ARQUIVOS_JS]
        resultado = subprocess.run([node, "-e", programa, *arquivos], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        self.assertEqual(json.loads(resultado.stdout), [])

    def test_ids_usados_pelo_script_existem_na_pagina(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        usados = set(re.findall(r'\$\("([a-z0-9-]+)"\)', script()))
        self.assertEqual(sorted(usados - ids), [])

    def test_csv_para_planilha_brasileira_e_sem_formula(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        fonte = re.search(r"(function celulaCsv.*?\nfunction montarCsv.*?\n\})", script(), re.S).group(1)
        candidatos = [
            {"posicao": 1, "numero": "13", "nome": "ANA LIMA", "partido": "PT", "votos": 1200, "percentual": 37.58, "situacao": ""},
            {"posicao": 2, "numero": "22", "nome": "=CMD|'/c calc'!A1", "partido": "P;L", "votos": 900, "percentual": 31.8, "situacao": 'Eleito "com aspas"'},
        ]
        programa = f"{fonte}\nprocess.stdout.write(JSON.stringify(montarCsv({json.dumps(candidatos)})));"
        saida = subprocess.run([node, "-e", programa], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(saida), (
            "\ufeffposicao;numero;nome;partido;votos;percentual;situacao\r\n"
            "1;13;ANA LIMA;PT;1200;37,58;\r\n"
            "2;22;'=CMD|'/c calc'!A1;\"P;L\";900;31,8;\"Eleito \"\"com aspas\"\"\"\r\n"
        ))

    def test_service_worker_so_responde_pela_pagina_e_pelos_arquivos_dela(self):
        """O service worker de verdade num ambiente de mentira: /api, /geo e outras origens passam direto, sem cache."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        programa = r"""
const vm = require("vm"), fs = require("fs");
const ouvintes = {}, guardados = [];
const contexto = vm.createContext({
  self: { addEventListener: (nome, f) => { ouvintes[nome] = f; }, skipWaiting() {}, clients: { claim() {} } },
  location: { origin: "http://x" }, URL, Response: class {},
  caches: { open: async () => ({ put: (chave) => guardados.push(chave) }), match: async () => undefined, keys: async () => [], delete: async () => true },
  fetch: () => Promise.resolve({ ok: true, clone: () => ({}) }),
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), contexto);
const casos = JSON.parse(process.argv[2]);
(async () => {
  const respondeu = [];
  for (const [metodo, modo, url] of casos) {
    let sim = false;
    ouvintes.fetch({ request: { method: metodo, mode: modo, url }, respondWith: (p) => { sim = true; p.catch(() => {}); } });
    respondeu.push(sim);
  }
  await new Promise((r) => setTimeout(r, 20));
  process.stdout.write(JSON.stringify({ respondeu, guardados }));
})();
"""
        casos = [
            ("GET", "navigate", "http://x/", True), ("GET", "navigate", "http://x/?cargo=presidente&uf=sp", True),
            ("GET", "cors", "http://x/js/base.js", True), ("GET", "no-cors", "http://x/estilo.css", True),
            ("GET", "cors", "http://x/api/placar?cargo=presidente", False), ("GET", "navigate", "http://x/api/mapa-municipal", False),
            ("GET", "cors", "http://x/geo/pe.json", False), ("GET", "navigate", "http://x/og.png", False),
            ("POST", "cors", "http://x/js/base.js", False), ("GET", "cors", "http://outro/js/base.js", False),
            ("GET", "cors", "http://x/js/../app.py", False), ("GET", "cors", "http://x/js/dir/base.js", False),
        ]
        resultado = subprocess.run([node, "-e", programa, str(WEB / "sw.js"), json.dumps([caso[:3] for caso in casos])], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-600:])
        saida = json.loads(resultado.stdout)
        self.assertEqual(saida["respondeu"], [caso[3] for caso in casos])
        self.assertEqual(saida["guardados"], ["/", "/", "/js/base.js", "/estilo.css"])      # só a página e os arquivos dela

    def test_nenhum_nome_global_repetido_entre_scripts(self):
        """Os scripts dividem o escopo global: `const` repetido quebra o carregamento, mas `function` repetida só
        sobrescreve a outra em silêncio. Cada nome de nível de cima tem um dono só."""
        donos = {}
        for nome in ARQUIVOS_JS:
            texto = (WEB / "js" / f"{nome}.js").read_text(encoding="utf-8")
            for achado in re.finditer(r"^(?:async\s+)?function\s+([A-Za-z0-9_$]+)|^(?:const|let|var)\s+([A-Za-z0-9_$]+)", texto, re.M):
                donos.setdefault(achado.group(1) or achado.group(2), []).append(nome)
        repetidos = {identificador: arquivos for identificador, arquivos in donos.items() if len(arquivos) > 1}
        self.assertEqual(repetidos, {})

    def test_replay_do_mapa_conta_os_estados_por_lider(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        fonte = re.search(r"(function contagemDaFoto\(.*?\n\})", script(), re.S).group(1)
        foto = {"t": 1, "ufs": {"sp": ["PT", 5.0, 50.0], "rj": ["PL", 1.0, 50.0], "mg": ["PT", 9.0, 40.0], "ba": ["", 0.0, 0.0], "pr": ["", 0.0, 0.0]}}
        programa = fonte + f"\nprocess.stdout.write(JSON.stringify(contagemDaFoto({json.dumps(foto)})));"
        saida = json.loads(subprocess.run([node, "-e", programa], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(saida, {"contagem": [["PT", 2], ["PL", 1]], "semLider": 2})   # do que mais lidera para o que menos lidera

    def test_mapa_de_sempre_continua_pintando_sem_o_replay(self):
        """O replay só mexe no mapa por ganchos: sem mapa-ao-vivo.js o desenho e a pintura continuam completos."""
        mapa_brasil = (WEB / "js" / "mapa-brasil.js").read_text(encoding="utf-8")
        self.assertIn("if (mapaCongelado) return;", mapa_brasil)
        self.assertIn("avisar(aoPintarUfs, d);", mapa_brasil)
        self.assertEqual(ARQUIVOS_JS.index("mapa-brasil") < ARQUIVOS_JS.index("mapa-ao-vivo"), True)   # usa o que o mapa-brasil declara

    def test_sintaxe_do_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        for arquivo in [*(WEB / "js").glob("*.js"), WEB / "sw.js"]:
            with self.subTest(arquivo=arquivo.name):
                resultado = subprocess.run([node, "--check", str(arquivo)], capture_output=True, text=True)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
