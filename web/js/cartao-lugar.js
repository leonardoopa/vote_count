/* Cartão que aparece ao passar o mouse num estado ou numa cidade: o selo do lugar, na cor de quem lidera, e os dois
   primeiros colocados com foto, percentual e votos. Vale para o mapa dos estados e para o dos municípios. */
function linhaDoCartao(c) {
  return criar("div", { class: "cartao-linha" },
    fotoDoCandidato(c),
    criar("div", { class: "cartao-quem" },
      criar("div", { class: "cartao-nome" }, c.nome),
      criar("div", { class: "cartao-partido", style: `color:${corDoPartido(c.partido)}` }, `${c.partido}${c.numero ? " " + c.numero : ""}`)),
    criar("div", { class: "cartao-valores" }, criar("b", {}, pct(c.percentual)), ...(c.votos != null ? [criar("small", {}, inteiro(c.votos))] : [])));
}

function cartaoDoLugar({ selo, titulo, subtitulo, candidatos, cor }) {
  return [criar("div", { class: "cartao-lugar" },
    criar("div", { class: "cartao-cab" },
      criar("span", { class: "cartao-selo", style: `background:${cor}` }, selo),
      criar("div", {}, criar("strong", {}, titulo), criar("div", { class: "cartao-sub" }, subtitulo))),
    ...candidatos.map(linhaDoCartao))];
}

/* A cidade chega sem foto: pega a do mesmo candidato no placar que está na tela (ele traz a foto dos primeiros). */
function fotoPeloNumero(numero) {
  const candidato = ultimo && ultimo.candidatos.find((c) => c.numero === numero);
  return candidato ? candidato.foto : null;
}
