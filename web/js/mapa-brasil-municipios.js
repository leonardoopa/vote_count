/* Mapa do Brasil por município, em quatro modos:
   Municípios: cada um pintado de azul ou vermelho (o partido de quem lidera, mais forte quanto maior a vantagem);
   Apurado: o quanto das seções de cada município já foi apurado; Vantagem: um pico por município, da altura da vantagem
   em votos de quem lidera; Estados: a pintura por estado de sempre.
   O desenho (geo/brasil.json: os ~5,6 mil municípios nas mesmas coordenadas dos estados) vai num <canvas> por baixo do SVG dos
   estados: 5,6 mil elementos SVG travavam a página (montar, pintar e dar zoom), e no canvas redesenhar tudo custa poucos
   milissegundos. Cada município nasce cinza e ganha a própria cor conforme o servidor busca as cidades no TSE: só município
   pinta o mapa, nunca o estado inteiro. */
const CAMINHOS_POR_QUADRO = 1400;   // Path2D por quadro ao montar a camada
const INTERVALO_BRASIL_MUN = 20000;
const INTERVALO_BRASIL_MUN_PRONTO = 120000;
const UF_DO_CODIGO_IBGE = {
  11: "ro", 12: "ac", 13: "am", 14: "rr", 15: "pa", 16: "ap", 17: "to", 21: "ma", 22: "pi", 23: "ce", 24: "rn", 25: "pb", 26: "pe",
  27: "al", 28: "se", 29: "ba", 31: "mg", 32: "es", 33: "rj", 35: "sp", 41: "pr", 42: "sc", 43: "rs", 50: "ms", 51: "mt", 52: "go", 53: "df",
};
const MODOS_DO_MAPA = {
  municipios: { rotulo: "Municípios" },
  apurado: { rotulo: "Apurado" },
  vantagem: { rotulo: "Vantagem", detalhe: "O tamanho da vantagem, em picos" },
  estados: { rotulo: "Estados", detalhe: "Quem lidera em cada estado" },
  candidato: { rotulo: "Candidato" },
};
const MODOS_NO_MENU = ["vantagem", "estados"];
const ufDoIbge = (ibge) => UF_DO_CODIGO_IBGE[ibge.slice(0, 2)];
const bm = { candidato: null, candidatosDoDuelo: [], indice: null, faixa: [20, 70], modo: "municipios", geo: null, baixando: false, pronto: false, svg: null, canvas: null, paths: new Map(), caixas: new Map(), ordem: [], cores: new Map(), picos: new Map(), focoUf: null, animaAte: 0, agendado: false, dados: null, marca: "", seq: 0, timer: 0 };
const contextoDeTeste = document.createElement("canvas").getContext("2d");   // para saber que município está sob o ponteiro

const modoDoMapa = () => (temMapa() ? bm.modo : "estados");
const usaMunicipios = () => modoDoMapa() !== "estados";

/* Altura do pico, em unidades do desenho dos estados: cresce com a raiz da vantagem, então 10 mil votos ainda aparecem e
   2 milhões não saem do mapa. */
const alturaDoPico = (votos) => Math.min(230, 5.2 * Math.sqrt(Math.max(votos, 0) / 1000));

/* Os picos sobem em vez de aparecer: ao entrar no modo, uma onda varre o mapa do norte ao sul e cada pico cresce de zero até a
   altura dele, passando um pouco do ponto antes de assentar; quando chega voto novo, o pico vai da altura de antes à de agora. */
const ANIMACAO_PICO_MS = 700, ANIMACAO_ONDA_MS = 900;
const suavizar = (t) => 1 + 1.6 * Math.pow(t - 1, 3) + 0.6 * Math.pow(t - 1, 2);
function alturaAnimada(de, alvo, atraso, decorrido) {
  const t = (decorrido - atraso) / ANIMACAO_PICO_MS;
  return t <= 0 ? de : t >= 1 ? alvo : de + (alvo - de) * suavizar(t);
}
const abreviarVotos = (n) => (n >= 1e6 ? `${(n / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi` : n >= 1e3 ? `${Math.round(n / 1e3).toLocaleString("pt-BR")} mil` : String(n));

