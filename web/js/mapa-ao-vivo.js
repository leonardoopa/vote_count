/* Mapa ao vivo: o que faz a noite de apuração parecer viva e o que deixa rever a noite.
   Os estados acendem do oeste para o leste na primeira pintura; onde chegou voto novo sai uma onda do centro do estado
   (maior, e com o estado piscando, quando o líder muda); e "Rever a noite" toca as fotos que o servidor guardou do mapa
   (/api/mapa-historico): os estados trocam de cor na ordem em que aconteceu. O desenho e a pintura são de mapa-brasil.js. */
const PASSO_DE_REVER_MAPA_MS = 420;
const verMapa = { svg: null, apuradas: new Map(), lideres: new Map() };   // o que o mapa já mostrou, por UF
const reverMapa = { ativo: false, fotos: [], indice: 0, tocando: false, timer: 0, carregando: false };
const semMovimento = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- ondas e entrada ---------- */
function mudancasDoMapa(d) {
  const mudou = [];
  for (const [uf, r] of Object.entries(d.ufs)) {
    if (!r.secoes) continue;
    const lider = r.situacao === "lider" ? r.lider.partido : "";
    const antes = verMapa.apuradas.get(uf), liderAntes = verMapa.lideres.get(uf);
    verMapa.apuradas.set(uf, r.secoes.apuradas);
    verMapa.lideres.set(uf, lider);
    if (antes === undefined) continue;                                   // primeira vez que vê este estado
    const virou = Boolean(lider) && Boolean(liderAntes) && lider !== liderAntes;
    const novas = r.secoes.apuradas - antes;
    if (novas > 0 || virou) mudou.push([uf, novas, virou, lider]);
  }
  return mudou.sort((a, b) => b[1] - a[1]).slice(0, 12);                // os 12 que mais andaram: mais que isso vira confete
}

function lancarOnda(uf, virou, partido) {
  if (!mapaSvg || !mapaSvg.ondas) return;
  const [x, y] = MAPA_UFS[uf].c;
  const onda = criarSvg("circle", { class: "onda" + (virou ? " onda-forte" : ""), cx: x, cy: y, r: 16, style: `stroke:${partido ? corDoPartido(partido) : "var(--ink)"}` });
  onda.addEventListener("animationend", () => onda.remove());
  mapaSvg.ondas.append(onda);
  const caminho = mapaSvg.porUf.get(uf);
  if (virou && caminho) { caminho.classList.add("virou"); setTimeout(() => caminho.classList.remove("virou"), 1700); }
}

function acenderOsEstados() {
  if (semMovimento() || !mapaSvg) return;
  [...mapaSvg.porUf.keys()].sort((a, b) => MAPA_UFS[a].c[0] - MAPA_UFS[b].c[0]).forEach((uf, i) => mapaSvg.porUf.get(uf).style.setProperty("--i", String(i)));
  mapaSvg.svg.classList.add("entrando");
  setTimeout(() => { if (mapaSvg) mapaSvg.svg.classList.remove("entrando"); }, 1800);
}

aoPintarUfs.push((d) => {
  const novo = verMapa.svg !== mapaSvg;                                  // o desenho foi refeito (outro cargo, turno ou ambiente)
  if (novo) { verMapa.svg = mapaSvg; verMapa.apuradas.clear(); verMapa.lideres.clear(); }
  const mudou = mudancasDoMapa(d);
  if (novo) { acenderOsEstados(); return; }
  if (semMovimento() || document.hidden || reverMapa.ativo) return;
  mudou.forEach(([uf, , virou, partido], i) => setTimeout(() => lancarOnda(uf, virou, partido), i * 140));
});

/* ---------- rever a noite ---------- */
const horaDaFotoDoMapa = (foto) => new Date(foto.t * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* Quantos estados cada partido liderava naquela foto (partido vazio = sem líder). */
function contagemDaFoto(foto) {
  const contagem = new Map();
  let semLider = 0;
  for (const [partido] of Object.values(foto.ufs)) {
    if (partido) contagem.set(partido, (contagem.get(partido) || 0) + 1);
    else semLider++;
  }
  return { contagem: [...contagem].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)), semLider };
}

