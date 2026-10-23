/* Comparar: à esquerda o que está na tela; à direita outra seleção (cargo, estado, cidade e turno). */
const cmp = { cargo: "presidente", uf: "sp", municipio: "", turno: "1" };
let cmpSeq = 0, cmpTimer = 0, cmpCidades = [], cmpSeqCidades = 0;

function tituloDe(selecao, cidade) {
  const lugar = selecao.uf === "br" ? "Brasil" : cidade ? `${cidade} (${selecao.uf.toUpperCase()})` : UFS[selecao.uf];
  return `${CARGOS[selecao.cargo]} · ${lugar} · ${selecao.turno}º turno`;
}

function colunaDeComparacao(d, titulo) {
  const lider = d.candidatos.length ? d.candidatos[0].votos : 0;
  const [primeiro, segundo] = d.candidatos;
  return [
    criar("h3", {}, titulo),
    criar("p", { class: "meta" }, `${pct(d.secoes.percentual)} das seções · ${d.final ? "apuração final" : "apuração parcial"}`),
    criar("ol", { class: "ranking" }, ...d.candidatos.slice(0, 5).map((c) => linha(c, lider, false))),
    criar("p", { class: "meta" }, `Comparecimento ${pct(d.eleitores.pct_comparecimento)} · brancos ${pct(d.votos.pct_brancos)} · nulos ${pct(d.votos.pct_nulos)}`),
    criar("p", { class: "meta" }, primeiro && segundo && d.votos.total ? `Diferença entre o 1º e o 2º: ${pp(primeiro.percentual - segundo.percentual)} (${inteiro(primeiro.votos - segundo.votos)} votos)` : "Apuração ainda não começou."),
  ];
}

function pintarLadoA() {
  if (ultimo) $("cmp-a").replaceChildren(...colunaDeComparacao(ultimo, titulo()));
  else $("cmp-a").replaceChildren(criar("p", { class: "meta" }, "Sem resultado na tela."));
}

async function carregarLadoB() {
  clearTimeout(cmpTimer);
  const minha = ++cmpSeq;
  const q = new URLSearchParams({ cargo: cmp.cargo, uf: cmp.uf, turno: cmp.turno, ambiente: estado.ambiente, top: 5 });
  if (cmp.municipio) q.set("municipio", cmp.municipio);
  const caixa = $("cmp-b");
  caixa.classList.add("carregando");
  try {
    const resposta = await fetch("/api/resultado?" + q, { cache: "no-store" });
    const corpo = await resposta.json();
    if (minha !== cmpSeq) return;
    const cidade = cmpCidades.find((c) => c.codigo === cmp.municipio);
    caixa.replaceChildren(...(resposta.ok
      ? colunaDeComparacao(corpo, tituloDe(cmp, cidade && cidade.nome))
      : [criar("h3", {}, tituloDe(cmp)), criar("p", { class: "aviso" }, corpo.erro || "Sem resultado para esta seleção.")]));
  } catch {
    if (minha === cmpSeq) caixa.replaceChildren(criar("p", { class: "aviso" }, "Sem conexão com o servidor."));
  } finally {
    if (minha === cmpSeq) {
      caixa.classList.remove("carregando");
      if ($("comparar").open) cmpTimer = setTimeout(carregarLadoB, 15000);
    }
  }
}

function sincronizarLadoB() {
  const ufs = ufsDoCargo(cmp.cargo);
  if (!ufs.includes(cmp.uf)) cmp.uf = cmp.cargo === "presidente" ? "br" : ufs.includes("sp") ? "sp" : ufs[0];
  preencher($("cmp-cargo"), Object.entries(CARGOS), cmp.cargo);
  preencher($("cmp-uf"), ufs.map((uf) => [uf, uf === "br" ? "Brasil" : UFS[uf]]), cmp.uf);
  const temSegundoTurno = cmp.cargo === "presidente" || cmp.cargo === "governador";
  if (!temSegundoTurno) cmp.turno = "1";
  $("cmp-turno").options[1].disabled = !temSegundoTurno;
  $("cmp-turno").value = cmp.turno;
  $("cmp-rotulo-cidade").hidden = cmp.uf === "br";
  if (comparacaoAberta) atualizarEndereco();
}