/* Retângulo [x0, y0, x1, y1] de um caminho no formato que tools/gerar_mapa.py escreve ("M x yl dx dy dx dy…z", um ou mais anéis). */
function caixaDoCaminho(d) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [, mx, my, passos] of d.matchAll(/M(-?\d+) (-?\d+)l([^z]*)z/g)) {
    let x = Number(mx), y = Number(my);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    const numeros = passos.match(/-?\d+/g) || [];
    for (let i = 0; i + 1 < numeros.length; i += 2) {
      x += Number(numeros[i]); y += Number(numeros[i + 1]);
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
  }
  return [x0, y0, x1, y1];
}

async function baixarDesenhoDoBrasil() {
  if (bm.geo || bm.baixando) return;
  bm.baixando = true;
  try {
    const resposta = await fetch("/geo/brasil.json");
    if (!resposta.ok) throw new Error("desenho");
    bm.geo = await resposta.json();
  } catch {
    bm.modo = "estados";   // sem o desenho dos municípios, fica o mapa por estado
    aplicarModoDoMapa();
  }
  bm.baixando = false;
  garantirCamadaDosMunicipios();
}

/* Monta a camada uma vez por desenho do Brasil: o canvas por baixo do SVG e um Path2D por município, alguns por quadro. */
function garantirCamadaDosMunicipios() {
  if (!mapaSvg || !temMapa() || palco.vista !== "brasil") return;
  if (!bm.geo) { baixarDesenhoDoBrasil(); return; }
  if (bm.svg !== mapaSvg.svg) { montarCamada(); return; }
  if (!bm.pronto) return;
  aplicarModoDoMapa();
  pintarMunicipios();
  carregarMunicipiosDoBrasil();
}

function montarCamada() {
  const svg = mapaSvg.svg, caixa = svg.parentNode;
  Object.assign(bm, { svg, pronto: false, paths: new Map(), caixas: new Map(), ordem: [], cores: new Map(), picos: new Map(), focoUf: null });
  bm.canvas = criar("canvas", { class: "mapa-canvas", "aria-hidden": "true" });
  bm.ctx = bm.canvas.getContext("2d");
  // Canvas e SVG dividem a mesma célula de uma grade: se o mapa descer ou crescer (a legenda quebrou, a janela mudou), os dois vão juntos.
  const pilha = criar("div", { class: "mapa-pilha" }, bm.canvas);
  caixa.insertBefore(pilha, svg);
  pilha.append(svg);
  svg.dataset.modo = modoDoMapa();   // enquanto a camada monta, os estados ficam sem cor: só município pinta o mapa
  new ResizeObserver(ajustarCanvas).observe(svg);
  new MutationObserver(agendarDesenho).observe(svg, { attributes: true, attributeFilter: ["viewBox"] });   // o zoom anima o viewBox
  const entradas = Object.entries(bm.geo.m);
  let posicao = 0;
  const lote = () => {
    if (bm.svg !== svg) return;   // o desenho dos estados foi refeito: esta camada ficou para trás
    for (const fim = Math.min(posicao + CAMINHOS_POR_QUADRO, entradas.length); posicao < fim; posicao++) {
      const [ibge, forma] = entradas[posicao];
      bm.paths.set(ibge, new Path2D(forma));
      bm.caixas.set(ibge, caixaDoCaminho(forma));
      bm.ordem.push(ibge);
    }
    if (posicao < entradas.length) { requestAnimationFrame(lote); return; }
    bm.pronto = true;
    ligarEventosDosMunicipios(svg);
    ajustarCanvas();
    garantirCamadaDosMunicipios();
  };
  requestAnimationFrame(lote);
}

/* O CSS põe o canvas em cima do SVG, do mesmo tamanho; aqui só se dá a ele a resolução da tela. */
function ajustarCanvas() {
  if (!bm.canvas || !bm.svg) return;
  const r = bm.svg.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  bm.canvas.width = Math.max(1, Math.round(r.width * dpr));
  bm.canvas.height = Math.max(1, Math.round(r.height * dpr));
  agendarDesenho();
}

function agendarDesenho() {
  if (bm.agendado) return;
  bm.agendado = true;
  requestAnimationFrame(() => { bm.agendado = false; desenharMunicipios(); });
}

