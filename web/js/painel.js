/* Filtros, cidades, placar principal, busca dos dados e tooltip. */
function ufsDoCargo(cargo) {
  const todas = Object.keys(UFS);
  if (cargo === "presidente") return ["br", ...todas];
  if (cargo === "deputado-distrital") return ["df"];
  if (cargo === "deputado-estadual") return todas.filter((uf) => uf !== "df");
  return todas;
}

function preencher(select, opcoes, valor) {
  select.replaceChildren(...opcoes.map(([v, texto]) => new Option(texto, v)));
  select.value = valor;
}

function sincronizarFiltros() {
  const ufs = ufsDoCargo(estado.cargo);
  if (!ufs.includes(estado.uf)) estado.uf = estado.cargo === "presidente" ? "br" : ufs.includes("sp") ? "sp" : ufs[0];
  preencher($("cargo"), Object.entries(CARGOS), estado.cargo);
  preencher($("uf"), ufs.map((uf) => [uf, uf === "br" ? "Brasil" : UFS[uf]]), estado.uf);
  const temSegundoTurno = estado.cargo === "presidente" || estado.cargo === "governador";
  if (!temSegundoTurno) estado.turno = "1";
  $("turno").options[1].disabled = !temSegundoTurno;
  $("turno").value = estado.turno;
  $("ambiente").value = estado.ambiente;
  $("rotulo-cidade").hidden = estado.uf === "br";
  atualizarEndereco();
}

const semAcento = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
const cidadeAtual = () => cidades.find((c) => c.codigo === estado.municipio) || null;

/* Lista as cidades da UF (o servidor guarda por 6 h). Falhou? Segue só com a UF inteira. */
async function carregarCidades() {
  const minha = ++sequenciaCidades;
  cidades = [];
  $("cidades").replaceChildren();
  if (estado.uf === "br") { estado.municipio = ""; $("cidade").value = ""; return; }
  try {
    const q = new URLSearchParams({ cargo: estado.cargo, uf: estado.uf, turno: estado.turno, ambiente: estado.ambiente });
    const resposta = await fetch("/api/municipios?" + q, { cache: "no-store" });
    const corpo = await resposta.json();
    if (minha !== sequenciaCidades) return;
    if (resposta.ok) cidades = corpo.municipios;
  } catch { /* sem lista, sem seletor: o placar da UF continua funcionando */ }
  if (minha !== sequenciaCidades) return;
  $("cidades").replaceChildren(...cidades.map((c) => new Option(c.nome)));
  if (estado.municipio && !cidadeAtual()) estado.municipio = "";
  $("cidade").value = cidadeAtual() ? cidadeAtual().nome : "";
  sincronizarFiltros();
  $("subtitulo").textContent = titulo();
}

/* Se a lista derrubou a cidade (não existe nesta UF/ambiente), refaz a consulta sem ela. */
async function atualizarCidades() {
  const antes = estado.municipio;
  await carregarCidades();
  if (estado.municipio !== antes) { ultimo = null; carregar(); avisar(aoMudarSelecao); }
}

function escolherCidade() {
  const texto = $("cidade").value;
  const alvo = semAcento(texto);
  const achada = alvo ? cidades.find((c) => semAcento(c.nome) === alvo) : null;
  if (!achada && alvo) return;  // ainda digitando: não consulta nada
  const codigo = achada ? achada.codigo : "";
  if (codigo === estado.municipio) return;
  estado.municipio = codigo;
  estado.top = TOP_INICIAL;
  ultimo = null;
  sincronizarFiltros();
  carregar();
  avisar(aoMudarSelecao);
}

function titulo() {
  const cidade = cidadeAtual();
  const lugar = estado.uf === "br" ? "Brasil" : cidade ? `${cidade.nome} (${estado.uf.toUpperCase()})` : UFS[estado.uf];
  return `${CARGOS[estado.cargo]} · ${lugar} · ${estado.turno}º turno`;
}

function mostrarSelos(d) {
  const selos = [];
  selos.push([d.final ? "Apuração final" : "Apuração parcial", ""]);
  if (d.ambiente === "simulado") selos.push(["Dados simulados do TSE (teste)", "atencao"]);
  $("selos").replaceChildren(...selos.map(([texto, classe]) => {
    const el = document.createElement("span");
    el.className = "selo " + classe;
    el.textContent = texto;
    return el;
  }));
}

function indicador(rotulo, valor, detalhe) {
  const el = document.createElement("div");
  el.className = "cartao indicador";
  for (const [classe, texto] of [["rotulo", rotulo], ["valor", valor], ["detalhe", detalhe]]) {
    const filho = document.createElement("div");
    filho.className = classe;
    filho.textContent = texto;
    el.append(filho);
  }
  return el;
}

