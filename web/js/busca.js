/* Busca rápida ("/" ou Ctrl/⌘+K). Cargos, estados e candidatos filtram na hora; as cidades vêm do servidor (lista já em cache). */
let buscaItens = [], buscaAtivo = 0, buscaSeq = 0, buscaTimer = 0, buscaCidades = [];

function irParaCidade({ uf, codigo }) {
  estado.uf = uf;
  estado.municipio = codigo;
  estado.top = TOP_INICIAL;
  ultimo = null;
  sincronizarFiltros();
  carregar();
  atualizarCidades();   // carrega a lista da UF e confere se a cidade existe lá
  avisar(aoMudarSelecao);
}

function destacarCandidato(posicao) {
  const alvo = $("ranking").children[posicao - 1];
  if (!alvo) return;
  irParaTela("placar");   // em celular a lista de candidatos é a tela "Placar"
  alvo.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  alvo.focus({ preventScroll: true });
}

function resultadosLocais(termo) {
  const alvo = semAcento(termo);
  if (!alvo) return { cargos: [], estados: [], candidatos: [] };
  const grupo = (nome, itens) => itens.slice(0, 6).map((item) => ({ grupo: nome, ...item }));
  return {
    cargos: grupo("Cargos", Object.entries(CARGOS).filter(([, nome]) => semAcento(nome).includes(alvo))
      .map(([codigo, nome]) => ({ rotulo: nome, detalhe: codigo === estado.cargo ? "cargo atual" : "", abrir: () => trocou("cargo", codigo) }))),
    estados: grupo("Estados", ufsDoCargo(estado.cargo).filter((uf) => uf === alvo || semAcento(uf === "br" ? "Brasil" : UFS[uf]).includes(alvo))
      .map((uf) => ({ rotulo: uf === "br" ? "Brasil" : UFS[uf], detalhe: uf === "br" ? "" : uf.toUpperCase(), abrir: () => trocou("uf", uf) }))),
    candidatos: grupo("Candidatos", ultimo ? ultimo.candidatos.filter((c) => semAcento(`${c.nome} ${c.partido} ${c.numero}`).includes(alvo))
      .map((c) => ({ rotulo: c.nome, detalhe: `${c.partido} · ${pct(c.percentual)}`, abrir: () => destacarCandidato(c.posicao) })) : []),
  };
}

function pintarBusca() {
  const termo = $("busca-campo").value;
  const locais = resultadosLocais(termo);
  buscaItens = [...locais.cargos, ...locais.estados, ...buscaCidades, ...locais.candidatos];
  buscaAtivo = Math.min(buscaAtivo, Math.max(0, buscaItens.length - 1));
  const lista = $("busca-lista");
  lista.replaceChildren();
  let grupoAtual = "";
  buscaItens.forEach((item, i) => {
    if (item.grupo !== grupoAtual) { grupoAtual = item.grupo; lista.append(criar("li", { role: "presentation", class: "grupo" }, grupoAtual)); }
    const opcao = criar("li", { role: "option", id: `busca-op-${i}`, "aria-selected": String(i === buscaAtivo) }, criar("span", {}, item.rotulo), criar("span", { class: "meta" }, item.detalhe));
    opcao.addEventListener("pointerdown", (e) => { e.preventDefault(); escolherNaBusca(i); });
    lista.append(opcao);
  });
  $("busca-campo").setAttribute("aria-activedescendant", buscaItens.length ? `busca-op-${buscaAtivo}` : "");
  $("busca-ajuda").textContent = !termo.trim() ? "Digite um estado, uma cidade, um cargo ou um candidato."
    : buscaItens.length ? "↑ ↓ para escolher · Enter para abrir · Esc para fechar" : "Nada encontrado.";
  const ativa = $(`busca-op-${buscaAtivo}`);
  if (ativa) ativa.scrollIntoView({ block: "nearest" });
}

function buscarCidadesNoServidor(termo) {
  clearTimeout(buscaTimer);
  const minha = ++buscaSeq;
  buscaCidades = [];
  if (semAcento(termo).length < 2) return;
  const daLista = (c) => ({ grupo: "Cidades", rotulo: c.nome, detalhe: UFS[c.uf], abrir: () => irParaCidade(c) });
  buscaTimer = setTimeout(async () => {
    let achadas;
    try {
      const q = new URLSearchParams({ cargo: estado.cargo, ambiente: estado.ambiente, q: termo.trim() });
      const resposta = await fetch("/api/busca?" + q, { cache: "no-store" });
      const corpo = await resposta.json();
      if (!resposta.ok) throw new Error("sem lista");
      achadas = corpo.cidades;
    } catch {   // servidor sem a lista do TSE: ainda dá para achar entre as cidades do estado que está na tela
      achadas = cidades.filter((c) => semAcento(c.nome).includes(semAcento(termo))).slice(0, 10).map((c) => ({ ...c, uf: estado.uf }));
    }
    if (minha !== buscaSeq) return;
    achadas.sort((a, b) => (b.uf === estado.uf) - (a.uf === estado.uf));   // as do estado que está na tela vêm primeiro
    buscaCidades = achadas.map(daLista);
    pintarBusca();
  }, 180);
}

function escolherNaBusca(i) {
  const item = buscaItens[i];
  if (!item) return;
  $("busca").close();
  item.abrir();
}

function abrirBusca() {
  if (document.querySelector("dialog[open]")) return;
  $("busca-campo").value = "";
  buscaAtivo = 0;
  buscaCidades = [];
  buscaSeq++;
  pintarBusca();
  $("busca").showModal();
  $("busca-campo").focus();
}

$("abrir-busca").addEventListener("click", abrirBusca);
$("busca").addEventListener("click", (e) => { if (e.target === $("busca")) $("busca").close(); });   // clicou fora
$("busca-campo").addEventListener("input", () => { buscaAtivo = 0; buscarCidadesNoServidor($("busca-campo").value); pintarBusca(); });
$("busca-campo").addEventListener("keydown", (e) => {
  const n = buscaItens.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (n) { buscaAtivo = (buscaAtivo + (e.key === "ArrowDown" ? 1 : n - 1)) % n; pintarBusca(); }
  } else if (e.key === "Enter") {
    e.preventDefault();
    escolherNaBusca(buscaAtivo);
  }
});
document.addEventListener("keydown", (e) => {
  const alvo = e.target;
  const digitando = alvo instanceof HTMLElement && (alvo.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(alvo.tagName));
  const atalhoK = (e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey);
  if (atalhoK || (e.key === "/" && !digitando && !e.metaKey && !e.ctrlKey && !e.altKey)) {
    e.preventDefault();
    abrirBusca();
  }
});