/* As cores vêm das variáveis do tema (o canvas não lê CSS): resolve uma vez por partido e guarda. */
const cacheDeCores = new Map();
function rgbDaVariavel(nome) {
  const chave = nome;
  if (!cacheDeCores.has(chave)) {
    const hex = getComputedStyle($("mapa-svg")).getPropertyValue(nome).trim().replace("#", "");
    cacheDeCores.set(chave, hex.length === 6 ? [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) : [137, 135, 129]);
  }
  return cacheDeCores.get(chave);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { cacheDeCores.clear(); bm.cores.clear(); pintarMunicipios(); });
const rgbDoPartido = (partido) => rgbDaVariavel(corDoPartido(partido).slice(4, -1));
const rgba = ([r, g, b], alfa) => `rgba(${r},${g},${b},${alfa.toFixed(2)})`;
const forcaDaVantagem = (margem) => 0.35 + 0.65 * Math.min(Math.max(margem, 0), 20) / 20;   // a mesma de `pinturaDe`

/* Desenha tudo: cada município na cor dele; no modo Vantagem, os municípios apagados e os picos por cima. */
function desenharMunicipios() {
  const { canvas, ctx, svg } = bm;
  if (!canvas || !bm.pronto) return;
  const r = svg.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  const largura = Math.round(r.width * dpr), altura = Math.round(r.height * dpr);
  if (canvas.width !== largura || canvas.height !== altura) { canvas.width = Math.max(1, largura); canvas.height = Math.max(1, altura); }   // sempre na resolução do que se vê
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!usaMunicipios() || !largura || !svg.parentNode) return;
  const [vx, vy, vw] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
  const escala = canvas.width / vw, f = MAPA_TAMANHO[0] / bm.geo.w;   // do desenho dos municípios para o dos estados, e deste para a tela
  const modo = modoDoMapa();
  ctx.setTransform(escala * f, 0, 0, escala * f, -vx * escala, -vy * escala);
  for (const ibge of bm.ordem) {
    const cor = modo === "vantagem" ? "rgba(255,255,255,0.05)" : bm.cores.get(ibge);
    if (!cor) continue;
    const fora = bm.focoUf && ufDoIbge(ibge) !== bm.focoUf;   // durante o zoom até um estado, os outros apagam
    ctx.globalAlpha = fora ? 0.08 : 1;
    ctx.fillStyle = cor;
    ctx.fill(bm.paths.get(ibge));
  }
  ctx.globalAlpha = 1;
  if (modo !== "vantagem") return;
  ctx.setTransform(escala, 0, 0, escala, -vx * escala, -vy * escala);   // os picos já estão nas coordenadas dos estados
  const agora = performance.now();
  for (const { x, y, de, altura, atraso, inicio, cor, ibge } of bm.picos.values()) {   // do norte para o sul: o de baixo cobre o de cima
    const h = alturaAnimada(de, altura, atraso, agora - inicio);
    if (h < 0.2) continue;
    const meia = 1.6 + h * 0.02;
    ctx.globalAlpha = bm.focoUf && ufDoIbge(ibge) !== bm.focoUf ? 0.08 : 0.85;
    ctx.fillStyle = cor;
    ctx.beginPath();
    ctx.moveTo(x - meia, y);
    ctx.lineTo(x, y - h);
    ctx.lineTo(x + meia, y);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  if (agora < bm.animaAte) agendarDesenho();   // ainda subindo: o próximo quadro
}

function aplicarModoDoMapa() {
  if (bm.svg && bm.pronto) bm.svg.dataset.modo = modoDoMapa();
  pintarModosDoMapa();
  agendarDesenho();
}

