/* Mapa do Brasil, painel por região e disputas mais apertadas. */
const INTERVALO_MAPA = 10000;   // o TSE guarda cada estado por 20 s no servidor: a página só relê o que já está pronto
const DISPUTAS_INICIAIS = 10;
let mapaSvg = null;   // o desenho dos estados é montado uma vez por seleção e só repintado a cada rodada
let mapaCongelado = false;      // true enquanto o replay (mapa-ao-vivo.js) mostra uma foto antiga: a rodada não repinta
const aoConstruirMapa = [];      // (mapaSvg) depois que o desenho dos estados foi montado; mapa-brasil-rotulos.js põe rótulos e etiquetas aqui
const MAPA_VISTA = [1120, MAPA_TAMANHO[1]];   // o desenho dos estados tem 1000 de largura; o resto é a coluna das etiquetas dos estados pequenos
const aoPintarUfs = [];         // (dados) depois que os estados foram repintados; mapa-ao-vivo.js solta as ondas aqui
let mapaDados = null, regioesDados = null, mapaMarca = "", mapaSeq = 0, mapaTimer = 0, disputasTodas = false, disputasDados = null;
const temMapa = () => estado.cargo === "presidente" || estado.cargo === "governador";
const temRegioes = () => estado.cargo === "presidente";
const temDisputas = () => estado.cargo === "governador" || estado.cargo === "senador";
const marcaMapa = () => [estado.cargo, estado.turno, estado.ambiente].join("|");
const pp = (n) => n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " p.p.";
const nomeDoCandidato = (c) => `${c.nome} (${c.partido})`;

/* Cor do estado: o partido do líder; quanto maior a margem, mais forte (até 20 pontos). Sem líder, cinza. */
function pinturaDe(partido, margem) {
  if (!partido) return "fill:var(--muted);fill-opacity:0.3";
  const forca = 0.35 + 0.65 * Math.min(margem, 20) / 20;
  return `fill:${corDoPartido(partido)};fill-opacity:${forca.toFixed(2)}`;
}
function pintura(r) {
  return r && r.situacao === "lider" ? pinturaDe(r.lider.partido, r.margem) : pinturaDe("", 0);
}

/* Texto curto do estado, usado na lista e no rótulo para leitor de tela. */
function resumoDaUf(r) {
  if (!r || r.situacao === "sem_dados") return "Sem dados do TSE agora";
  if (r.situacao === "sem_segundo_turno") return r.primeiro_turno ? `Sem 2º turno. Definido no 1º: ${nomeDoCandidato(r.primeiro_turno)}` : "Sem 2º turno";
  if (r.situacao === "zerado") return "Apuração ainda não começou";
  if (r.situacao === "empate") return `Empate no topo: ${r.empatados.map(nomeDoCandidato).join(" e ")}`;
  const marca = r.lider.eleito ? " · eleito" : r.lider.segundo_turno ? " · vai ao 2º turno" : "";
  return `${nomeDoCandidato(r.lider)} lidera com ${pct(r.lider.percentual)}${marca}, ${pp(r.margem)} à frente`;
}

function dicaDaUf(uf, r) {
  if (r && r.situacao === "lider") {
    return cartaoDoLugar({ selo: uf.toUpperCase(), titulo: UFS[uf], subtitulo: `${pct(r.secoes.percentual)} das seções`, candidatos: [r.lider, r.segundo].filter(Boolean), cor: corDoPartido(r.lider.partido) });
  }
  const nos = [criar("strong", {}, `${UFS[uf]} (${uf.toUpperCase()})`), criar("span", {}, resumoDaUf(r))];
  if (r && r.situacao === "lider") {
    nos.push(criar("span", {}, ` · ${inteiro(r.margem_votos)} votos de vantagem · ${pct(r.secoes.percentual)} das seções`));
  } else if (r && r.secoes) {
    nos.push(criar("span", {}, ` · ${pct(r.secoes.percentual)} das seções`));
  }
  return nos;
}

