/* Hemiciclo (Câmara e Senado) e mais votados. Câmara e mais votados vêm dos arquivos de todas as UFs, buscados em
   segundo plano pelo servidor (poucas consultas por segundo no total), então enchem aos poucos. */
const INTERVALO_HEMICICLO = 20000;
let hemiMarca = "", hemiSeq = 0, hemiTimer = 0;
const temSenado = () => estado.cargo === "senador";
const temCamara = () => estado.cargo === "deputado-federal";
const temMaisVotados = () => ["deputado-federal", "deputado-estadual", "deputado-distrital"].includes(estado.cargo);

/* Posições das cadeiras em fileiras concêntricas, da esquerda para a direita (x de -1 a 1, y de 0 para cima). */
function posicoesDoHemiciclo(n) {
  const fileiras = Math.max(2, Math.round(Math.sqrt(n / 2.6)));
  const interno = 0.38;
  const raios = Array.from({ length: fileiras }, (_, i) => interno + (1 - interno) * i / (fileiras - 1));
  const soma = raios.reduce((a, b) => a + b, 0);
  const por = raios.map((r) => Math.max(1, Math.round(n * r / soma)));
  let falta = n - por.reduce((a, b) => a + b, 0);
  for (let i = por.length - 1; falta !== 0; i = (i - 1 + por.length) % por.length) {
    const passo = Math.sign(falta);
    if (por[i] + passo >= 1) { por[i] += passo; falta -= passo; }
  }
  const posicoes = [];
  raios.forEach((raio, i) => {
    for (let j = 0; j < por[i]; j++) {
      const angulo = por[i] === 1 ? Math.PI / 2 : Math.PI * (1 - j / (por[i] - 1));
      posicoes.push({ x: raio * Math.cos(angulo), y: raio * Math.sin(angulo), angulo, raio });
    }
  });
  posicoes.sort((a, b) => b.angulo - a.angulo || a.raio - b.raio);
  const entreFileiras = (1 - interno) / (fileiras - 1);
  const entreCadeiras = Math.PI * interno / Math.max(1, por[0] - 1);
  return { posicoes, raio: 0.42 * Math.min(entreFileiras, entreCadeiras) };
}

/* Cada cadeira: {estado: "cheia" | "provisoria" | "indefinida" | "fora", partido, titulo}. */
function desenharHemiciclo(cadeiras, rotuloCentral, subrotulo, descricao) {
  const { posicoes, raio } = posicoesDoHemiciclo(cadeiras.length);
  const svg = criarSvg("svg", { viewBox: "-1.06 -1.06 2.12 1.18", role: "img", "aria-label": `Hemiciclo: ${descricao}. As cadeiras por partido estão na tabela abaixo.` });
  cadeiras.forEach((cadeira, i) => {
    const cor = cadeira.partido ? corDoPartido(cadeira.partido) : "var(--baseline)";
    const estilo = {
      cheia: `fill:${cor};stroke:${cor}`,
      provisoria: `fill:${cor};fill-opacity:0.4;stroke:${cor}`,
      indefinida: "fill:none;stroke:var(--baseline)",
      fora: "fill:none;stroke:var(--baseline);stroke-dasharray:0.02 0.02",
    }[cadeira.estado];
    const bolinha = criarSvg("circle", { cx: posicoes[i].x.toFixed(4), cy: (-posicoes[i].y).toFixed(4), r: raio.toFixed(4), style: estilo });
    bolinha.addEventListener("pointermove", (e) => mostrarDicaEm([criar("strong", {}, cadeira.titulo)], e.clientX, e.clientY));
    bolinha.addEventListener("pointerleave", () => { dica.hidden = true; });
    svg.append(bolinha);
  });
  svg.append(criarSvg("text", { class: "grande", x: 0, y: -0.06 }, rotuloCentral), criarSvg("text", { class: "pequeno", x: 0, y: 0.04 }, subrotulo));
  return svg;
}

function tabelaDoHemiciclo(cabecalho, linhas) {
  return [criar("thead", {}, criar("tr", {}, ...cabecalho.map((t) => criar("th", {}, t)))),
    criar("tbody", {}, ...linhas.map((l) => criar("tr", {}, ...l.map((c) => criar("td", {}, String(c))))))];
}

/* Partidos com cor própria ganham um item cada; os demais (cinza) vão juntos num item só, com os números por extenso. */
function legendaDosPartidos(partidos) {
  const comCor = partidos.filter(([partido]) => corDoPartido(partido) !== "var(--p-outros)");
  const outros = partidos.filter(([partido]) => corDoPartido(partido) === "var(--p-outros)");
  const itens = comCor.map(([partido, texto]) => criar("li", {}, criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), texto));
  if (outros.length) itens.push(criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--p-outros)" }), `Outros (cinza): ${outros.map(([, texto]) => texto.replace(": ", " ")).join(" · ")}`));
  return itens;
}