async function carregarCidadesDoLadoB() {
  const minha = ++cmpSeqCidades;
  cmpCidades = [];
  $("cmp-cidades").replaceChildren();
  if (cmp.uf === "br") { cmp.municipio = ""; $("cmp-cidade").value = ""; return; }
  try {
    const q = new URLSearchParams({ cargo: cmp.cargo, uf: cmp.uf, turno: cmp.turno, ambiente: estado.ambiente });
    const resposta = await fetch("/api/municipios?" + q, { cache: "no-store" });
    const corpo = await resposta.json();
    if (minha !== cmpSeqCidades) return;
    if (resposta.ok) cmpCidades = corpo.municipios;
  } catch { /* sem lista, compara o estado inteiro */ }
  if (minha !== cmpSeqCidades) return;
  $("cmp-cidades").replaceChildren(...cmpCidades.map((c) => new Option(c.nome)));
  const daUrl = cmpCidades.find((c) => c.codigo === cmp.municipio);   // veio no endereço: mostra o nome dela no campo
  if (daUrl) $("cmp-cidade").value = daUrl.nome;
}

function mudouLadoB(campo, valor) {
  cmp[campo] = valor;
  cmp.municipio = "";   // a lista de cidades depende de cargo, estado e turno
  $("cmp-cidade").value = "";
  sincronizarLadoB();
  carregarLadoB();
  carregarCidadesDoLadoB();
}

function escolherCidadeDoLadoB() {
  const alvo = semAcento($("cmp-cidade").value);
  const achada = alvo ? cmpCidades.find((c) => semAcento(c.nome) === alvo) : null;
  if (!achada && alvo) return;   // ainda digitando
  const codigo = achada ? achada.codigo : "";
  if (codigo === cmp.municipio) return;
  cmp.municipio = codigo;
  atualizarEndereco();
  carregarLadoB();
}

/* `inicial` vem do endereço (?comparar=...): abre já com aquela seleção à direita. */
function abrirComparar(inicial = null) {
  if (inicial) Object.assign(cmp, inicial);
  else {
    Object.assign(cmp, { cargo: estado.cargo, turno: estado.turno, municipio: "" });
    cmp.uf = estado.uf === "br" ? "sp" : estado.cargo === "presidente" ? "br" : estado.uf === "sp" ? "rj" : "sp";
  }
  $("cmp-cidade").value = "";
  sincronizarLadoB();
  pintarLadoA();
  carregarLadoB();
  carregarCidadesDoLadoB();
  comparacaoAberta = cmp;
  atualizarEndereco();
  $("comparar").showModal();
}

$("abrir-comparar").addEventListener("click", () => abrirComparar());
$("comparar").addEventListener("close", () => { clearTimeout(cmpTimer); cmpSeq++; comparacaoAberta = null; atualizarEndereco(); });
$("cmp-cargo").addEventListener("change", (e) => mudouLadoB("cargo", e.target.value));
$("cmp-uf").addEventListener("change", (e) => mudouLadoB("uf", e.target.value));
$("cmp-turno").addEventListener("change", (e) => mudouLadoB("turno", e.target.value));
$("cmp-cidade").addEventListener("input", escolherCidadeDoLadoB);
$("cmp-cidade").addEventListener("change", escolherCidadeDoLadoB);
aoRenderizar.push(() => { if ($("comparar").open) pintarLadoA(); });

const comparacaoDoEndereco = lerComparacao(params.get("comparar"));
if (comparacaoDoEndereco && !embutido) abrirComparar(comparacaoDoEndereco);