function selecionarUfDoMapa(uf) {
  if (uf !== "br" && temMapa()) { irParaTela("centro"); entrarNaUf(uf); return; }   // palco.js: zoom animado até o estado (em celular, na tela do mapa)
  if (uf === estado.uf) return;
  trocou("uf", uf);   // o duelo, no alto de todas as telas, já mostra o estado escolhido
}

function destacarUf() {
  for (const caminho of $("mapa-svg").querySelectorAll("path")) {
    const atual = caminho.dataset.uf === estado.uf;
    caminho.classList.toggle("atual", atual);
    if (atual) caminho.parentNode.append(caminho);   // o contorno marcado fica por cima dos vizinhos
  }
  $("mapa-brasil").hidden = estado.cargo !== "presidente" || estado.uf === "br";
  for (const botao of $("mapa-tabela").querySelectorAll("button")) {
    botao.setAttribute("aria-current", String(botao.dataset.uf === estado.uf));
  }
}

function legendaDoMapa(d) {
  const contagem = new Map();
  let neutros = 0;
  for (const r of Object.values(d.ufs)) {
    if (r.situacao === "lider") contagem.set(r.lider.partido, (contagem.get(r.lider.partido) || 0) + 1);
    else neutros++;
  }
  const itens = [...contagem].sort((a, b) => b[1] - a[1]).map(([partido, n]) => criar("li", {},
    criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), `${partido}: ${n} ${n > 1 ? "estados" : "estado"}`));
  if (neutros) itens.push(criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--muted);opacity:0.35" }), `Sem líder definido: ${neutros}`));
  return itens;
}

/* Monta o desenho uma vez. As rodadas seguintes só trocam a cor de cada estado (com transição), então o mapa
   não pisca e quem está com zoom num estado continua onde estava. */
function construirMapa() {
  const [largura, altura] = MAPA_VISTA;
  const svg = criarSvg("svg", { viewBox: `0 0 ${largura} ${altura}`, role: "img", "aria-label": "Mapa do Brasil com o líder de cada estado. A lista dos estados está logo abaixo." });
  const caminhos = criarSvg("g"), rotulos = criarSvg("g"), ondas = criarSvg("g", { class: "ondas", "aria-hidden": "true" }), porUf = new Map();
  for (const [uf, forma] of Object.entries(MAPA_UFS)) {
    const caminho = criarSvg("path", { d: forma.d, "data-uf": uf });
    caminho.addEventListener("pointermove", (e) => mostrarDicaEm(dicaDaUf(uf, mapaDados && mapaDados.ufs[uf]), e.clientX, e.clientY));
    caminho.addEventListener("pointerleave", () => { dica.hidden = true; });
    caminho.addEventListener("click", () => { dica.hidden = true; selecionarUfDoMapa(uf); });
    caminhos.append(caminho);
    porUf.set(uf, caminho);
  }
  svg.append(caminhos, rotulos, ondas);   // os rótulos e as ondas ficam por cima de qualquer contorno
  $("mapa-svg").style.setProperty("--proporcao", String(largura / altura));   // o CSS dimensiona o mapa pela proporção, para caber na tela sem barras
  $("mapa-svg").replaceChildren(svg);
  mapaSvg = { svg, porUf, ondas, rotulos };
  avisar(aoConstruirMapa, mapaSvg);
}

/* Repinta cada estado. O estado que mudou de cor ou de força pisca de leve: dá para ver a apuração andando. */
function pintarUfs(d) {
  if (mapaCongelado) return;
  for (const [uf, caminho] of mapaSvg.porUf) {
    const estilo = pintura(d.ufs[uf]);
    const antes = caminho.getAttribute("style");
    if (antes === estilo) continue;
    caminho.setAttribute("style", estilo);
    if (antes !== null) {
      caminho.classList.remove("mudou");
      void caminho.getBoundingClientRect();   // reinicia a animação se ele mudar duas vezes seguidas
      caminho.classList.add("mudou");
    }
  }
  avisar(aoPintarUfs, d);
}