/* "Municípios" e "Apurado" são botões; "Vantagem" e "Estados" ficam no menu "Mais mapas", como no painel do TSE. */
function pintarModosDoMapa() {
  const nav = $("mapa-modo");
  nav.hidden = !temMapa();
  if (!temMapa()) return;
  const botao = (modo) => {
    const b = criar("button", { type: "button", "aria-pressed": String(modo === bm.modo) }, MODOS_DO_MAPA[modo].rotulo);
    b.addEventListener("click", () => trocarModoDoMapa(modo));
    return b;
  };
  const noMenu = MODOS_NO_MENU.includes(bm.modo) || bm.modo === "candidato";
  const rotuloAberto = bm.modo === "candidato" && bm.candidato ? bm.candidato.nome : MODOS_NO_MENU.includes(bm.modo) ? MODOS_DO_MAPA[bm.modo].rotulo : "Mais mapas";
  const abrir = criar("button", { type: "button", class: "mais-mapas-abrir", "aria-pressed": String(noMenu), "aria-haspopup": "menu", "aria-expanded": "false" }, `${rotuloAberto} ▾`);
  const menu = criar("div", { class: "mais-mapas-menu", role: "menu", hidden: "" }, ...MODOS_NO_MENU.map((modo) => {
    const item = criar("button", { type: "button", role: "menuitem", "aria-current": String(modo === bm.modo) }, criar("strong", {}, MODOS_DO_MAPA[modo].rotulo), criar("span", {}, MODOS_DO_MAPA[modo].detalhe));
    item.addEventListener("click", () => trocarModoDoMapa(modo));
    return item;
  }), ...(estado.cargo === "presidente" ? bm.candidatosDoDuelo.map((c) => {
    const item = criar("button", { type: "button", role: "menuitem", class: "com-foto", style: `--cor:${corDoPartido(c.partido)}`, "aria-current": String(bm.candidato && bm.candidato.numero === c.numero) },
      fotoDoCandidato(c), criar("div", {}, criar("strong", {}, c.nome), criar("span", {}, `${c.partido} · onde vai melhor`)));
    item.addEventListener("click", () => escolherCandidatoNoMapa(bm.candidato && bm.candidato.numero === c.numero ? null : c));
    return item;
  }) : []));
  abrir.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; abrir.setAttribute("aria-expanded", String(!menu.hidden)); });
  nav.replaceChildren(botao("municipios"), botao("apurado"), criar("div", { class: "mais-mapas" }, abrir, menu));
}
document.addEventListener("click", () => { const menu = document.querySelector(".mais-mapas-menu"); if (menu) menu.hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { const menu = document.querySelector(".mais-mapas-menu"); if (menu) menu.hidden = true; } });

function trocarModoDoMapa(modo) {
  if (modo === bm.modo) return;
  bm.modo = modo;
  bm.candidato = null;
  bm.cores.clear();
  if (modo === "vantagem") bm.picos = new Map();   // os picos nascem do zero a cada entrada no modo
  pintarPainelDoCandidato();
  if (ultimo) pintarDuelo(ultimo);
  aplicarModoDoMapa();
  if (usaMunicipios()) { pintarMunicipios(); carregarMunicipiosDoBrasil(); return; }
  clearTimeout(bm.timer);
  bm.seq++;
  if (mapaDados) {
    $("mapa-info").textContent = `${Object.values(mapaDados.ufs).filter((r) => r.situacao === "lider").length} de 27 com líder`;
    $("mapa-legenda").replaceChildren(...legendaDoMapa(mapaDados));
  }
}

const entre0e1 = (n) => Math.min(Math.max(n, 0), 1);
/* A votação do candidato escolhido numa cidade (null onde ele não ficou entre os dois primeiros, que são os que o servidor manda). */
function percentualDoCandidatoNaCidade(linha) {
  if (!linha || !bm.candidato) return null;
  if (bm.indice === null) bm.indice = bm.dados.candidatos.findIndex((c) => c.numero === bm.candidato.numero);
  return linha[0] === bm.indice ? linha[1] : linha[2] === bm.indice ? linha[3] : null;
}
const forcaDoCandidato = (p) => 0.12 + 0.88 * entre0e1((p - bm.faixa[0]) / (bm.faixa[1] - bm.faixa[0]));

