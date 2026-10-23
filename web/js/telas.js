/* Tela única: o placar cabe na janela, sem rolar a página.
   Em celular (até 1179 px) uma barra embaixo troca entre quatro telas (mapa, placar, detalhes e ao vivo) e o duelo fica fixo no
   alto de todas. Em tela larga as três colunas aparecem juntas e a barra some. Cada bloco da página diz a que tela pertence em
   `data-na-tela`; o CSS esconde os das outras telas. Uma tela sem nada para mostrar (ex.: "detalhes" no Senado) some da barra. */
const TELAS = [
  { id: "centro", rotulo: () => (cargoComMapa() ? "Mapa" : "Hemiciclo") },
  { id: "placar", rotulo: () => "Placar" },
  { id: "detalhes", rotulo: () => "Detalhes" },
  { id: "aovivo", rotulo: () => "Ao vivo" },
];
const telaUnica = { preferida: "centro", cargo: estado.cargo };

/* O mapa só aparece depois que o servidor responde, mas a tela dele já vale desde o começo (senão a página abriria no placar e pularia). */
const telaTemConteudo = (id) => (id === "centro" && cargoComMapa()) || [...document.querySelectorAll(`[data-na-tela="${id}"]`)].some((el) => !el.hidden);

function pintarBarraDeTelas() {
  const barra = $("barra-telas");
  const visiveis = TELAS.filter((t) => telaTemConteudo(t.id));
  const atual = visiveis.some((t) => t.id === telaUnica.preferida) ? telaUnica.preferida : "placar";
  $("pagina").dataset.tela = atual;
  const marca = `${atual}|${visiveis.map((t) => `${t.id}:${t.rotulo()}`).join(",")}`;
  if (marca === barra.dataset.marca) return;
  barra.dataset.marca = marca;
  barra.replaceChildren(...visiveis.map((t) => {
    const botao = criar("button", { type: "button", "aria-pressed": String(t.id === atual) }, criar("span", { class: `icone icone-${t.id}`, "aria-hidden": "true" }), t.rotulo());
    botao.addEventListener("click", () => irParaTela(t.id));
    return botao;
  }));
}

function irParaTela(id) {
  telaUnica.preferida = id;
  pintarBarraDeTelas();
}

// Trocar de cargo volta para a tela principal; os blocos que aparecem e somem a cada resposta atualizam a barra.
aoMudarSelecao.push(function voltarAoInicioDasTelas() {
  if (estado.cargo !== telaUnica.cargo) { telaUnica.cargo = estado.cargo; telaUnica.preferida = "centro"; }
  pintarBarraDeTelas();
});
if (!embutido) {
  new MutationObserver(pintarBarraDeTelas).observe($("painel"), { subtree: true, attributes: true, attributeFilter: ["hidden"] });
  document.querySelector(".coluna.dir").append(document.querySelector(".rodape"));   // o rodapé é do fim da lista: vai para a última tela (e, em tela larga, para o fim da coluna da direita)
  document.querySelector(".rodape").dataset.naTela = "aovivo";
  pintarBarraDeTelas();
}