function pintarCamara(d) {
  $("hemiciclo").hidden = false;
  $("hemiciclo-h").textContent = "Hemiciclo da Câmara dos Deputados";
  const ordem = Object.fromEntries(d.blocos.map((b, i) => [b.bloco, i]));
  const partidos = [...d.partidos].sort((a, b) => (ordem[a.bloco] - ordem[b.bloco]) || (b.cadeiras - a.cadeiras));
  const cadeiras = partidos.flatMap((p) => Array.from({ length: p.cadeiras }, () => ({ estado: "cheia", partido: p.partido, titulo: `${p.partido} · ${p.cadeiras} cadeiras · bloco ${p.bloco}` })));
  while (cadeiras.length < d.total) cadeiras.push({ estado: "indefinida", partido: null, titulo: "Cadeira ainda sem eleito" });
  const carregando = d.ufs_com_dados < d.ufs_total;
  $("hemiciclo-info").textContent = `${inteiro(d.eleitos)} de ${inteiro(d.total)} eleitos`;
  $("hemiciclo-nota").hidden = !carregando && d.eleitos > 0;
  $("hemiciclo-nota").textContent = d.ufs_com_dados === 0 ? "Buscando os dados dos estados no TSE. As cadeiras aparecem aos poucos."
    : carregando ? `Dados de ${d.ufs_com_dados} de ${d.ufs_total} estados até agora; o hemiciclo enche conforme o servidor busca o resto.`
    : "O TSE ainda não marcou eleitos. As cadeiras aparecem quando ele marcar.";
  $("hemiciclo-corpo").hidden = false;
  $("hemiciclo-svg").replaceChildren(desenharHemiciclo(cadeiras, inteiro(d.eleitos), `de ${inteiro(d.total)} eleitos`, `${inteiro(d.eleitos)} de ${inteiro(d.total)} deputados federais eleitos`));
  $("hemiciclo-legenda").replaceChildren(...legendaDosPartidos(partidos.map((p) => [p.partido, `${p.partido}: ${p.cadeiras}`])));
  $("hemiciclo-tabela").replaceChildren(...tabelaDoHemiciclo(["Partido", "Bloco (federação)", "Cadeiras"], partidos.map((p) => [p.partido, p.bloco, p.cadeiras])));
}

function pintarSenado(d) {
  $("hemiciclo").hidden = false;
  $("hemiciclo-h").textContent = "Hemiciclo do Senado";
  const ordemPartido = Object.fromEntries(d.partidos.map((p, i) => [p.partido, i]));
  const definidas = d.cadeiras.filter((c) => c.partido).sort((a, b) => (ordemPartido[a.partido] - ordemPartido[b.partido]) || (a.situacao === "eleito" ? -1 : 1) - (b.situacao === "eleito" ? -1 : 1));
  const cadeiras = [
    ...definidas.map((c) => ({ estado: c.situacao === "eleito" ? "cheia" : "provisoria", partido: c.partido, titulo: `${c.nome} (${c.partido}) · ${c.uf.toUpperCase()} · ${c.situacao === "eleito" ? "eleito" : "liderando"}` })),
    ...d.cadeiras.filter((c) => !c.partido).map((c) => ({ estado: "indefinida", partido: null, titulo: `${UFS[c.uf]}: vaga ainda sem líder` })),
    ...Array.from({ length: d.fora_da_disputa }, () => ({ estado: "fora", partido: null, titulo: "Cadeira que não está em disputa em 2026" })),
  ];
  const eleitos = d.cadeiras.filter((c) => c.situacao === "eleito").length;
  $("hemiciclo-info").textContent = `${eleitos} de ${d.em_disputa} vagas com eleito`;
  $("hemiciclo-nota").hidden = false;
  $("hemiciclo-nota").textContent = `Em 2026 disputam-se ${d.em_disputa} das ${d.total} cadeiras (2 por estado). Cor cheia: eleito. Cor clara: liderando, ainda sem eleito marcado pelo TSE. Tracejadas: as ${d.fora_da_disputa} cadeiras que não estão em disputa.`;
  $("hemiciclo-corpo").hidden = false;
  $("hemiciclo-svg").replaceChildren(desenharHemiciclo(cadeiras, String(eleitos), `de ${d.em_disputa} vagas`, `${eleitos} de ${d.em_disputa} vagas em disputa já têm senador eleito`));
  $("hemiciclo-legenda").replaceChildren(...legendaDosPartidos(d.partidos.map((p) => [p.partido, `${p.partido}: ${p.eleitos + p.liderando}`])));
  $("hemiciclo-tabela").replaceChildren(...tabelaDoHemiciclo(["Partido", "Eleitos", "Liderando"], d.partidos.map((p) => [p.partido, p.eleitos, p.liderando])));
}

