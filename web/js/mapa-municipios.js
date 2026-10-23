/* Mapa por município. O desenho (geo/<uf>.json, do IBGE) e os dados (uma busca ao TSE por cidade, feita aos poucos
   pelo servidor) só são pedidos quando a pessoa entra no estado (palco.js); depois o mapa enche conforme as cidades chegam.
   O mapa dá zoom (zoom-mapa.js); a área que está na tela é avisada ao servidor, que busca essas cidades primeiro. */
const INTERVALO_MAPA_MUN = 15000;
const ZOOM_MAXIMO_MUN = 40;
const FOCO_MAXIMO_MUN = 60;     // cidades da área visível que o servidor busca primeiro
const ROTULO_MIN_PX = 44;       // a cidade só ganha nome no mapa quando o desenho dela é largo assim na tela
const ROTULOS_MAXIMO_MUN = 150;
const munGeo = {};              // desenhos já baixados, por UF: {w, h, m: {ibge: caminho}, n: {ibge: nome}}
const mun = { aberto: false, seq: 0, timer: 0, marca: "", dados: null, mapa: null, foco: "" };
const temMapaMun = () => (estado.cargo === "presidente" || estado.cargo === "governador") && estado.uf !== "br";
const marcaMun = () => [estado.cargo, estado.uf, estado.turno, estado.ambiente].join("|");

function resumoDaCidade(r) {
  if (r.situacao === "zerado") return "Apuração ainda não começou";
  if (r.situacao === "empate") return `Empate no topo: ${r.empatados.map(nomeDoCandidato).join(" e ")}`;
  return `${nomeDoCandidato(r.lider)} lidera com ${pct(r.lider.percentual)}${r.lider.eleito ? " · eleito" : ""}, ${pp(r.margem)} à frente (${inteiro(r.margem_votos)} votos) · ${pct(r.apurado)} das seções`;
}

/* O nome vem do desenho (todas as cidades, desde o primeiro instante); o placar vem do servidor (só as já buscadas). */
function dicaDaCidade(ibge) {
  const r = mun.dados && mun.dados.cidades[ibge];
  const nome = (munGeo[estado.uf].n || {})[ibge] || (r && r.nome) || "Município";
  return [criar("strong", {}, nome), criar("span", {}, r ? resumoDaCidade(r) : "Placar ainda não carregado: o servidor busca as cidades aos poucos.")];
}

/* Estado com uma ilha distante (Fernando de Noronha em PE, Trindade no ES) deixaria o desenho inteiro pequeno na tela.
   O enquadramento inicial ignora o 1% de cidades mais afastadas, se isso tirar bastante área em branco; "Ver tudo" mostra tudo. */
