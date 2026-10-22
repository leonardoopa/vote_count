/* Mapa-múndi (só presidente): os países onde há embaixada ou consulado com urna, coloridos pelo líder da votação no exterior.
   Clicar no Brasil leva ao mapa dos estados; clicar noutro país mostra o resultado dele e as cidades. O TSE publica o exterior por
   cidade, então o servidor busca aos poucos (como no mapa por município) e só começa quando a pessoa pede. */
const INTERVALO_MUNDO = 15000;
const ZOOM_MAXIMO_MUNDO = 24;
const PONTO_MINIMO_PX = 9;      // país com votos e menor que isto na tela ganha um ponto clicável
const mundo = { aberto: false, seq: 0, timer: 0, marca: "", geo: null, dados: null, mapa: null, pais: "" };
const temMundo = () => estado.cargo === "presidente";
const marcaMundo = () => [estado.turno, estado.ambiente].join("|");
const nomeDoPais = (iso) => (mundo.geo && mundo.geo.n[iso]) || iso;
const entradaDoPais = (iso) => (mundo.dados ? (iso === "BR" ? mundo.dados.brasil : mundo.dados.paises[iso]) : null) || null;

function resumoDoPais(r) {
  if (r.situacao === "sem_dados") return "Cidades ainda não carregadas";
  if (r.situacao === "zerado") return "Apuração ainda não começou";
  if (r.situacao === "empate") return "Empate no topo";
  const onde = r.locais && r.locais !== r.carregados ? ` · ${inteiro(r.carregados)} de ${inteiro(r.locais)} locais` : "";
  return `${nomeDoCandidato(r.lider)} lidera com ${pct(r.lider.percentual)}, ${pp(r.margem)} à frente (${inteiro(r.margem_votos)} votos) · ${pct(r.apurado)} das seções${onde}`;
}

function dicaDoPais(iso) {
  const r = entradaDoPais(iso), locais = mundo.dados && mundo.dados.locais[iso];
  const texto = r ? resumoDoPais(r)
    : locais ? `${inteiro(locais)} ${locais > 1 ? "locais" : "local"} de votação: ainda não carregado`
      : "Sem urna do Brasil neste país";
  return [criar("strong", {}, nomeDoPais(iso)), criar("span", {}, texto)];
}

function escolherPais(iso) {
  dica.hidden = true;
  if (iso === "BR") {
    mundo.pais = "";
    if (estado.uf !== "br") trocou("uf", "br");
    $("mapa").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  } else if (mundo.dados && mundo.dados.locais[iso]) {
    mundo.pais = iso;
    carregarMundo();     // o detalhe do país vem junto da próxima resposta
  } else {
    return;
  }
  pintarMundo();
  pintarPais();
  pintarTrilha();
}

function construirMundo() {
  const geo = mundo.geo, caixa = $("mundo-svg");
  if (mundo.mapa) mundo.mapa.zoom.destruir();
  const svg = criarSvg("svg", { viewBox: `0 0 ${geo.w} ${geo.h}`, role: "img", tabindex: "0",
    "aria-label": "Mapa-múndi com o líder da votação no exterior de cada país. A lista dos países está logo abaixo. Use + e − para ampliar, as setas para mover e 0 para ver o mundo todo." });
  const grupo = criarSvg("g"), pontos = criarSvg("g"), rotulos = criarSvg("g", { class: "mun-rotulos", "aria-hidden": "true" });
  const caminhos = new Map();
  for (const [iso, forma] of Object.entries(geo.m)) {
    const caminho = criarSvg("path", { d: forma, "data-pais": iso });
    caminhos.set(iso, caminho);
    grupo.append(caminho);
  }
  svg.append(grupo, pontos, rotulos);
  caixa.replaceChildren(svg);
  const caixas = new Map();
  for (const [iso, caminho] of caminhos) caixas.set(iso, caminho.getBBox());
  const zoom = ativarZoom(caixa, svg, geo.w, geo.h, { maximo: ZOOM_MAXIMO_MUNDO, aoParar: aoParouOZoomMundo });
  mundo.mapa = { svg, grupo, pontos, rotulos, caminhos, caixas, zoom, textos: new Map(), circulos: new Map() };

  svg.addEventListener("pointermove", (e) => {
    const alvo = e.buttons ? null : e.target.closest("[data-pais]");   // arrastando o mapa, sem dica
    if (alvo) mostrarDicaEm(dicaDoPais(alvo.dataset.pais), e.clientX, e.clientY);
    else dica.hidden = true;
  });
  svg.addEventListener("pointerleave", () => { dica.hidden = true; });
  svg.addEventListener("click", (e) => {
    const alvo = e.target.closest("[data-pais]");
    if (alvo) escolherPais(alvo.dataset.pais);
  });
}

