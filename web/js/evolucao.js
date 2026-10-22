/* Evolução da apuração, replay e atualizações. */
const EVO = { W: 640, H: 300, E: 46, D: 12, T: 14, B: 30 };  // tamanho do desenho e margens (esquerda, direita, topo, base)
const EVO_LINHAS = 6;
const TRACOS = ["", "8 4", "2 4", "10 3 2 3", "4 2"];       // candidatos da mesma cor se distinguem também pelo traço
const CARGOS_COM_SERIE = ["presidente", "governador", "senador"];
let evo = null;                  // {candidatos, pontos} da seleção atual
let evoMarca = "", evoSeq = 0;
let evoLinhas = [];              // linhas desenhadas: {c, cor, traco}
let evoCursor = null;            // elementos do cursor dentro do SVG
const replay = { indice: -1, tocando: false, timer: 0 };   // indice -1 = ao vivo (último ponto)

const temSerie = () => CARGOS_COM_SERIE.includes(estado.cargo);
const pontoComVoto = (p) => p.placar.some((linha) => linha[1] > 0);
const linhaDo = (p, numero) => p.placar.find((linha) => linha[0] === numero);
const iX = (percentual) => EVO.E + (percentual / 100) * (EVO.W - EVO.E - EVO.D);

function amostra(cor, traco) {
  return criarSvg("svg", { width: 18, height: 8, viewBox: "0 0 18 8", "aria-hidden": "true" },
    criarSvg("line", { x1: 0, y1: 4, x2: 18, y2: 4, style: `stroke:${cor};stroke-width:3;stroke-linecap:round;stroke-dasharray:${traco || "none"}` }));
}

function escolherLinhas() {
  const usadas = {};
  return evo.candidatos.slice(0, EVO_LINHAS).map((c) => {
    const cor = corDoPartido(c.partido);
    usadas[cor] = (usadas[cor] ?? -1) + 1;
    return { c, cor, traco: TRACOS[usadas[cor] % TRACOS.length] };
  });
}

function limitesY() {
  const valores = [];
  for (const p of evo.pontos) {
    if (!pontoComVoto(p)) continue;
    for (const { c } of evoLinhas) { const l = linhaDo(p, c.numero); if (l) valores.push(l[2]); }
  }
  let baixo = Math.max(0, Math.floor(Math.min(...valores) / 10) * 10);
  let alto = Math.min(100, Math.ceil(Math.max(...valores) / 10) * 10);
  if (alto - baixo < 10) alto = Math.min(100, baixo + 10);
  return [baixo, alto, alto - baixo <= 20 ? 5 : 10];
}

function desenharGrafico() {
  const { W, H, E, D, T, B } = EVO;
  const [baixo, alto, passo] = limitesY();
  const iY = (v) => T + (1 - (v - baixo) / (alto - baixo)) * (H - T - B);
  const svg = criarSvg("svg", {
    viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0",
    "aria-label": "Gráfico de linhas: percentual de cada candidato conforme as seções são apuradas. Use as setas para percorrer as totalizações; os números também estão na tabela abaixo.",
  });
  for (let v = baixo; v <= alto; v += passo) {
    svg.append(
      criarSvg("line", { x1: E, x2: W - D, y1: iY(v), y2: iY(v), style: `stroke:var(${v === baixo ? "--baseline" : "--grid"});stroke-width:1` }),
      criarSvg("text", { x: E - 8, y: iY(v) + 4, "text-anchor": "end" }, `${v}%`));
  }
  for (const v of [0, 25, 50, 75, 100]) {
    svg.append(criarSvg("text", { x: iX(v), y: H - 8, "text-anchor": v === 0 ? "start" : v === 100 ? "end" : "middle" }, `${v}%`));
  }
  for (const { c, cor, traco } of evoLinhas) {
    let segmento = [];
    const fechar = () => {
      if (segmento.length > 1) {
        svg.append(criarSvg("polyline", { points: segmento.join(" "), style: `fill:none;stroke:${cor};stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:${traco || "none"}` }));
      }
      segmento = [];
    };
    let fim = null;
    for (const p of evo.pontos) {
      const l = pontoComVoto(p) ? linhaDo(p, c.numero) : null;
      if (!l) { fechar(); continue; }
      fim = [iX(p.percentual), iY(l[2])];
      segmento.push(fim.map((n) => n.toFixed(1)).join(","));
    }
    fechar();
    if (fim) svg.append(criarSvg("circle", { cx: fim[0], cy: fim[1], r: 3.5, style: `fill:${cor}` }));
  }
  const regua = criarSvg("line", { y1: T, y2: H - B, style: "stroke:var(--ink-2);stroke-width:1;stroke-dasharray:3 3" });
  const bolas = evoLinhas.map(({ cor }) => criarSvg("circle", { r: 4.5, style: `fill:${cor};stroke:var(--surface);stroke-width:2` }));
  const grupo = criarSvg("g", { visibility: "hidden", "pointer-events": "none" }, regua, ...bolas);
  svg.append(grupo);
  evoCursor = { grupo, regua, bolas, iY };

  const maisPerto = (clientX) => {
    const r = svg.getBoundingClientRect();
    const alvo = ((clientX - r.left) * (W / r.width) - E) / (W - E - D) * 100;
    let melhor = 0;
    evo.pontos.forEach((p, i) => { if (Math.abs(p.percentual - alvo) < Math.abs(evo.pontos[melhor].percentual - alvo)) melhor = i; });
    return melhor;
  };
  const explorar = (i, x, y) => { posicionarCursor(i); mostrarDicaEm(dicaDaEvolucao(i), x, y); };
  svg.addEventListener("pointermove", (e) => explorar(maisPerto(e.clientX), e.clientX, e.clientY));
  svg.addEventListener("pointerleave", () => { dica.hidden = true; mostrarReplay(); });
  svg.addEventListener("blur", () => { dica.hidden = true; mostrarReplay(); });
  svg.addEventListener("keydown", (e) => {
    const n = evo.pontos.length, atual = replay.indice < 0 ? n - 1 : replay.indice;
    const alvo = { ArrowLeft: atual - 1, ArrowRight: atual + 1, Home: 0, End: n - 1 }[e.key];
    if (alvo === undefined) return;
    e.preventDefault();
    irParaPonto(Math.max(0, Math.min(n - 1, alvo)));
    const r = svg.getBoundingClientRect();
    mostrarDicaEm(dicaDaEvolucao(replay.indice < 0 ? n - 1 : replay.indice), r.left + iX(evo.pontos[replay.indice < 0 ? n - 1 : replay.indice].percentual) * (r.width / W), r.top + r.height / 2);
  });
  return svg;
}