function enquadrarSemIlhas(caixas, largura, altura) {
  const centros = [...caixas.values()].map((c) => [c.x + c.width / 2, c.y + c.height / 2]);
  if (centros.length < 20) return null;
  const corte = (valores) => {
    const ordem = [...valores].sort((a, b) => a - b);
    return [ordem[Math.floor(ordem.length * 0.01)], ordem[Math.ceil(ordem.length * 0.99) - 1]];
  };
  const [x0, x1] = corte(centros.map((c) => c[0])), [y0, y1] = corte(centros.map((c) => c[1]));
  if ((x1 - x0) * (y1 - y0) > 0.6 * largura * altura) return null;   // sem ilha: o desenho inteiro já enquadra bem
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

function construirMapaMun() {
  const uf = estado.uf, geo = munGeo[uf], caixa = $("mapa-mun-svg");
  if (mun.mapa) mun.mapa.zoom.destruir();
  const svg = criarSvg("svg", { viewBox: `0 0 ${geo.w} ${geo.h}`, role: "img", tabindex: "0",
    "aria-label": `Mapa dos municípios de ${UFS[uf]} com o líder de cada cidade já carregada. Use + e − para ampliar, as setas para mover e 0 para ver o estado todo.` });
  const grupo = criarSvg("g"), rotulos = criarSvg("g", { class: "mun-rotulos", "aria-hidden": "true" });
  const caminhos = new Map();
  for (const [ibge, forma] of Object.entries(geo.m)) {
    const caminho = criarSvg("path", { d: forma, "data-ibge": ibge });
    caminhos.set(ibge, caminho);
    grupo.append(caminho);
  }
  svg.append(grupo, rotulos);
  caixa.replaceChildren(svg);
  const caixas = new Map();               // retângulo de cada cidade no desenho, para saber o que está na tela
  for (const [ibge, caminho] of caminhos) caixas.set(ibge, caminho.getBBox());
  const zoom = ativarZoom(caixa, svg, geo.w, geo.h, { maximo: ZOOM_MAXIMO_MUN, aoParar: aoParouOZoomMun });
  mun.mapa = { uf, svg, grupo, rotulos, caminhos, caixas, zoom, textos: new Map() };
  mun.foco = "";
  const quadro = enquadrarSemIlhas(caixas, geo.w, geo.h);
  if (quadro) zoom.irPara(quadro, { margem: 1.2, duracao: 0 });

  svg.addEventListener("pointermove", (e) => {
    const alvo = e.buttons ? null : e.target.closest("path[data-ibge]");   // arrastando o mapa, sem dica
    if (alvo) mostrarDicaEm(dicaDaCidade(alvo.dataset.ibge), e.clientX, e.clientY);
    else dica.hidden = true;
  });
  svg.addEventListener("pointerleave", () => { dica.hidden = true; });
  svg.addEventListener("click", (e) => {
    const alvo = e.target.closest("path[data-ibge]");
    const r = alvo && mun.dados && mun.dados.cidades[alvo.dataset.ibge];
    if (!r) return;
    dica.hidden = true;
    // O zoom até a cidade vem primeiro; o placar dela só troca quando o mapa chega lá.
    mun.mapa.zoom.irPara(mun.mapa.caixas.get(alvo.dataset.ibge), { margem: 2.4, aoTerminar: () => irParaCidade({ uf: estado.uf, codigo: r.codigo }) });
  });
}

function marcarCidadeAtual() {
  if (!mun.mapa || !mun.dados) return;
  for (const [ibge, caminho] of mun.mapa.caminhos) {
    const r = mun.dados.cidades[ibge];
    const atual = Boolean(r) && estado.municipio !== "" && r.codigo === estado.municipio;
    if (atual && !caminho.classList.contains("atual")) mun.mapa.grupo.append(caminho);   // por último: o contorno não fica sob os vizinhos
    caminho.classList.toggle("atual", atual);
  }
}

function pintarMapaMun() {
  const d = mun.dados, porCodigo = d.cidades;
  for (const [ibge, caminho] of mun.mapa.caminhos) {
    const r = porCodigo[ibge];
    caminho.setAttribute("style", pintura(r && r.situacao === "lider" ? r : null));
    caminho.classList.toggle("sem-dados", !r);
  }
  marcarCidadeAtual();
  const contagem = new Map();
  for (const r of Object.values(porCodigo)) if (r.situacao === "lider") contagem.set(r.lider.partido, (contagem.get(r.lider.partido) || 0) + 1);
  $("mapa-mun-legenda").replaceChildren(...[...contagem].sort((a, b) => b[1] - a[1]).map(([partido, n]) => criar("li", {},
    criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), `${partido}: ${inteiro(n)} ${n > 1 ? "cidades" : "cidade"}`)),
    criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--muted);opacity:0.35" }), "Cinza: ainda não carregada ou sem líder"));
  $("mapa-mun-info").textContent = `${inteiro(d.carregadas)} de ${inteiro(d.total)} cidades`;
  $("mapa-mun-nota").hidden = d.carregadas >= d.total;
  $("mapa-mun-nota").textContent = d.carregadas >= d.total ? "" : "O servidor busca as cidades no TSE aos poucos; o mapa enche sozinho. Clique numa cidade para ver o placar dela.";
  atualizarRotulosMun();
}

function atualizarRotulosMun() {
  const mapa = mun.mapa;
  if (mapa) rotularMapa(mapa, munGeo[mapa.uf].n || {}, munGeo[mapa.uf].w, munGeo[mapa.uf].h, { maximo: ROTULOS_MAXIMO_MUN, minimoPx: ROTULO_MIN_PX });
}