/* País com votos mas pequeno demais na tela (Singapura, Barein, Barbados…) ganha um ponto, para dar para clicar nele. */
function atualizarPontosMundo() {
  const mapa = mundo.mapa;
  if (!mapa || !mundo.dados) return;
  const porPixel = mapa.zoom.unidadesPorPixel();
  for (const iso of Object.keys(mundo.dados.paises)) {
    const caixa = mapa.caixas.get(iso);
    const pequeno = caixa && caixa.width / porPixel < PONTO_MINIMO_PX && caixa.height / porPixel < PONTO_MINIMO_PX;
    let circulo = mapa.circulos.get(iso);
    if (!pequeno) { if (circulo) { circulo.remove(); mapa.circulos.delete(iso); } continue; }
    if (!circulo) {
      circulo = criarSvg("circle", { class: "ponto", "data-pais": iso, cx: caixa.x + caixa.width / 2, cy: caixa.y + caixa.height / 2 });
      mapa.circulos.set(iso, circulo);
      mapa.pontos.append(circulo);
    }
    circulo.setAttribute("r", 5 * porPixel);
    circulo.setAttribute("style", pintura(mundo.dados.paises[iso].situacao === "lider" ? mundo.dados.paises[iso] : null));
    circulo.classList.toggle("atual", iso === mundo.pais);
  }
}

function aoParouOZoomMundo() {
  atualizarPontosMundo();
  if (mundo.mapa) rotularMapa(mundo.mapa, mundo.geo.n, mundo.geo.w, mundo.geo.h, { kMinimo: 2.5 });
}

function pintarMundo() {
  const d = mundo.dados, mapa = mundo.mapa;
  if (!d || !mapa) return;
  for (const [iso, caminho] of mapa.caminhos) {
    const r = entradaDoPais(iso);
    caminho.setAttribute("style", pintura(r && r.situacao === "lider" ? r : null));
    caminho.classList.toggle("sem-dados", !r);
    caminho.classList.toggle("atual", iso === mundo.pais);
  }
  const contagem = new Map();
  for (const iso of [...Object.keys(d.paises), ...(d.brasil ? ["BR"] : [])]) {
    const r = entradaDoPais(iso);
    if (r && r.situacao === "lider") contagem.set(r.lider.partido, (contagem.get(r.lider.partido) || 0) + 1);
  }
  $("mundo-legenda").replaceChildren(...[...contagem].sort((a, b) => b[1] - a[1]).map(([partido, n]) => criar("li", {},
    criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), `${partido}: ${inteiro(n)} ${n > 1 ? "países" : "país"}`)),
    criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--muted);opacity:0.35" }), "Cinza: sem urna do Brasil ou ainda não carregado"));
  const comUrna = Object.keys(d.locais).length;
  $("mundo-info").textContent = `${inteiro(d.carregadas)} de ${inteiro(d.total)} cidades · ${inteiro(Object.keys(d.paises).length)} de ${inteiro(comUrna)} países`;
  $("mundo-nota").hidden = d.carregadas >= d.total;
  $("mundo-nota").textContent = d.carregadas >= d.total ? "" : "O servidor busca as cidades do exterior no TSE aos poucos; o mapa enche sozinho. Clique num país para ver o resultado dele.";
  pintarTabelaDoMundo(d);
  atualizarPontosMundo();
  rotularMapa(mapa, mundo.geo.n, mundo.geo.w, mundo.geo.h, { kMinimo: 2.5 });
}

