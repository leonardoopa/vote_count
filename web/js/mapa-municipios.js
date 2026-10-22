/* Mapa por município. O desenho (geo/<uf>.json, do IBGE) e os dados (uma busca ao TSE por cidade, feita aos poucos
   pelo servidor) só são pedidos quando a pessoa clica; depois o mapa enche conforme as cidades chegam. */
const INTERVALO_MAPA_MUN = 15000;
const munGeo = {};                                   // desenhos já baixados, por UF
const mun = { aberto: false, seq: 0, timer: 0, marca: "", dados: null };
const temMapaMun = () => (estado.cargo === "presidente" || estado.cargo === "governador") && estado.uf !== "br";
const marcaMun = () => [estado.cargo, estado.uf, estado.turno, estado.ambiente].join("|");

function resumoDaCidade(r) {
  if (r.situacao === "zerado") return "Apuração ainda não começou";
  if (r.situacao === "empate") return `Empate no topo: ${r.empatados.map(nomeDoCandidato).join(" e ")}`;
  return `${nomeDoCandidato(r.lider)} lidera com ${pct(r.lider.percentual)}${r.lider.eleito ? " · eleito" : ""}, ${pp(r.margem)} à frente (${inteiro(r.margem_votos)} votos) · ${pct(r.apurado)} das seções`;
}

function desenharMapaMun() {
  const geo = munGeo[estado.uf];
  if (!geo || !mun.dados) return;
  const d = mun.dados, porCodigo = d.cidades;
  const svg = criarSvg("svg", { viewBox: `0 0 ${geo.w} ${geo.h}`, role: "img", "aria-label": `Mapa dos municípios de ${UFS[estado.uf]} com o líder de cada cidade já carregada.` });
  const grupo = criarSvg("g");
  for (const [ibge, forma] of Object.entries(geo.m)) {
    const r = porCodigo[ibge];
    const caminho = criarSvg("path", { d: forma, style: pintura(r && r.situacao === "lider" ? r : null), "data-codigo": r ? r.codigo : "" });
    if (r) {
      if (r.codigo === estado.municipio) caminho.classList.add("atual");
      caminho.addEventListener("pointermove", (e) => mostrarDicaEm([criar("strong", {}, r.nome), criar("span", {}, resumoDaCidade(r))], e.clientX, e.clientY));
      caminho.addEventListener("pointerleave", () => { dica.hidden = true; });
      caminho.addEventListener("click", () => { dica.hidden = true; irParaCidade({ uf: estado.uf, codigo: r.codigo }); });
    } else {
      caminho.style.cursor = "default";
    }
    grupo.append(caminho);
  }
  svg.append(grupo);
  $("mapa-mun-svg").replaceChildren(svg);
  const contagem = new Map();
  for (const r of Object.values(porCodigo)) if (r.situacao === "lider") contagem.set(r.lider.partido, (contagem.get(r.lider.partido) || 0) + 1);
  $("mapa-mun-legenda").replaceChildren(...[...contagem].sort((a, b) => b[1] - a[1]).map(([partido, n]) => criar("li", {},
    criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), `${partido}: ${inteiro(n)} ${n > 1 ? "cidades" : "cidade"}`)),
    criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--muted);opacity:0.35" }), "Cinza: ainda não carregada ou sem líder"));
  $("mapa-mun-info").textContent = `${inteiro(d.carregadas)} de ${inteiro(d.total)} cidades`;
  $("mapa-mun-nota").hidden = d.carregadas >= d.total;
  $("mapa-mun-nota").textContent = d.carregadas >= d.total ? "" : "O servidor busca as cidades no TSE aos poucos; o mapa enche sozinho. Clique numa cidade para ver o placar dela.";
}

async function carregarMapaMun() {
  clearTimeout(mun.timer);
  const minha = ++mun.seq, uf = estado.uf;
  if (!mun.aberto || !temMapaMun()) return;
  $("mapa-mun-tentar").hidden = true;
  try {
    if (!munGeo[uf]) {
      $("mapa-mun-nota").hidden = false;
      $("mapa-mun-nota").textContent = "Baixando o desenho dos municípios…";
      const resposta = await fetch(`/geo/${uf}.json`);
      if (!resposta.ok) throw new Error("desenho");
      munGeo[uf] = await resposta.json();
    }
  } catch {
    if (minha !== mun.seq) return;
    $("mapa-mun-nota").hidden = false;
    $("mapa-mun-nota").textContent = "Não foi possível baixar o desenho dos municípios. Vou tentar de novo em instantes; se preferir, tente agora.";
    $("mapa-mun-tentar").hidden = false;
    mun.timer = setTimeout(carregarMapaMun, 15000);
    return;
  }
  const resposta = await tentar("/api/mapa-municipal", new URLSearchParams({ cargo: estado.cargo, uf, turno: estado.turno, ambiente: estado.ambiente }));
  if (minha !== mun.seq) return;
  $("mapa-mun-corpo").hidden = false;
  if (resposta.ok) {
    mun.dados = resposta.corpo;
    desenharMapaMun();
  } else {
    $("mapa-mun-nota").hidden = false;
    $("mapa-mun-nota").textContent = resposta.corpo.erro || "Mapa por município indisponível agora.";
  }
  if (!document.hidden) mun.timer = setTimeout(carregarMapaMun, resposta.ok && resposta.corpo.carregadas < resposta.corpo.total ? INTERVALO_MAPA_MUN / 3 : INTERVALO_MAPA_MUN);
}

aoMudarSelecao.push(() => {
  $("mapa-mun").hidden = !temMapaMun();
  if (!temMapaMun()) { clearTimeout(mun.timer); mun.seq++; mun.marca = ""; return; }
  if (marcaMun() === mun.marca) {   // só mudou a cidade: o mapa é o mesmo, muda o contorno marcado
    for (const caminho of $("mapa-mun-svg").querySelectorAll("path")) caminho.classList.toggle("atual", caminho.dataset.codigo !== "" && caminho.dataset.codigo === estado.municipio);
    return;
  }
  mun.marca = marcaMun();
  mun.dados = null;
  $("mapa-mun-corpo").hidden = true;
  $("mapa-mun-info").textContent = "";
  $("mapa-mun-tentar").hidden = true;
  $("mapa-mun-abrir").hidden = mun.aberto;
  if (!mun.aberto) { $("mapa-mun-nota").hidden = false; $("mapa-mun-nota").textContent = "O TSE publica um arquivo por cidade, então o servidor busca as cidades uma a uma e o mapa enche aos poucos. Só começa se você pedir."; }
  carregarMapaMun();
});
$("mapa-mun-abrir").addEventListener("click", () => { mun.aberto = true; $("mapa-mun-abrir").hidden = true; carregarMapaMun(); });
$("mapa-mun-tentar").addEventListener("click", carregarMapaMun);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(mun.timer);
  else if (mun.aberto && mun.marca) carregarMapaMun();
});
