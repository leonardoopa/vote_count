/* Faixa do duelo: os dois primeiros colocados de presidente e governador, com foto, percentual e uma barra em que
   cada candidato cresce do seu lado, então o vazio do meio mostra quanto falta para os 50%. */
const CARGOS_COM_DUELO = ["presidente", "governador"];

function tituloDoDuelo(d, a, b) {
  if (!d.votos.total) return "Aguardando os primeiros votos";
  if (a.eleito) return `Eleição decidida: ${a.nome}`;
  const vaiAoSegundo = (c) => /2º turno/i.test(c.situacao || "");
  if (vaiAoSegundo(a) && vaiAoSegundo(b)) return `${a.nome} e ${b.nome} vão ao 2º turno`;
  const vantagem = pp(a.percentual - b.percentual);
  return d.final ? `Apuração encerrada: ${a.nome} à frente por ${vantagem}` : `${a.nome} lidera por ${vantagem}`;
}

function ladoDoDuelo(c, cor, direita) {
  return criar("div", { class: "duelo-lado" + (direita ? " direita" : "") },
    criar("div", { class: "duelo-foto" }, fotoDoCandidato(c)),
    criar("div", { class: "duelo-texto" },
      criar("div", { class: "duelo-nome" }, c.nome),
      criar("div", { class: "duelo-partido" }, criar("i", { class: "amostra-cor", style: `background:${cor}` }), `${c.partido} · Nº ${c.numero}`),
      criar("div", { class: "duelo-pct" }, pct(c.percentual)),
      criar("div", { class: "duelo-votos" }, `${inteiro(c.votos)} votos`)));
}

function pintarDuelo(d) {
  const [a, b] = d.candidatos;
  const ativo = CARGOS_COM_DUELO.includes(estado.cargo) && a && b;
  $("duelo").hidden = !ativo;
  if (!ativo) return;
  const corA = corDoPartido(a.partido);
  const corB = corDoPartido(b.partido) === corA ? "var(--p-laranja)" : corDoPartido(b.partido);   // dois partidos sem cor própria não podem ficar iguais
  const barra = criar("div", { class: "duelo-barra", role: "img", "aria-label": `${a.nome} ${pct(a.percentual)}, ${b.nome} ${pct(b.percentual)}` },
    criar("i", { class: "esq", style: `width:${Number(a.percentual)}%;background:${corA}` }),
    criar("i", { class: "dir", style: `width:${Number(b.percentual)}%;background:${corB}` }),
    criar("b", { title: "50%" }));
  $("duelo").replaceChildren(
    criar("h2", { class: "duelo-titulo" }, tituloDoDuelo(d, a, b)),
    criar("div", { class: "duelo-linha" }, ladoDoDuelo(a, corA, false), ladoDoDuelo(b, corB, true)),
    barra,
    criar("div", { class: "duelo-rodape" }, criar("span", {}, `${pct(d.secoes.percentual)} das seções apuradas`), criar("span", {}, "marca no meio: 50% dos votos válidos")));
}
aoRenderizar.push(pintarDuelo);
aoMudarSelecao.push(function esconderDuelo() { $("duelo").hidden = true; });