function posicionarCursor(i) {
  if (!evoCursor) return;
  const p = evo.pontos[i], x = iX(p.percentual);
  evoCursor.regua.setAttribute("x1", x);
  evoCursor.regua.setAttribute("x2", x);
  evoLinhas.forEach(({ c }, k) => {
    const l = pontoComVoto(p) ? linhaDo(p, c.numero) : null;
    const bola = evoCursor.bolas[k];
    bola.setAttribute("visibility", l ? "visible" : "hidden");
    if (l) { bola.setAttribute("cx", x); bola.setAttribute("cy", evoCursor.iY(l[2])); }
  });
  evoCursor.grupo.setAttribute("visibility", "visible");
}

function dicaDaEvolucao(i) {
  const p = evo.pontos[i];
  const nos = [criar("strong", {}, `${pct(p.percentual)} das seções`), criar("span", {}, p.totalizacao || "Antes da apuração")];
  for (const { c, cor, traco } of evoLinhas) {
    const l = pontoComVoto(p) ? linhaDo(p, c.numero) : null;
    if (l) nos.push(criar("div", { class: "evo-dica-linha" }, amostra(cor, traco), c.nome, criar("b", {}, pct(l[2]))));
  }
  return nos;
}

function pintarEvolucao() {
  const pontos = evo.pontos, comVoto = pontos.filter(pontoComVoto).length;
  $("evo").hidden = false;
  $("evo-info").textContent = pontos.length ? `${pontos.length} ${pontos.length > 1 ? "totalizações guardadas" : "totalização guardada"}` : "";
  const sem = comVoto < 2;
  $("evo-corpo").hidden = sem;
  $("evo-nota").hidden = !sem;
  if (sem) {
    pararReplay();
    $("evo-nota").textContent = comVoto === 0
      ? "A apuração ainda não começou. O gráfico aparece com as primeiras totalizações."
      : "O gráfico aparece a partir da segunda totalização. Este servidor guarda os pontos desde que a primeira pessoa abriu a página.";
    return;
  }
  evoLinhas = escolherLinhas();
  $("evo-legenda").replaceChildren(...evoLinhas.map(({ c, cor, traco }) => criar("li", {}, amostra(cor, traco), `${c.nome} (${c.partido})`)));
  $("evo-grafico").replaceChildren(desenharGrafico());
  const cabecalho = criar("tr", {}, criar("th", {}, "Totalização"), criar("th", {}, "Seções"), ...evoLinhas.map(({ c }) => criar("th", {}, c.nome)));
  const linhas = pontos.filter(pontoComVoto).reverse().map((p) => criar("tr", {},
    criar("td", {}, p.totalizacao), criar("td", {}, pct(p.percentual)),
    ...evoLinhas.map(({ c }) => { const l = linhaDo(p, c.numero); return criar("td", {}, l ? pct(l[2]) : "—"); })));
  $("evo-tabela").replaceChildren(criar("thead", {}, cabecalho), criar("tbody", {}, ...linhas));
  if (replay.indice >= pontos.length - 1) replay.indice = -1;
  $("replay-linha").max = pontos.length - 1;
  mostrarReplay();
}

