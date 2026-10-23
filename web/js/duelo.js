/* Faixa do duelo: os dois primeiros colocados de presidente e governador, sempre na mesma posição (o menor número à
   esquerda). Quem está na frente aparece maior, com anel e brilho na cor do partido, e uma seta no meio aponta para o
   lado dele com a vantagem em pontos: dá para ver quem lidera sem ler uma frase. */
const CARGOS_COM_DUELO = ["presidente", "governador"];

/* Duas setas apontando para um lado: a vantagem "empurra" a barra para quem está na frente. */
function setasDoDuelo(para) {
  const sentido = para === "esq" ? -1 : 1, base = para === "esq" ? 26 : 2;
  const ponta = (x) => `M${x - 6 * sentido} 4 L${x + 6 * sentido} 14 L${x - 6 * sentido} 24`;
  return criarSvg("svg", { class: "duelo-setas", viewBox: "0 0 28 28", "aria-hidden": "true" },
    criarSvg("path", { d: ponta(base), class: "forte" }), criarSvg("path", { d: ponta(base - 12 * sentido), class: "fraca" }));
}

function ladoDoDuelo(c, cor, direita, lidera, temLider) {
  const escolhido = estado.cargo === "presidente" && bm.candidato && bm.candidato.numero === c.numero;
  const classe = "duelo-lado" + (direita ? " direita" : "") + (lidera ? " lider" : temLider ? " atras" : "") + (escolhido ? " escolhido" : "");
  const foto = criar("div", { class: "duelo-foto", style: `--cor:${cor}` }, fotoDoCandidato(c));
  if (c.eleito) foto.append(criar("span", { class: "duelo-selo", title: "Eleito" }, "✓"));
  const lado = criar("div", { class: classe, style: `--cor:${cor}`, ...(estado.cargo === "presidente" ? { role: "button", tabindex: "0", "aria-pressed": String(escolhido), title: escolhido ? "Voltar ao mapa por município" : `Ver no mapa onde ${c.nome} vai melhor` } : {}) },
    foto,
    criar("div", { class: "duelo-texto" },
      criar("div", { class: "duelo-nome" }, c.nome),
      criar("div", { class: "duelo-partido" }, criar("i", { class: "amostra-cor", style: `background:${cor}` }), `${c.partido} · Nº ${c.numero}`, ...(c.segundo_turno || /2º turno/i.test(c.situacao || "") ? [criar("span", { class: "duelo-chip" }, "2º turno")] : [])),
      criar("div", { class: "duelo-pct" }, pct(c.percentual)),
      criar("div", { class: "duelo-votos" }, `${inteiro(c.votos)} votos`)));
  if (estado.cargo === "presidente") {   // tocar na foto mostra no mapa a votação dele; tocar de novo volta
    const escolher = () => escolherCandidatoNoMapa(escolhido ? null : { numero: c.numero, nome: c.nome, partido: c.partido, foto: c.foto, situacao: c.situacao });
    lado.addEventListener("click", escolher);
    lado.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escolher(); } });
  }
  return lado;
}

function pintarDuelo(d) {
  const [primeiro, segundo] = d.candidatos;
  const ativo = CARGOS_COM_DUELO.includes(estado.cargo) && primeiro && segundo;
  $("duelo").hidden = !ativo;
  if (!ativo) return;
  const temLider = d.votos.total > 0 && primeiro.votos !== segundo.votos;
  const [a, b] = Number(primeiro.numero) <= Number(segundo.numero) ? [primeiro, segundo] : [segundo, primeiro];
  const corA = corDoPartido(a.partido);
  const corB = corDoPartido(b.partido) === corA ? "var(--p-laranja)" : corDoPartido(b.partido);   // dois partidos sem cor própria não podem ficar iguais
  const lado = !temLider ? "" : primeiro === a ? "esq" : "dir";
  const corDoLider = lado === "esq" ? corA : corB;
  bm.candidatosDoDuelo = [a, b].map((c) => ({ numero: c.numero, nome: c.nome, partido: c.partido, foto: c.foto, situacao: c.situacao }));   // o menu do mapa oferece os mesmos dois
  const vantagem = temLider ? pp(primeiro.percentual - segundo.percentual).replace(" p.p.", "") : "—";
  const centro = criar("div", { class: "duelo-centro", style: `--cor:${corDoLider}`, "data-para": lado, title: temLider ? `${primeiro.nome} está ${pp(primeiro.percentual - segundo.percentual)} à frente` : "Sem líder ainda" },
    ...(lado === "dir" ? [] : lado === "esq" ? [setasDoDuelo("esq")] : []),
    criar("div", { class: "duelo-vantagem" }, criar("b", {}, vantagem), criar("small", {}, "p.p.")),
    ...(lado === "dir" ? [setasDoDuelo("dir")] : []));
  const barra = criar("div", { class: "duelo-barra", role: "img", "aria-label": `${a.nome} ${pct(a.percentual)}, ${b.nome} ${pct(b.percentual)}` },
    criar("i", { class: "esq" + (lado === "esq" ? " lider" : ""), style: `width:${Number(a.percentual)}%;background:${corA};--cor:${corA}` }),
    criar("i", { class: "dir" + (lado === "dir" ? " lider" : ""), style: `width:${Number(b.percentual)}%;background:${corB};--cor:${corB}` }),
    criar("b", { title: "50%" }));
  $("duelo").replaceChildren(
    criar("div", { class: "duelo-linha" }, ladoDoDuelo(a, corA, false, lado === "esq", temLider), centro, ladoDoDuelo(b, corB, true, lado === "dir", temLider)),
    barra,
    criar("div", { class: "duelo-rodape" }, criar("span", {}, `${pct(d.secoes.percentual)} das seções apuradas`), criar("span", {}, "marca no meio: 50% dos votos válidos")));
}
aoRenderizar.push(pintarDuelo);
aoMudarSelecao.push(function esconderDuelo() { $("duelo").hidden = true; });