function mostrarFotoDoMapa(i) {
  reverMapa.indice = i;
  const foto = reverMapa.fotos[i];
  for (const [uf, caminho] of mapaSvg.porUf) {
    const [partido, margem] = foto.ufs[uf] || ["", 0, 0];
    caminho.setAttribute("style", pinturaDe(partido, margem));
  }
  const { contagem, semLider } = contagemDaFoto(foto);
  $("replay-mapa-contagem").replaceChildren(...contagem.map(([partido, n]) => criar("li", {},
    criar("i", { class: "amostra-cor", style: `background:${corDoPartido(partido)}` }), `${partido}: ${n} ${n > 1 ? "estados" : "estado"}`)),
    ...(semLider ? [criar("li", {}, criar("i", { class: "amostra-cor", style: "background:var(--muted);opacity:0.35" }), `Sem líder: ${semLider}`)] : []));
  $("replay-mapa-linha").value = String(i);
  $("replay-mapa-linha").setAttribute("aria-valuetext", `Foto ${i + 1} de ${reverMapa.fotos.length}, ${horaDaFotoDoMapa(foto)}`);
  $("replay-mapa-hora").textContent = `${horaDaFotoDoMapa(foto)} · ${i + 1} de ${reverMapa.fotos.length}`;
}

function pararDeReverMapa() {
  clearInterval(reverMapa.timer);
  reverMapa.tocando = false;
  $("replay-mapa-play").textContent = reverMapa.ativo ? "▶ Continuar" : "▶ Rever a noite";
  $("replay-mapa-play").setAttribute("aria-pressed", "false");
}

function tocarReverMapa() {
  if (reverMapa.indice >= reverMapa.fotos.length - 1) mostrarFotoDoMapa(0);
  reverMapa.tocando = true;
  $("replay-mapa-play").textContent = "⏸ Pausar";
  $("replay-mapa-play").setAttribute("aria-pressed", "true");
  clearInterval(reverMapa.timer);
  reverMapa.timer = setInterval(() => {
    if (reverMapa.indice >= reverMapa.fotos.length - 1) { pararDeReverMapa(); return; }
    mostrarFotoDoMapa(reverMapa.indice + 1);
  }, PASSO_DE_REVER_MAPA_MS);
}

function voltarAoVivoDoMapa() {
  const estava = reverMapa.ativo;
  pararDeReverMapa();
  reverMapa.ativo = false;
  reverMapa.fotos = [];
  mapaCongelado = false;
  $("mapa").classList.remove("em-replay");
  $("replay-mapa-linha").hidden = true;
  $("replay-mapa-vivo").hidden = true;
  $("replay-mapa-contagem").hidden = true;
  $("replay-mapa-hora").textContent = "";
  $("replay-mapa-play").textContent = "▶ Rever a noite";
  if (estava && mapaSvg && mapaDados) pintarUfs(mapaDados);             // as cores de agora voltam, com o pisca de quem mudou
}

async function abrirReverMapa() {
  if (reverMapa.carregando || !mapaSvg) return;
  reverMapa.carregando = true;
  $("replay-mapa-hora").textContent = "Buscando a noite…";
  const resposta = await tentar("/api/mapa-historico", new URLSearchParams({ cargo: estado.cargo, turno: estado.turno, ambiente: estado.ambiente }));
  reverMapa.carregando = false;
  if (!mapaSvg) { $("replay-mapa-hora").textContent = ""; return; }
  if (!resposta.ok || resposta.corpo.fotos.length < 2) {
    $("replay-mapa-hora").textContent = "Ainda não há o que rever: o servidor guarda o mapa a cada mudança, enquanto alguém está na página.";
    return;
  }
  reverMapa.fotos = resposta.corpo.fotos;
  reverMapa.ativo = true;
  mapaCongelado = true;
  $("mapa").classList.add("em-replay");
  $("replay-mapa-linha").max = String(reverMapa.fotos.length - 1);
  $("replay-mapa-linha").hidden = false;
  $("replay-mapa-vivo").hidden = false;
  $("replay-mapa-contagem").hidden = false;
  mostrarFotoDoMapa(0);
  tocarReverMapa();
}

$("replay-mapa-play").addEventListener("click", () => {
  if (!reverMapa.ativo) abrirReverMapa();
  else if (reverMapa.tocando) pararDeReverMapa();
  else tocarReverMapa();
});
$("replay-mapa-linha").addEventListener("input", (e) => { pararDeReverMapa(); mostrarFotoDoMapa(Number(e.target.value)); });
$("replay-mapa-vivo").addEventListener("click", voltarAoVivoDoMapa);
aoMudarSelecao.push(voltarAoVivoDoMapa);   // outra seleção (cargo, turno, estado, cidade) encerra o replay