/* A cor de cada município, em rgba: a dele, se já chegou; senão cinza (o estado nunca empresta a cor dele). */
function corDoMunicipio(ibge, linha, modo) {
  if (modo === "candidato") {
    const cor = rgbDoPartido(bm.candidato.partido);
    const p = linha ? percentualDoCandidatoNaCidade(linha) : null;
    return p === null ? "rgba(137,135,129,0.08)" : rgba(cor, forcaDoCandidato(p));
  }
  if (modo === "apurado") return linha ? rgba(rgbDaVariavel("--series"), 0.18 + 0.82 * Math.min(linha[4], 100) / 100) : "rgba(137,135,129,0.2)";
  if (linha) return rgba(rgbDoPartido(bm.dados.candidatos[linha[0]].partido), forcaDaVantagem(linha[2] >= 0 ? linha[1] - linha[3] : linha[1]));
  return "rgba(137,135,129,0.15)";
}

/* A escala do mapa do candidato vai do 5º ao 95º percentil da votação dele, para um município fora da curva não apagar o resto. */
function calcularFaixaDoCandidato(cidades) {
  bm.indice = null;
  const valores = Object.values(cidades).map(percentualDoCandidatoNaCidade).filter((p) => p !== null).sort((a, b) => a - b);
  if (valores.length < 20) return;
  bm.faixa = [Math.floor(valores[Math.floor(valores.length * 0.05)]), Math.ceil(valores[Math.ceil(valores.length * 0.95) - 1])];
  if (bm.faixa[1] - bm.faixa[0] < 5) bm.faixa[1] = bm.faixa[0] + 5;
}

function pintarMunicipios() {
  if (!bm.pronto || !mapaDados || !usaMunicipios()) return;
  const cidades = bm.dados ? bm.dados.cidades : {}, modo = modoDoMapa();
  if (modo === "candidato" && bm.dados) calcularFaixaDoCandidato(cidades);
  for (const ibge of bm.ordem) bm.cores.set(ibge, corDoMunicipio(ibge, cidades[ibge], modo));
  if (modo === "vantagem") calcularPicos(cidades);
  pintarLegendaDosMunicipios();
  agendarDesenho();
}

/* Um pico (triângulo) por município com vantagem, no centro dele. Do norte para o sul: o de baixo cobre o de cima. */
function calcularPicos(cidades) {
  const f = bm.geo.w / MAPA_TAMANHO[0], picos = new Map();
  if (!bm.geo.c) return;
  const antes = bm.picos, agora = performance.now();
  const entrada = antes.size === 0, quieto = semMovimento();   // com o mapa vazio, a onda de entrada; sem movimento, o pico já nasce pronto
  const ibges = Object.keys(cidades).filter((ibge) => bm.geo.c[ibge] && cidades[ibge][5] > 0).sort((a, b) => bm.geo.c[a][1] - bm.geo.c[b][1]);
  let fim = 0;
  for (const ibge of ibges) {
    const linha = cidades[ibge], [cx, cy] = bm.geo.c[ibge], altura = alturaDoPico(linha[5]), velho = antes.get(ibge);
    const cor = rgba(rgbDoPartido(bm.dados.candidatos[linha[0]].partido), 1);
    if (velho && velho.altura === altura && velho.cor === cor) { picos.set(ibge, velho); continue; }   // não mudou: segue o ritmo que já tinha
    const y = cy / f, de = quieto ? altura : velho ? alturaAnimada(velho.de, velho.altura, velho.atraso, agora - velho.inicio) : 0;
    const atraso = entrada && !quieto ? (y / MAPA_TAMANHO[1]) * ANIMACAO_ONDA_MS : 0;
    if (de !== altura) fim = Math.max(fim, agora + atraso + ANIMACAO_PICO_MS);
    picos.set(ibge, { ibge, x: cx / f, y, de, altura, atraso, inicio: agora, cor });
  }
  bm.picos = picos;
  bm.animaAte = Math.max(bm.animaAte, fim);
}

function legendaDeIntensidade(rotulo) {
  return criar("li", { class: "escala-cor" }, ...[0.35, 0.55, 0.8, 1].map((forca) => criar("i", { class: "amostra-cor", style: `background:var(--ink-2);opacity:${forca}` })), rotulo);
}