function pintarTabelaDoMundo(d) {
  const linhas = [...Object.entries(d.paises), ...(d.brasil ? [["BR", d.brasil]] : [])]
    .sort((a, b) => b[1].votos - a[1].votos)
    .map(([iso, r]) => {
      const lider = r.situacao === "lider" ? `${nomeDoCandidato(r.lider)}` : resumoDoPais(r);
      return criar("tr", {},
        criar("td", {}, criar("button", { class: "botao-link", type: "button", "data-pais": iso, "aria-current": String(iso === mundo.pais) }, nomeDoPais(iso))),
        criar("td", {}, lider),
        criar("td", {}, r.lider ? pct(r.lider.percentual) : "—"),
        criar("td", {}, inteiro(r.votos)),
        criar("td", {}, pct(r.apurado)));
    });
  $("mundo-tabela").replaceChildren(
    criar("thead", {}, criar("tr", {}, ...["País", "Líder", "Percentual", "Votos", "Apurado"].map((t) => criar("th", {}, t)))),
    criar("tbody", {}, ...linhas));
  for (const botao of $("mundo-tabela").querySelectorAll("button")) botao.addEventListener("click", () => escolherPais(botao.dataset.pais));
}

/* Painel do país escolhido: a soma das cidades dele, os candidatos e a lista das embaixadas e consulados. */
function pintarPais() {
  const d = mundo.dados, detalhe = d && d.detalhe && d.detalhe.pais === mundo.pais ? d.detalhe : null;
  $("mundo-pais").hidden = !mundo.pais;
  if (!mundo.pais) return;
  const r = entradaDoPais(mundo.pais);
  $("mundo-pais-nome").textContent = nomeDoPais(mundo.pais);
  $("mundo-pais-resumo").textContent = r ? resumoDoPais(r) : "Carregando as cidades deste país…";
  if (!detalhe) {
    $("mundo-pais-candidatos").replaceChildren();
    $("mundo-pais-cidades").replaceChildren();
    return;
  }
  $("mundo-pais-candidatos").replaceChildren(
    criar("thead", {}, criar("tr", {}, ...["Candidato", "Votos", "Percentual"].map((t) => criar("th", {}, t)))),
    criar("tbody", {}, ...detalhe.candidatos.map((c) => criar("tr", {},
      criar("td", {}, nomeDoCandidato(c)), criar("td", {}, inteiro(c.votos)), criar("td", {}, pct(c.percentual))))));
  $("mundo-pais-cidades").replaceChildren(
    criar("thead", {}, criar("tr", {}, ...["Cidade", "Líder", "Votos", "Apurado"].map((t) => criar("th", {}, t)))),
    criar("tbody", {}, ...detalhe.cidades.map((c) => criar("tr", {},
      criar("td", {}, c.nome),
      criar("td", {}, c.lider ? `${nomeDoCandidato(c.lider)} · ${pct(c.lider.percentual)}` : c.situacao === "sem_dados" ? "ainda não carregada" : c.situacao === "empate" ? "empate" : "apuração não começou"),
      criar("td", {}, c.votos === undefined ? "—" : inteiro(c.votos)),
      criar("td", {}, c.apurado === undefined ? "—" : pct(c.apurado))))));
}

/* Onde a pessoa está: Mundo › Brasil › Estado › Cidade, ou Mundo › País. Cada passo é um botão que leva até lá. */
function pintarTrilha() {
  const nav = $("trilha");
  nav.hidden = !temMundo();
  if (!temMundo()) return;
  const passos = [["Mundo", () => { mundo.pais = ""; pintarMundo(); pintarPais(); pintarTrilha(); $("mundo").scrollIntoView({ behavior: "smooth", block: "start" }); }]];
  if (mundo.pais) {
    passos.push([nomeDoPais(mundo.pais), null]);
  } else {
    passos.push(["Brasil", estado.uf === "br" ? null : () => trocou("uf", "br")]);
    if (estado.uf !== "br") passos.push([UFS[estado.uf] || estado.uf.toUpperCase(), estado.municipio ? () => irParaCidade({ uf: estado.uf, codigo: "" }) : null]);
    if (estado.municipio) {
      const cidadeEscolhida = cidadeAtual();
      passos.push([cidadeEscolhida ? cidadeEscolhida.nome : "Cidade", null]);
    }
  }
  const marca = passos.map(([texto, ao]) => `${texto}${ao ? "*" : ""}`).join("|");
  if (marca === nav.dataset.marca) return;     // nada mudou: não mexe no que está focado
  nav.dataset.marca = marca;
  nav.replaceChildren(criar("ol", {}, ...passos.map(([texto, ao], i) => {
    const item = criar("li", {}, ao ? criar("button", { class: "botao-link", type: "button" }, texto) : criar("span", { "aria-current": i === passos.length - 1 ? "page" : "false" }, texto));
    if (ao) item.firstChild.addEventListener("click", ao);
    return item;
  })));
}