function linha(c, lider, comDica = true) {
  const li = document.createElement("li");
  li.className = "linha";
  li.tabIndex = 0;
  const largura = lider > 0 ? (c.votos / lider) * 100 : 0;

  const pos = document.createElement("span");
  pos.className = "pos";
  pos.textContent = c.posicao;

  const quem = document.createElement("div");
  quem.className = "quem com-foto";
  const nome = document.createElement("div");
  nome.className = "nome";
  nome.textContent = c.nome;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.append(`Nº ${c.numero} · ${c.partido}`);
  if (c.situacao) {
    meta.append(" · ");
    const sit = document.createElement("span");
    if (c.eleito) sit.className = "eleito";
    sit.textContent = (c.eleito ? "✓ " : "") + c.situacao;
    meta.append(sit);
  }
  quem.append(fotoDoCandidato(c), criar("div", {}, nome, meta));

  const trilho = document.createElement("div");
  trilho.className = "trilho";
  trilho.setAttribute("aria-hidden", "true");
  const barra = document.createElement("div");
  barra.className = "barra";
  barra.style.width = largura + "%";
  trilho.append(barra);

  const votos = document.createElement("span");
  votos.className = "num votos";
  votos.textContent = inteiro(c.votos);
  const pc = document.createElement("span");
  pc.className = "num pct";
  pc.textContent = pct(c.percentual);

  li.append(pos, quem, trilho, votos, pc);
  if (comDica) ligarDica(li, c);
  return li;
}

function renderizar(d) {
  mostrarSelos(d);
  $("subtitulo").textContent = titulo();
  document.title = `${titulo()} · Contador de votos 2026`;

  $("heroi-valor").textContent = pct(d.secoes.percentual);
  $("medidor-barra").style.width = d.secoes.percentual + "%";
  $("medidor").setAttribute("aria-valuenow", d.secoes.percentual);
  $("heroi-detalhe").textContent = `${inteiro(d.secoes.apuradas)} de ${inteiro(d.secoes.total)} seções`;

  $("indicadores").replaceChildren(
    indicador("Total de votos", inteiro(d.votos.total), `${inteiro(d.eleitores.aptos)} eleitores aptos`),
    indicador("Comparecimento", inteiro(d.eleitores.comparecimento), pct(d.eleitores.pct_comparecimento)),
    indicador("Abstenção", inteiro(d.eleitores.abstencao), pct(d.eleitores.pct_abstencao)),
    indicador("Votos brancos", inteiro(d.votos.brancos), pct(d.votos.pct_brancos)),
    indicador("Votos nulos", inteiro(d.votos.nulos), pct(d.votos.pct_nulos)),
  );

  const lider = d.candidatos.length ? d.candidatos[0].votos : 0;
  $("ranking").replaceChildren(...d.candidatos.map((c) => linha(c, lider)));
  const parcial = d.candidatos.length < d.total_candidatos;
  $("lista-info").textContent = (d.votos.total === 0 ? "Apuração ainda não começou · " : "") +
    (parcial ? `mostrando ${d.candidatos.length} de ${inteiro(d.total_candidatos)}` : `${inteiro(d.total_candidatos)} candidatos`);
  $("mais").hidden = !parcial || estado.top >= TOP_MAXIMO;

  mostrarAviso(d.aviso || "");
  ultimo = d;
  recebidoEm = Date.now();
  atualizarTempo();
  avisar(aoRenderizar, d);
}

/* Indicador "ao vivo": idade do dado que a página mostra. Fora do ar, ele diz isso em vez de fingir. */
function mostrarAoVivo(idade) {
  const minutos = Math.floor(idade / 60);
  const [classe, texto] = semConexao ? ["offline", "Sem conexão com o servidor"]
    : ultimo.final ? ["", "Apuração encerrada"]
    : idade <= 45 ? ["vivo", `Ao vivo · atualizado há ${idade} s`]
    : ["atrasado", `Dado de ${minutos >= 1 ? minutos + " min" : idade + " s"} atrás`];
  const el = $("ao-vivo");
  el.hidden = false;
  el.className = "selo ao-vivo " + classe;
  if (el.textContent !== texto) el.textContent = texto;
}

function mostrarAviso(texto) {
  $("aviso").hidden = !texto;
  $("aviso").textContent = texto;
}

function atualizarTempo() {
  if (!ultimo) { $("ao-vivo").hidden = true; return; }
  const idade = ultimo.idade_s + Math.round((Date.now() - recebidoEm) / 1000);
  mostrarAoVivo(idade);
  const totalizacao = ultimo.ultima_totalizacao ? `Última totalização: ${ultimo.ultima_totalizacao} (Brasília)` : "Totalização ainda não iniciada";
  $("rodape-tempo").textContent = `${totalizacao} · TSE consultado há ${idade}s · esta página atualiza sozinha.`;
}

