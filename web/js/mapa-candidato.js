/* O candidato escolhido no mapa (tocando na foto dele no duelo, ou no menu "Mais mapas"): o mapa passa a mostrar a votação
   dele em cada município, os rótulos dos estados mostram o percentual dele e este painel conta quanto ele teve no Brasil e
   onde foi melhor e pior. Tocar de novo na foto, ou em "Voltar", volta ao mapa por município. */
const FAIXA_DO_CANDIDATO_POR_UF = [15, 70];   // da votação mais fraca à mais forte, na escala de cor dos estados

/* A votação do candidato num estado (null onde ele não é um dos dois primeiros, que são os que o resumo por estado traz). */
function percentualNaUf(r, numero) {
  if (!r || r.situacao !== "lider") return null;
  for (const c of [r.lider, r.segundo]) if (c && c.numero === numero) return c.percentual;
  return null;
}

const estiloDoCandidatoNaUf = (p, partido) => (p === null ? "fill:var(--muted);fill-opacity:0.12" : `fill:${corDoPartido(partido)};fill-opacity:${(0.2 + 0.8 * Math.min(Math.max((p - FAIXA_DO_CANDIDATO_POR_UF[0]) / (FAIXA_DO_CANDIDATO_POR_UF[1] - FAIXA_DO_CANDIDATO_POR_UF[0]), 0), 1)).toFixed(2)}`);

function escolherCandidatoNoMapa(candidato) {
  if (candidato && (estado.cargo !== "presidente" || !temMapa())) return;
  bm.candidato = candidato;
  bm.modo = candidato ? "candidato" : "municipios";
  bm.cores.clear();
  bm.indice = null;
  if (candidato && palco.vista !== "brasil") voltarAoBrasil();
  aplicarModoDoMapa();
  pintarMunicipios();
  carregarMunicipiosDoBrasil();
  if (mapaDados) atualizarRotulosDosEstados(mapaDados);
  pintarPainelDoCandidato();
  if (ultimo) pintarDuelo(ultimo);
}

function linhaDeEstado(uf, p, cor, maior) {
  const botao = criar("button", { class: "botao-link", type: "button", "aria-label": `Ver o placar de ${UFS[uf]}` }, UFS[uf]);
  botao.addEventListener("click", () => selecionarUfDoMapa(uf));
  return criar("li", { class: "candidato-uf" },
    criar("span", { class: "candidato-sigla" }, uf.toUpperCase()), botao,
    criar("div", { class: "rq-trilho" }, criar("div", { class: "rq-barra", style: `width:${(p / maior) * 100}%;background:${cor}` })),
    criar("b", { class: "num" }, pct(p)));
}

function pintarPainelDoCandidato() {
  const painel = $("candidato"), c = bm.candidato;
  painel.hidden = !(c && temMapa() && palco.vista === "brasil" && mapaDados);
  if (painel.hidden) return;
  const nacional = ultimo && estado.uf === "br" ? ultimo.candidatos.find((x) => x.numero === c.numero) : null;
  const votos = nacional ? nacional.votos : ((mapaDados.candidatos || []).find((x) => x.numero === c.numero) || {}).votos;
  const cor = corDoPartido(c.partido);
  const porUf = Object.keys(UFS).map((uf) => [uf, percentualNaUf(mapaDados.ufs[uf], c.numero)]).filter(([, p]) => p !== null).sort((a, b) => b[1] - a[1]);
  const maior = porUf.length ? porUf[0][1] : 1;
  const fechar = criar("button", { class: "botao-link candidato-fechar", type: "button", "aria-label": "Fechar o painel do candidato" }, "✕");
  fechar.addEventListener("click", () => escolherCandidatoNoMapa(null));
  const voltar = criar("button", { class: "botao-link", type: "button" }, "‹ Voltar");
  voltar.addEventListener("click", () => escolherCandidatoNoMapa(null));
  const linha = (rotulo, valor) => criar("div", { class: "candidato-dado" }, criar("span", {}, rotulo), criar("b", {}, valor));
  painel.replaceChildren(
    voltar,
    criar("div", { class: "candidato-cab" }, criar("div", { class: "candidato-foto" }, fotoDoCandidato(c)),
      criar("div", {}, criar("h2", { class: "candidato-nome" }, c.nome), criar("div", { class: "candidato-partido", style: `color:${cor}` }, `${c.partido} · Presidente`)), fechar),
    criar("div", { class: "candidato-pct" }, criar("b", {}, nacional ? pct(nacional.percentual) : "—"), criar("span", {}, "dos votos válidos no Brasil")),
    linha("Votos", votos != null ? inteiro(votos) : "—"),
    linha("Situação", nacional ? (nacional.eleito ? "Eleito" : nacional.situacao || "—") : (c.situacao || "—")),
    linha("Seções apuradas", ultimo ? pct(ultimo.secoes.percentual) : "—"),
    ...(porUf.length ? [
      criar("h3", { class: "candidato-sub" }, "Onde vai melhor"),
      criar("ol", { class: "candidato-lista" }, ...porUf.slice(0, 5).map(([uf, p]) => linhaDeEstado(uf, p, cor, maior))),
      criar("h3", { class: "candidato-sub" }, "Onde vai pior"),
      criar("ol", { class: "candidato-lista" }, ...porUf.slice(-3).reverse().map(([uf, p]) => linhaDeEstado(uf, p, cor, maior))),
    ] : [criar("p", { class: "meta" }, "O resultado por estado ainda está chegando.")]));
}

aoPintarUfs.push(pintarPainelDoCandidato);
aoMudarSelecao.push(function ajustarPainelDoCandidato() { pintarPainelDoCandidato(); });
