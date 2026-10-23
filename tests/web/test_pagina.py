"""Testes de `web/ (index.html, estilo.css, scripts e service worker)`."""
import json
import re
import shutil
import subprocess
import unittest

from contador.caminhos import WEB
from contador.tse import catalogo


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
  document: falso, window: falso, navigator: falso, history: falso, localStorage: falso, sessionStorage: falso, Notification: falso, Option: falso, Image: falso,
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

    def test_sintaxe_do_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node não está instalado")
        for arquivo in [*(WEB / "js").glob("*.js"), WEB / "sw.js"]:
            with self.subTest(arquivo=arquivo.name):
                resultado = subprocess.run([node, "--check", str(arquivo)], capture_output=True, text=True)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