function legendaDosPicos() {
  const picos = [10000, 100000, 500000].map((votos) => {
    const altura = alturaDoPico(votos) / 4;
    return criar("span", { class: "escala-pico" }, criarSvg("svg", { viewBox: "0 0 12 30", width: "12", height: "30", "aria-hidden": "true" }, criarSvg("path", { d: `M0 30L6 ${30 - altura * 3}L12 30z` })), abreviarVotos(votos));
  });
  return criar("li", { class: "escala-picos" }, ...picos, "votos de vantagem");
}

function pintarLegendaDosMunicipios() {
  if (!usaMunicipios() || !bm.dados) return;
  const modo = modoDoMapa(), contagem = new Map(), vantagem = new Map();
  for (const linha of Object.values(bm.dados.cidades)) {
    const partido = bm.dados.candidatos[linha[0]].partido;
    contagem.set(partido, (contagem.get(partido) || 0) + 1);
    vantagem.set(partido, (vantagem.get(partido) || 0) + Math.max(linha[5], 0));
  }
  const por = (mapa) => [...mapa].sort((a, b) => b[1] - a[1]).slice(0, 4);
  const amostra = (partido) => criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` });
  let itens;
  if (modo === "candidato") {
    const aFrente = Object.values(bm.dados.cidades).filter((linha) => linha[0] === bm.indice).length;
    const cor = rgbDoPartido(bm.candidato.partido), swatches = [0.25, 0.5, 0.75, 1].map((forca) => criar("i", { class: "amostra-cor", style: `background:${rgba(cor, forca)}` }));
    itens = [criar("li", {}, "À frente em ", criar("b", {}, inteiro(aFrente)), ` ${aFrente === 1 ? "município" : "municípios"}`), criar("li", { class: "escala-cor" }, `menos de ${bm.faixa[0]}%`, ...swatches, `${bm.faixa[1]}% ou mais`)];
  } else if (modo === "vantagem") {
    itens = [...por(vantagem).map(([partido, votos]) => criar("li", {}, amostra(partido), partido, " ", criar("b", {}, `+${abreviarVotos(votos)}`))), legendaDosPicos()];
  } else if (modo === "apurado") {
    itens = [criar("li", { class: "escala-cor" }, ...[0.3, 0.55, 0.8, 1].map((forca) => criar("i", { class: "amostra-cor", style: `background:var(--series);opacity:${forca}` })), "seções apuradas: pouco → tudo")];
  } else {
    itens = [...por(contagem).map(([partido, n]) => criar("li", {}, amostra(partido), `${partido}: `, criar("b", {}, inteiro(n)), ` ${n > 1 ? "municípios" : "município"}`)), legendaDeIntensidade("vantagem: pouca → 20 pontos ou mais")];
  }
  $("mapa-legenda").replaceChildren(...itens);
  $("mapa-info").textContent = `${inteiro(bm.dados.carregadas)} de ${inteiro(bm.dados.total)} municípios`;
  $("mapa-explica").textContent = {
    municipios: "A cor é a do partido de quem lidera cada município; quanto mais forte, maior a vantagem (até 20 pontos). O município que ainda não chegou do TSE fica cinza. Clique para ver o estado.",
    apurado: "A cor mostra quanto das seções de cada município já foi apurado: quanto mais forte, mais apurado. Clique para ver o estado.",
    candidato: bm.candidato ? `A cor mostra a votação de ${bm.candidato.nome} em cada município: quanto mais forte, mais votos válidos ele teve ali. Onde ele não ficou entre os dois primeiros o município fica apagado. Clique para ver o estado.` : "",
    vantagem: "Cada pico é um município: a altura é a vantagem em votos de quem lidera nele e a cor é a do partido. Clique para ver o estado.",
  }[modo];
}

async function carregarMunicipiosDoBrasil() {
  clearTimeout(bm.timer);
  const minha = ++bm.seq;
  if (!usaMunicipios() || palco.vista !== "brasil" || document.hidden || !bm.pronto) return;
  const q = new URLSearchParams({ cargo: estado.cargo, uf: "br", turno: estado.turno, ambiente: estado.ambiente });
  const resposta = await tentar("/api/mapa-municipal", q);
  if (minha !== bm.seq) return;
  if (resposta.ok) { bm.dados = resposta.corpo; pintarMunicipios(); }
  const pronto = resposta.ok && resposta.corpo.carregadas >= resposta.corpo.total;
  bm.timer = setTimeout(carregarMunicipiosDoBrasil, pronto ? INTERVALO_BRASIL_MUN_PRONTO : INTERVALO_BRASIL_MUN);
}

function dicaDoMunicipioDoBrasil(ibge) {
  const nome = ((bm.geo && bm.geo.n) || {})[ibge] || "Município", uf = ufDoIbge(ibge), linha = bm.dados && bm.dados.cidades[ibge];
  if (!linha) {
    return [criar("strong", {}, `${nome} (${uf.toUpperCase()})`), criar("span", {}, "Placar da cidade ainda não carregado: o servidor busca as cidades aos poucos.")];
  }
  const candidato = (indice, percentual) => ({ ...bm.dados.candidatos[indice], percentual });
  const lista = [candidato(linha[0], linha[1]), ...(linha[2] >= 0 ? [candidato(linha[2], linha[3])] : [])];
  return cartaoDoLugar({ selo: uf.toUpperCase(), titulo: nome, subtitulo: `${pct(linha[4])} das seções`, candidatos: lista, cor: corDoPartido(lista[0].partido) });
}

/* O município sob o ponteiro: converte a posição na tela para o desenho, filtra pelos retângulos e confere o contorno. */
function municipioSob(clientX, clientY) {
  if (!bm.pronto || !usaMunicipios()) return null;
  const r = bm.svg.getBoundingClientRect(), [vx, vy, vw] = bm.svg.getAttribute("viewBox").split(/\s+/).map(Number);
  if (!r.width) return null;
  const f = MAPA_TAMANHO[0] / bm.geo.w, gx = (vx + (clientX - r.left) * vw / r.width) / f, gy = (vy + (clientY - r.top) * vw / r.width) / f;
  for (let i = bm.ordem.length - 1; i >= 0; i--) {   // o último desenhado fica por cima
    const ibge = bm.ordem[i], [x0, y0, x1, y1] = bm.caixas.get(ibge);
    if (gx < x0 || gx > x1 || gy < y0 || gy > y1) continue;
    if (contextoDeTeste.isPointInPath(bm.paths.get(ibge), gx, gy)) return ibge;
  }
  return null;
}

/* Um ouvinte só para o mapa todo. Clicar num município leva ao estado dele (com o zoom de sempre). */
function ligarEventosDosMunicipios(svg) {
  svg.addEventListener("pointermove", (e) => {
    if (!usaMunicipios() || e.buttons) return;
    const ibge = municipioSob(e.clientX, e.clientY);
    svg.style.cursor = ibge ? "pointer" : "";
    if (ibge) mostrarDicaEm(dicaDoMunicipioDoBrasil(ibge), e.clientX, e.clientY);
    else if (!e.target.closest("[data-uf], .etiqueta")) dica.hidden = true;   // estados e etiquetas cuidam da própria dica
  });
  svg.addEventListener("pointerleave", () => { dica.hidden = true; svg.style.cursor = ""; });   // saiu do mapa: a dica some
  svg.addEventListener("click", (e) => {
    const ibge = usaMunicipios() && !e.target.closest(".etiqueta") ? municipioSob(e.clientX, e.clientY) : null;
    if (ibge) { dica.hidden = true; selecionarUfDoMapa(ufDoIbge(ibge)); }
  });
}

/* Durante o zoom até um estado, os municípios dele ficam e o resto apaga (como os contornos dos estados). */
function marcarMunicipiosDaUf(uf, ligado) {
  bm.focoUf = ligado ? uf : null;
  agendarDesenho();
}

aoPintarUfs.push(() => garantirCamadaDosMunicipios());
aoMudarSelecao.push(function ajustarMapaDosMunicipios() {
  const marca = marcaMapa();
  pintarModosDoMapa();
  if (marca === bm.marca) return;
  bm.marca = marca;
  bm.dados = null;       // outro cargo, turno ou ambiente: os municípios e a conta mudam
  bm.cores.clear();
  if (bm.candidato) { bm.candidato = null; if (bm.modo === "candidato") bm.modo = "municipios"; }
  clearTimeout(bm.timer);
  bm.seq++;
});
