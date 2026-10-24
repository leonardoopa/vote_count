/* Rótulos do mapa do Brasil: a sigla e o percentual do líder dentro de cada estado grande, e uma etiqueta ao lado do
   mapa, com uma linha até o estado, para os pequenos do litoral (que não cabem escrita) e para o Exterior. */
const ESTADOS_EM_ETIQUETA = ["rn", "pb", "pe", "al", "se", "es", "rj"];
const ETIQUETA = { x: 1024, largura: 86, altura: 26, passo: 31 };

const percentualInteiro = (r) => (r && r.situacao === "lider" ? `${Math.round(r.lider.percentual)}%` : "—");

function criarEtiqueta(grupo, rotulo, cy, y, aoPassar, aoClicar) {
  const g = criarSvg("g", { class: "etiqueta", tabindex: "0", role: "button", "aria-label": rotulo });
  const retangulo = criarSvg("rect", { x: ETIQUETA.x, y, width: ETIQUETA.largura, height: ETIQUETA.altura, rx: 5 });
  const sigla = criarSvg("text", { class: "etiqueta-sigla", x: ETIQUETA.x + 9, y: y + 18 }, rotulo);
  const percentual = criarSvg("text", { class: "etiqueta-pct", x: ETIQUETA.x + ETIQUETA.largura - 9, y: y + 18, "text-anchor": "end" }, "");
  g.append(retangulo, sigla, percentual);
  g.addEventListener("pointermove", (e) => mostrarDicaEm(aoPassar(), e.clientX, e.clientY));
  g.addEventListener("pointerleave", () => { dica.hidden = true; });
  g.addEventListener("click", () => { dica.hidden = true; aoClicar(); });
  g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); aoClicar(); } });
  grupo.append(g);
  return { g, retangulo, percentual, cy };
}

function dicaDoExterior() {
  const r = mapaDados && mapaDados.exterior;
  if (!r || r.situacao !== "lider") return [criar("strong", {}, "Exterior"), criar("span", {}, "Votos de brasileiros no exterior: ainda sem líder")];
  return cartaoDoLugar({ selo: "EX", titulo: "Exterior", subtitulo: `${pct(r.apurado)} das seções`, candidatos: [r.lider, r.segundo].filter(Boolean), cor: corDoPartido(r.lider.partido) });
}

/* O desenho tem 1120 unidades de largura e no celular aparece com uns 350 px: uma letra de 20 unidades sairia com 6 px. `--upp`
   (unidades do desenho por pixel da tela) deixa o CSS escrever o tamanho em pixels, e a sigla fica legível em qualquer tela e com zoom. */
function escalarRotulosPelaTela(svg) {
  const escalar = () => {
    const m = svg.getScreenCTM();
    if (m && m.a) svg.style.setProperty("--upp", (1 / m.a).toFixed(4));
  };
  new ResizeObserver(escalar).observe(svg);
  new MutationObserver(escalar).observe(svg, { attributes: true, attributeFilter: ["viewBox"] });   // o zoom do mapa mexe no viewBox
  escalar();
}

aoConstruirMapa.push(function montarRotulosDosEstados(mapa) {
  const porcentagens = new Map(), etiquetas = new Map(), linhas = criarSvg("g", { class: "etiquetas-linhas", "aria-hidden": "true" }), grupo = criarSvg("g", { class: "etiquetas" });
  for (const [uf, forma] of Object.entries(MAPA_UFS)) {
    if (forma.l < 90 || ESTADOS_EM_ETIQUETA.includes(uf)) continue;
    // `dy` em em: o rótulo cresce junto com o tamanho da letra (que acompanha a tela, veja `--upp` abaixo) sem sair do lugar
    const pctDoEstado = criarSvg("text", { class: "uf-pct", x: forma.c[0], y: forma.c[1], dy: "1.05em", "text-anchor": "middle" }, "");
    mapa.rotulos.append(criarSvg("text", { class: "uf-sigla", x: forma.c[0], y: forma.c[1], dy: "-0.12em", "text-anchor": "middle" }, uf.toUpperCase()), pctDoEstado);
    porcentagens.set(uf, pctDoEstado);
  }
  let y = 0;
  for (const uf of [...ESTADOS_EM_ETIQUETA].sort((a, b) => MAPA_UFS[a].c[1] - MAPA_UFS[b].c[1])) {
    const [cx, cy] = MAPA_UFS[uf].c;
    y = Math.max(y + ETIQUETA.passo, cy - ETIQUETA.altura / 2);   // as etiquetas não se encostam, mas ficam perto da altura do estado
    linhas.append(criarSvg("line", { x1: cx, y1: cy, x2: ETIQUETA.x, y2: y + ETIQUETA.altura / 2 }));
    const etiqueta = criarEtiqueta(grupo, uf.toUpperCase(), cy, y, () => dicaDaUf(uf, mapaDados && mapaDados.ufs[uf]), () => selecionarUfDoMapa(uf));
    etiquetas.set(uf, etiqueta);
  }
  const exterior = criarEtiqueta(grupo, "EX", 0, y + ETIQUETA.passo + 8, dicaDoExterior, () => irParaVista("mundo"));
  exterior.g.classList.add("etiqueta-exterior");
  exterior.g.hidden = true;
  mapa.svg.insertBefore(linhas, mapa.ondas);
  mapa.svg.insertBefore(grupo, mapa.ondas);
  escalarRotulosPelaTela(mapa.svg);
  mapa.porcentagens = porcentagens;
  mapa.etiquetas = etiquetas;
  mapa.exterior = exterior;
});

/* "■ 71%" embaixo da sigla: o quadradinho tem a cor do partido de quem lidera (ou do candidato escolhido no mapa). */
function escreverPercentualDoEstado(texto, r, alvo) {
  const p = alvo ? percentualNaUf(r, alvo.numero) : (r && r.situacao === "lider" ? r.lider.percentual : null);
  if (p === null) { texto.textContent = "—"; return; }
  const partido = alvo ? alvo.partido : r.lider.partido;
  texto.replaceChildren(criarSvg("tspan", { class: "uf-cor", style: `fill:${corDoPartido(partido)}` }, "■"), ` ${Math.round(p)}%`);
}

/* A cada rodada: o percentual de cada estado e a cor de cada etiqueta (a mesma cor do estado, com a mesma força). */
function atualizarRotulosDosEstados(d) {
  const mapa = mapaSvg;
  if (!mapa || !mapa.etiquetas) return;
  const alvo = temMapa() && bm.modo === "candidato" ? bm.candidato : null;   // com um candidato escolhido, valem a votação e a cor dele
  const percentual = (r) => { if (!alvo) return percentualInteiro(r); const p = percentualNaUf(r, alvo.numero); return p === null ? "—" : `${Math.round(p)}%`; };
  const estilo = (r) => (alvo ? estiloDoCandidatoNaUf(percentualNaUf(r, alvo.numero), alvo.partido) : pintura(r));
  for (const [uf, texto] of mapa.porcentagens) escreverPercentualDoEstado(texto, d.ufs[uf], alvo);
  for (const [uf, etiqueta] of mapa.etiquetas) {
    etiqueta.retangulo.setAttribute("style", estilo(d.ufs[uf]));
    etiqueta.percentual.textContent = percentual(d.ufs[uf]);
  }
  const exterior = d.exterior;
  mapa.exterior.g.hidden = !exterior || estado.cargo !== "presidente";
  if (exterior) {
    mapa.exterior.retangulo.setAttribute("style", estilo(exterior));
    mapa.exterior.percentual.textContent = percentual(exterior);
  }
}
aoPintarUfs.push(atualizarRotulosDosEstados);