function pintarMapa(d) {
  mapaDados = d;
  $("mapa").hidden = false;
  const comLider = Object.values(d.ufs).filter((r) => r.situacao === "lider").length;
  $("mapa-info").textContent = `${comLider} de 27 com líder`;
  $("mapa-nota").hidden = !d.aviso;
  $("mapa-nota").textContent = d.aviso || "";
  $("mapa-corpo").hidden = false;
  $("mapa-explica").textContent = `A cor é a do partido de quem lidera cada estado${estado.cargo === "presidente" ? " para presidente" : " para governador"}; quanto mais forte, maior a vantagem (até 20 pontos). Clique num estado para ver o placar dele.`;
  $("mapa-legenda").replaceChildren(...legendaDoMapa(d));

  if (!mapaSvg) construirMapa();
  pintarUfs(d);

  const nomes = Object.keys(UFS).sort((a, b) => UFS[a].localeCompare(UFS[b], "pt-BR"));
  const linhas = nomes.map((uf) => {
    const r = d.ufs[uf];
    const lider = r && r.situacao === "lider";
    return criar("tr", {},
      criar("th", { scope: "row" }, criar("button", { class: "botao-link", type: "button", "data-uf": uf, "aria-label": `Ver o placar de ${UFS[uf]}` }, UFS[uf])),
      criar("td", {}, lider ? nomeDoCandidato(r.lider) : resumoDaUf(r)),
      criar("td", {}, lider ? pct(r.lider.percentual) : "—"),
      criar("td", {}, lider ? pp(r.margem) : "—"),
      criar("td", {}, r && r.secoes ? pct(r.secoes.percentual) : "—"));
  });
  $("mapa-tabela").replaceChildren(
    criar("thead", {}, criar("tr", {}, ...["Estado", "Líder", "Percentual", "Vantagem", "Apurado"].map((t) => criar("th", {}, t)))),
    criar("tbody", {}, ...linhas));
  for (const botao of $("mapa-tabela").querySelectorAll("button")) botao.addEventListener("click", () => selecionarUfDoMapa(botao.dataset.uf));
  destacarUf();
}

function pintarRegioes(d) {
  regioesDados = d;
  $("regioes").hidden = false;
  $("regioes-info").textContent = "soma dos estados de cada região";
  $("regioes-grade").replaceChildren(...d.regioes.map((r) => {
    const andamento = r.secoes.total ? `${pct(r.secoes.percentual)} das seções` : "sem dados";
    const ranking = r.lider
      ? r.candidatos.map((c) => criar("li", {},
        criar("span", {}, nomeDoCandidato(c)), criar("b", { class: "num" }, pct(c.percentual)),
        criar("div", { class: "rq-trilho" }, criar("div", { class: "rq-barra", style: `width:${c.percentual / r.lider.percentual * 100}%;background:${corDoPartido(c.partido)}` }))))
      : [criar("li", { class: "meta" }, "Apuração ainda não começou nesta região.")];
    return criar("article", { class: "regiao" },
      criar("h3", {}, r.regiao), criar("p", { class: "meta" }, `${andamento} · ${inteiro(r.votos)} votos`), criar("ol", {}, ...ranking));
  }));
}

const SITUACAO_DA_DISPUTA = { eleito: "Eleito", segundo_turno: "Vai ao 2º turno", apurando: "Em apuração" };