/* Replay: percorre os pontos guardados; "ao vivo" = último ponto (índice -1). */
function mostrarReplay() {
  if (!evo || !evoCursor) return;
  const n = evo.pontos.length, vivo = replay.indice < 0, i = vivo ? n - 1 : replay.indice, p = evo.pontos[i];
  const linha = $("replay-linha");
  linha.value = i;
  linha.setAttribute("aria-valuetext", `Totalização ${i + 1} de ${n}, ${pct(p.percentual)} das seções`);
  $("replay-hora").textContent = `${vivo ? "Ao vivo · " : ""}${p.totalizacao || "antes da apuração"} · ${pct(p.percentual)} das seções`;
  $("replay-play").textContent = replay.tocando ? "⏸ Pausar" : "▶ Reproduzir a apuração";
  $("replay-play").setAttribute("aria-pressed", String(replay.tocando));
  const quadro = $("replay-quadro");
  quadro.hidden = vivo;
  if (vivo) { evoCursor.grupo.setAttribute("visibility", "hidden"); return; }
  posicionarCursor(i);
  const nomes = Object.fromEntries(evo.candidatos.map((c) => [c.numero, c]));
  const topo = p.placar.slice(0, 5), maior = Math.max(...topo.map((l) => l[2]), 1);
  quadro.replaceChildren(...topo.map(([numero, , percentual]) => {
    const c = nomes[numero] || { nome: numero, partido: "" };
    return criar("li", {},
      criar("span", {}, `${c.nome} (${c.partido})`),
      criar("div", { class: "rq-trilho" }, criar("div", { class: "rq-barra", style: `width:${(percentual / maior) * 100}%;background:${corDoPartido(c.partido)}` })),
      criar("b", { class: "num" }, pct(percentual)));
  }));
}

function irParaPonto(i) {
  replay.indice = i >= evo.pontos.length - 1 ? -1 : i;
  mostrarReplay();
}

function pararReplay() {
  clearInterval(replay.timer);
  replay.tocando = false;
}

function alternarReplay() {
  if (replay.tocando) { pararReplay(); mostrarReplay(); return; }
  if (!evo || evo.pontos.length < 2) return;
  if (replay.indice < 0) replay.indice = 0;
  replay.tocando = true;
  const passoMs = evo.pontos.length > 60 ? 250 : 600;
  replay.timer = setInterval(() => {
    const proximo = replay.indice + 1;
    if (proximo >= evo.pontos.length - 1) { pararReplay(); replay.indice = -1; }
    else replay.indice = proximo;
    mostrarReplay();
  }, passoMs);
  mostrarReplay();
}

function pintarFeed(eventos) {
  $("feed").hidden = false;
  $("feed-info").textContent = eventos.length >= 40 ? "40 mais recentes" : eventos.length ? `${eventos.length} ${eventos.length > 1 ? "atualizações" : "atualização"}` : "";
  $("feed-lista").replaceChildren(...(eventos.length
    ? eventos.map((e) => criar("li", {}, criar("time", {}, e.hora), criar("span", e.tipo === "totalizacao" ? {} : { class: "destaque" }, e.texto)))
    : [criar("li", { class: "vazio" }, "Nenhuma atualização registrada ainda. Elas aparecem a cada totalização nova do TSE.")]));
}

async function carregarEvolucao() {
  const minha = ++evoSeq;
  try {
    const q = consultaSelecao();
    const [historico, atualizacoes] = await Promise.all(["/api/historico?", "/api/atualizacoes?"].map((rota) => fetch(rota + q, { cache: "no-store" })));
    if (!historico.ok || !atualizacoes.ok) throw new Error("sem série");
    const [serie, feed] = [await historico.json(), await atualizacoes.json()];
    if (minha !== evoSeq) return;
    evo = serie;
    pintarEvolucao();
    pintarFeed(feed.eventos);
  } catch { /* sem série não há gráfico nem feed: o placar continua */ }
}

aoRenderizar.push((d) => {
  $("evo").hidden = $("feed").hidden = $("evo").hidden || !temSerie();
  if (!temSerie()) return;
  const marca = [estado.cargo, estado.uf, estado.turno, estado.ambiente, estado.municipio, d.ultima_totalizacao, d.secoes.apuradas, d.votos.total, d.final, d.candidatos.filter((c) => c.situacao).length].join("|");
  if (marca === evoMarca) return;
  evoMarca = marca;
  carregarEvolucao();
});
aoMudarSelecao.push(() => {
  pararReplay();
  evoSeq++;
  evo = null; evoCursor = null; evoMarca = "";
  replay.indice = -1;
  $("evo").hidden = $("feed").hidden = true;
});
$("replay-play").addEventListener("click", alternarReplay);
$("replay-linha").addEventListener("input", (e) => { pararReplay(); irParaPonto(Number(e.target.value)); });