function pintarMaisVotados(d) {
  $("maisvotados").hidden = false;
  const nome = { "deputado-federal": "deputados federais", "deputado-estadual": "deputados estaduais e distritais", "deputado-distrital": "deputados estaduais e distritais" }[estado.cargo];
  $("maisvotados-h").textContent = `Mais votados do Brasil · ${nome}`;
  const carregando = d.ufs_com_dados < d.ufs_total;
  $("maisvotados-info").textContent = d.candidatos.length ? `${d.ufs_com_dados} de ${d.ufs_total} estados` : "";
  $("maisvotados-nota").hidden = !carregando && d.candidatos.length > 0;
  $("maisvotados-nota").textContent = d.ufs_com_dados === 0 ? "Buscando os dados dos estados no TSE. O ranking aparece aos poucos."
    : carregando ? `Ranking parcial: dados de ${d.ufs_com_dados} de ${d.ufs_total} estados até agora.` : "O TSE ainda não publicou votos.";
  $("maisvotados-lista").replaceChildren(...d.candidatos.map((c) => criar("li", {},
    criar("span", { class: "pos" }, c.posicao),
    criar("div", { class: "com-foto" }, fotoDoCandidato(c), criar("div", {}, criar("div", { class: "nome" }, c.nome),
      criar("div", { class: "meta" }, `${c.partido} · ${UFS[c.uf]}`, ...(c.eleito ? [" · ", criar("span", { class: "eleito" }, "✓ eleito")] : [])))),
    criar("span", { class: "num" }, `${inteiro(c.votos)} votos`))));
}

async function carregarHemiciclo() {
  clearTimeout(hemiTimer);
  const minha = ++hemiSeq;
  const q = new URLSearchParams({ ambiente: estado.ambiente });
  const qMais = new URLSearchParams({ ambiente: estado.ambiente, cargo: estado.cargo });
  const [casa, mais] = await Promise.all([
    temSenado() ? tentar("/api/senado", q) : temCamara() ? tentar("/api/camara", q) : null,
    temMaisVotados() ? tentar("/api/maisvotados", qMais) : null,
  ]);
  if (minha !== hemiSeq) return;
  let completo = true;
  if (casa) {
    if (casa.ok) { (temSenado() ? pintarSenado : pintarCamara)(casa.corpo); completo = temSenado() || casa.corpo.ufs_com_dados >= casa.corpo.ufs_total; }
    else { $("hemiciclo").hidden = false; $("hemiciclo-corpo").hidden = true; $("hemiciclo-nota").hidden = false; $("hemiciclo-nota").textContent = casa.corpo.erro || "Hemiciclo indisponível agora."; }
  }
  if (mais) {
    if (mais.ok) { pintarMaisVotados(mais.corpo); completo = completo && mais.corpo.ufs_com_dados >= mais.corpo.ufs_total; }
    else { $("maisvotados").hidden = false; $("maisvotados-nota").hidden = false; $("maisvotados-nota").textContent = mais.corpo.erro || "Ranking indisponível agora."; $("maisvotados-lista").replaceChildren(); }
  }
  // Enquanto o servidor ainda busca os estados, volta logo; depois, no ritmo normal.
  if (!document.hidden) hemiTimer = setTimeout(carregarHemiciclo, completo ? INTERVALO_HEMICICLO * 3 : INTERVALO_HEMICICLO / 2);
}

aoMudarSelecao.push(() => {
  const marca = [estado.cargo, estado.ambiente].join("|");
  if (!temSenado() && !temCamara() && !temMaisVotados()) {
    clearTimeout(hemiTimer);
    hemiSeq++;
    hemiMarca = "";
    $("hemiciclo").hidden = $("maisvotados").hidden = true;
    return;
  }
  if (marca === hemiMarca) return;   // só mudou o estado ou a cidade: estes recursos são do país todo
  hemiMarca = marca;
  $("hemiciclo").hidden = !(temSenado() || temCamara());
  $("maisvotados").hidden = !temMaisVotados();
  $("hemiciclo-corpo").hidden = true;
  $("hemiciclo-nota").hidden = false;
  $("hemiciclo-nota").textContent = "Carregando o hemiciclo…";
  $("maisvotados-nota").hidden = false;
  $("maisvotados-nota").textContent = "Carregando o ranking…";
  $("maisvotados-lista").replaceChildren();
  carregarHemiciclo();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(hemiTimer);
  else if (hemiMarca) carregarHemiciclo();
});