async function carregar() {
  clearTimeout(temporizador);
  const minha = ++sequencia;
  $("painel").classList.add("carregando");
  try {
    const q = new URLSearchParams({ cargo: estado.cargo, uf: estado.uf, turno: estado.turno, ambiente: estado.ambiente, top: estado.top });
    if (estado.municipio) q.set("municipio", estado.municipio);
    const resposta = await fetch("/api/resultado?" + q, { cache: "no-store" });
    const corpo = await resposta.json();
    if (minha !== sequencia) return;
    semConexao = false;
    if (resposta.ok) renderizar(corpo);
    else if (estado.turnoPadrao && estado.turno === "2" && estado.cargo !== "presidente") { trocou("turno", "1", { padrao: true }); return; }   // governador sem 2º turno nesta UF: mostra o 1º
    else falhar(corpo.erro);
  } catch {
    if (minha === sequencia) { semConexao = true; falhar("Sem conexão com o servidor. Mantendo o último placar."); atualizarTempo(); }
  } finally {
    if (minha === sequencia) {
      $("painel").classList.remove("carregando");
      if (!document.hidden || alertasLigados) temporizador = setTimeout(carregar, document.hidden ? ATUALIZAR_EM_SEGUNDO_PLANO : ATUALIZAR_A_CADA);
    }
  }
}

function falhar(mensagem) {
  mostrarAviso(mensagem);
  if (!ultimo) {
    $("subtitulo").textContent = titulo();
    $("selos").replaceChildren();
    $("heroi-valor").textContent = "—";
    $("medidor-barra").style.width = "0";
    $("heroi-detalhe").textContent = "";
    $("indicadores").replaceChildren();
    const vazio = document.createElement("li");
    vazio.className = "vazio";
    vazio.textContent = "Sem resultado para exibir.";
    $("ranking").replaceChildren(vazio);
    $("lista-info").textContent = "";
    $("mais").hidden = true;
  }
}

function trocou(campo, valor, { padrao = false } = {}) {
  const ufAntes = estado.uf;
  if (campo === "turno" && !padrao) estado.turnoPadrao = false;   // escolha da pessoa vale daqui para frente
  if (campo === "cargo" && estado.turnoPadrao) estado.turno = "2";   // trocar de cargo volta ao padrão (o 1º só entrou de reserva)
  estado[campo] = valor;
  estado.top = TOP_INICIAL;
  ultimo = null;
  sincronizarFiltros();
  // A cidade é de uma UF e de um ambiente: trocar qualquer um deles (inclusive via cargo) a descarta.
  if (campo === "ambiente" || estado.uf !== ufAntes) {
    estado.municipio = "";
    $("cidade").value = "";
    sincronizarFiltros();
  }
  carregar();
  atualizarCidades();
  avisar(aoMudarSelecao);
}

/* Tooltip: reforça a linha, nunca é a única forma de ler um valor. */
const dica = $("dica");
function mostrarDicaEm(nos, x, y) {
  dica.replaceChildren(...nos);
  dica.hidden = false;
  const caixa = dica.getBoundingClientRect();
  dica.style.left = Math.max(8, Math.min(x + 14, innerWidth - caixa.width - 8)) + "px";
  dica.style.top = Math.max(8, Math.min(y + 14, innerHeight - caixa.height - 8)) + "px";
}
function ligarDica(el, c) {
  const mostrar = (x, y) => mostrarDicaEm([
    criar("strong", {}, `${inteiro(c.votos)} votos · ${pct(c.percentual)}`),
    criar("span", {}, `${c.nome} · Nº ${c.numero} · ${c.partido}${c.situacao ? " · " + c.situacao : ""}`),
  ], x, y);
  const esconder = () => { dica.hidden = true; el.classList.remove("foco"); };
  el.addEventListener("pointermove", (e) => mostrar(e.clientX, e.clientY));
  el.addEventListener("pointerleave", esconder);
  el.addEventListener("focus", () => {
    el.classList.add("foco");
    const r = el.getBoundingClientRect();
    mostrar(r.left + r.width / 2, r.bottom - 8);
  });
  el.addEventListener("blur", esconder);
}

$("cargo").addEventListener("change", (e) => trocou("cargo", e.target.value));
$("uf").addEventListener("change", (e) => trocou("uf", e.target.value));
$("turno").addEventListener("change", (e) => trocou("turno", e.target.value));
$("ambiente").addEventListener("change", (e) => trocou("ambiente", e.target.value));
$("cidade").addEventListener("input", escolherCidade);
$("cidade").addEventListener("change", escolherCidade);
$("mais").addEventListener("click", () => {
  estado.top = Math.min(estado.top + TOP_PASSO, TOP_MAXIMO);
  carregar();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { if (!alertasLigados) clearTimeout(temporizador); }   // com alertas, segue no ritmo lento
  else carregar();
});
setInterval(atualizarTempo, 1000);