async function carregarMundo() {
  clearTimeout(mundo.timer);
  const minha = ++mundo.seq;
  if (!mundo.aberto || !temMundo()) return;
  $("mundo-tentar").hidden = true;
  try {
    if (!mundo.geo) {
      $("mundo-nota").hidden = false;
      $("mundo-nota").textContent = "Baixando o mapa-múndi…";
      const resposta = await fetch("/geo/mundo.json");
      if (!resposta.ok) throw new Error("desenho");
      mundo.geo = await resposta.json();
    }
  } catch {
    if (minha !== mundo.seq) return;
    $("mundo-nota").hidden = false;
    $("mundo-nota").textContent = "Não foi possível baixar o mapa-múndi. Vou tentar de novo em instantes; se preferir, tente agora.";
    $("mundo-tentar").hidden = false;
    mundo.timer = setTimeout(carregarMundo, 15000);
    return;
  }
  const consulta = new URLSearchParams({ turno: estado.turno, ambiente: estado.ambiente });
  if (mundo.pais) consulta.set("pais", mundo.pais);
  const resposta = await tentar("/api/mundo", consulta);
  if (minha !== mundo.seq) return;
  $("mundo-corpo").hidden = false;
  if (resposta.ok) {
    mundo.dados = resposta.corpo;
    if (!mundo.mapa) construirMundo();     // o corpo precisa estar visível: getBBox mede o desenho na tela
    pintarMundo();
    pintarPais();
    pintarTrilha();
  } else {
    $("mundo-nota").hidden = false;
    $("mundo-nota").textContent = resposta.corpo.erro || "Mapa-múndi indisponível agora.";
  }
  if (!document.hidden) mundo.timer = setTimeout(carregarMundo, resposta.ok && resposta.corpo.carregadas < resposta.corpo.total ? INTERVALO_MUNDO / 3 : INTERVALO_MUNDO);
}

aoMudarSelecao.push(() => {
  $("mundo").hidden = !temMundo();
  pintarTrilha();
  if (!temMundo()) { clearTimeout(mundo.timer); mundo.seq++; mundo.marca = ""; return; }
  if (marcaMundo() === mundo.marca) return;   // só mudou estado ou cidade: o mundo é o mesmo
  mundo.marca = marcaMundo();
  mundo.dados = null;
  mundo.pais = "";
  $("mundo-corpo").hidden = true;
  $("mundo-pais").hidden = true;
  $("mundo-info").textContent = "";
  $("mundo-tentar").hidden = true;
  $("mundo-abrir").hidden = mundo.aberto;
  if (!mundo.aberto) { $("mundo-nota").hidden = false; $("mundo-nota").textContent = "Brasileiros votam no exterior para presidente. O TSE publica o resultado por embaixada e consulado, então o servidor busca as cidades uma a uma e o mapa enche aos poucos. Só começa se você pedir."; }
  carregarMundo();
});
aoRenderizar.push(() => pintarTrilha());   // o nome da cidade só chega depois da lista de cidades
$("mundo-abrir").addEventListener("click", () => { mundo.aberto = true; $("mundo-abrir").hidden = true; carregarMundo(); });
$("mundo-tentar").addEventListener("click", carregarMundo);
$("mundo-pais-fechar").addEventListener("click", () => { mundo.pais = ""; pintarMundo(); pintarPais(); pintarTrilha(); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(mundo.timer);
  else if (mundo.aberto && mundo.marca) carregarMundo();
});