function pintarDisputas(d) {
  disputasDados = d;
  $("disputas").hidden = false;
  const lista = disputasTodas ? d.disputas : d.disputas.slice(0, DISPUTAS_INICIAIS);
  $("disputas-info").textContent = d.disputas.length ? `${d.disputas.length} ${d.disputas.length > 1 ? "estados" : "estado"} em disputa` : "";
  $("disputas-nota").textContent = !d.disputas.length ? "As disputas aparecem quando a apuração começar."
    : estado.cargo === "senador" ? "Menor diferença de votos entre o 2º colocado (última vaga) e o 3º, em cada estado."
    : "Menor diferença de votos entre o 1º e o 2º colocados, em cada estado.";
  $("disputas-lista").replaceChildren(...lista.map((x) => {
    const [dentro, fora] = x.entre;
    return criar("li", { class: "disputa" },
      criar("button", { class: "botao-link uf", type: "button", "data-uf": x.uf, "aria-label": `Ver o placar de ${UFS[x.uf]}` }, x.uf.toUpperCase()),
      criar("div", { class: "quem" },
        criar("div", { class: "nome" }, `${nomeDoCandidato(dentro)} ${pct(dentro.percentual)} · ${nomeDoCandidato(fora)} ${pct(fora.percentual)}`),
        criar("span", { class: "meta" }, `Diferença de ${inteiro(x.margem_votos)} votos (${pp(x.margem)}) · ${pct(x.secoes.percentual)} das seções`)),
      criar("span", { class: "selo" + (x.situacao === "apurando" ? "" : " atencao") }, SITUACAO_DA_DISPUTA[x.situacao] || x.situacao));
  }));
  for (const botao of $("disputas-lista").querySelectorAll("button")) botao.addEventListener("click", () => selecionarUfDoMapa(botao.dataset.uf));
  $("disputas-mais").hidden = disputasTodas || d.disputas.length <= DISPUTAS_INICIAIS;
}

async function tentar(rota, q) {
  try {
    const resposta = await fetch(`${rota}?${q}`, { cache: "no-store" });
    return { ok: resposta.ok, corpo: await resposta.json() };
  } catch {
    return { ok: false, corpo: { erro: "Sem conexão com o servidor." } };
  }
}

async function carregarMapa() {
  clearTimeout(mapaTimer);
  const minha = ++mapaSeq;
  const q = new URLSearchParams({ cargo: estado.cargo, turno: estado.turno, ambiente: estado.ambiente });
  const [mapa, regioes, disputas] = await Promise.all([
    temMapa() ? tentar("/api/mapa", q) : null,
    temRegioes() ? tentar("/api/regioes", q) : null,
    temDisputas() ? tentar("/api/disputas", q) : null,
  ]);
  if (minha !== mapaSeq) return;
  // Falha de um bloco não apaga o que já está na tela: o servidor se recupera na próxima rodada.
  if (mapa) {
    if (mapa.ok) pintarMapa(mapa.corpo);
    else if ($("mapa-corpo").hidden) { $("mapa").hidden = false; $("mapa-nota").hidden = false; $("mapa-nota").textContent = mapa.corpo.erro || "Mapa indisponível agora."; }
  }
  if (regioes && regioes.ok) pintarRegioes(regioes.corpo);
  if (disputas) {
    if (disputas.ok) pintarDisputas(disputas.corpo);
    else if (!disputasDados) { $("disputas").hidden = false; $("disputas-nota").textContent = disputas.corpo.erro || "Disputas indisponíveis agora."; }
  }
  if (!document.hidden) mapaTimer = setTimeout(carregarMapa, INTERVALO_MAPA);
}

aoMudarSelecao.push(() => {
  const marca = marcaMapa();
  if (!temMapa() && !temDisputas()) {
    clearTimeout(mapaTimer);
    mapaSeq++;
    mapaMarca = "";
    for (const id of ["mapa", "regioes", "disputas"]) $(id).hidden = true;
    return;
  }
  if (marca === mapaMarca) { destacarUf(); return; }   // só mudou o estado ou a cidade: o mapa é o mesmo
  mapaMarca = marca;
  disputasTodas = false;
  disputasDados = mapaDados = regioesDados = mapaSvg = null;
  $("mapa").hidden = !temMapa();
  $("mapa-corpo").hidden = true;
  $("mapa-nota").hidden = false;
  $("mapa-nota").textContent = "Carregando o mapa…";
  $("regioes").hidden = true;
  $("disputas").hidden = !temDisputas();
  $("disputas-nota").textContent = "Carregando as disputas…";
  $("disputas-lista").replaceChildren();
  $("disputas-mais").hidden = true;
  carregarMapa();
});
$("mapa-brasil").addEventListener("click", () => selecionarUfDoMapa("br"));
$("disputas-mais").addEventListener("click", () => { disputasTodas = true; if (disputasDados) pintarDisputas(disputasDados); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(mapaTimer);
  else if (mapaMarca) carregarMapa();
});