/* As cidades da área visível, as mais perto do centro primeiro: o servidor busca essas antes das outras. */
function focoDoMapaMun() {
  const mapa = mun.mapa, { x, y, k } = mapa.zoom.vista, geo = munGeo[mapa.uf];
  if (k < 2) return "";
  const largura = geo.w / k, altura = geo.h / k, cx = x + largura / 2, cy = y + altura / 2, vistas = [];
  for (const [ibge, c] of mapa.caixas) {
    if (c.x > x + largura || c.x + c.width < x || c.y > y + altura || c.y + c.height < y) continue;
    vistas.push([Math.hypot(c.x + c.width / 2 - cx, c.y + c.height / 2 - cy), ibge]);
  }
  return vistas.sort((a, b) => a[0] - b[0]).slice(0, FOCO_MAXIMO_MUN).map(([, ibge]) => ibge).join(",");
}

function aoParouOZoomMun() {
  atualizarRotulosMun();
  const foco = focoDoMapaMun();
  if (foco === mun.foco) return;
  mun.foco = foco;
  if (mun.dados && mun.dados.carregadas < mun.dados.total) carregarMapaMun();   // não espera o próximo ciclo
}

async function carregarMapaMun() {
  clearTimeout(mun.timer);
  const minha = ++mun.seq, uf = estado.uf;
  if (!mun.aberto || !temMapaMun() || palco.vista !== "uf") return;   // só busca enquanto o mapa dos municípios está na tela
  $("mapa-mun-tentar").hidden = true;
  try {
    if (!munGeo[uf]) {
      $("mapa-mun-nota").hidden = false;
      $("mapa-mun-nota").textContent = "Baixando o desenho dos municípios…";
      const resposta = await fetch(`/geo/${uf}.json`);
      if (!resposta.ok) throw new Error("desenho");
      munGeo[uf] = await resposta.json();
    }
  } catch {
    if (minha !== mun.seq) return;
    $("mapa-mun-nota").hidden = false;
    $("mapa-mun-nota").textContent = "Não foi possível baixar o desenho dos municípios. Vou tentar de novo em instantes; se preferir, tente agora.";
    $("mapa-mun-tentar").hidden = false;
    mun.timer = setTimeout(carregarMapaMun, 15000);
    return;
  }
  const consulta = new URLSearchParams({ cargo: estado.cargo, uf, turno: estado.turno, ambiente: estado.ambiente });
  if (mun.foco && mun.mapa && mun.mapa.uf === uf) consulta.set("foco", mun.foco);
  const resposta = await tentar("/api/mapa-municipal", consulta);
  if (minha !== mun.seq) return;
  $("mapa-mun-corpo").hidden = false;
  if (resposta.ok) {
    mun.dados = resposta.corpo;
    if (!mun.mapa || mun.mapa.uf !== uf) construirMapaMun();   // o corpo precisa estar visível: getBBox mede o desenho na tela
    pintarMapaMun();
  } else {
    $("mapa-mun-nota").hidden = false;
    $("mapa-mun-nota").textContent = resposta.corpo.erro || "Mapa por município indisponível agora.";
  }
  if (!document.hidden) mun.timer = setTimeout(carregarMapaMun, resposta.ok && resposta.corpo.carregadas < resposta.corpo.total ? INTERVALO_MAPA_MUN / 3 : INTERVALO_MAPA_MUN);
}

aoMudarSelecao.push(() => {
  $("mapa-mun").hidden = !temMapaMun();
  if (!temMapaMun()) { clearTimeout(mun.timer); mun.seq++; mun.marca = ""; return; }
  if (marcaMun() === mun.marca) { marcarCidadeAtual(); return; }   // só mudou a cidade: o mapa é o mesmo, muda o contorno marcado
  mun.marca = marcaMun();
  mun.dados = null;
  $("mapa-mun-corpo").hidden = true;
  $("mapa-mun-info").textContent = "";
  $("mapa-mun-tentar").hidden = true;
  $("mapa-mun-abrir").hidden = mun.aberto;
  if (!mun.aberto) { $("mapa-mun-nota").hidden = false; $("mapa-mun-nota").textContent = "O TSE publica um arquivo por cidade, então o servidor busca as cidades uma a uma e o mapa enche aos poucos. Só começa se você pedir."; }
  carregarMapaMun();
});
$("mapa-mun-abrir").addEventListener("click", () => { mun.aberto = true; $("mapa-mun-abrir").hidden = true; carregarMapaMun(); });
$("mapa-mun-tentar").addEventListener("click", carregarMapaMun);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(mun.timer);
  else if (mun.aberto && mun.marca) carregarMapaMun();
});
