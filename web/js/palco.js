/* Palco: um mapa só, no centro da página, com três vistas: Brasil (os estados), Estado (os municípios) e Exterior (o mundo).
   `palco.vista` diz qual está na tela e o CSS esconde as outras. Clicar num estado dá zoom animado até ele; clicar numa
   cidade dá outro zoom (mapa-municipios.js). Só a vista que está na tela busca dados no servidor. */
const cargoComMapa = () => estado.cargo === "presidente" || estado.cargo === "governador";

// Quem abre um endereço de estado (?uf=sp) já cai no mapa dos municípios dele.
const ufDoEndereco = (params.get("uf") || "").toLowerCase();
if (!embutido && cargoComMapa() && ufDoEndereco && ufDoEndereco !== "br") {
  palco.vista = "uf";
  mun.aberto = true;
  $("mapa-mun-abrir").hidden = true;
}
$("palco").dataset.vista = palco.vista;

function mostrarVista(vista) {
  if (palco.vista === vista) return;
  palco.vista = vista;
  $("palco").dataset.vista = vista;
  if (vista !== "uf") { clearTimeout(mun.timer); mun.seq++; }
  if (vista !== "mundo") { clearTimeout(mundo.timer); mundo.seq++; }
  if (vista !== "brasil") { clearTimeout(bm.timer); bm.seq++; }
  if (vista === "brasil") garantirCamadaDosMunicipios();
  if (vista === "uf") {
    mun.aberto = true;
    $("mapa-mun-abrir").hidden = true;
    $("mapa-mun-nota").textContent = "Buscando as cidades no TSE: o mapa enche sozinho.";
    carregarMapaMun();
  }
  if (vista === "mundo") {
    mundo.aberto = true;
    $("mundo-abrir").hidden = true;
    $("mundo-nota").textContent = "Buscando as cidades do exterior no TSE: o mapa enche sozinho.";
    carregarMundo();
  }
  pintarTrilha();
  pintarPainelDoCandidato();
}

function irParaVista(vista) {
  if (vista === "brasil") voltarAoBrasil();
  else { if (vista === "mundo") mundo.pais = ""; mostrarVista(vista); }
}

/* Brasil → Estado: o mapa dos estados dá zoom até o escolhido (os outros apagam) e então o mapa dos municípios entra. */
function entrarNaUf(uf) {
  const svg = mapaSvg && mapaSvg.svg, caminho = mapaSvg && mapaSvg.porUf.get(uf);
  const concluir = () => {
    if (estado.uf !== uf) trocou("uf", uf);
    else if (estado.municipio) irParaCidade({ uf, codigo: "" });
    mostrarVista("uf");
  };
  if (palco.vista !== "brasil" || !svg || !caminho) { concluir(); return; }
  svg.classList.add("focando");
  caminho.classList.add("alvo");
  marcarMunicipiosDaUf(uf, true);
  const [largura, altura] = MAPA_VISTA;
  animarViewBox(svg, janelaQueEnquadra(caminho.getBBox(), largura, altura, 1.25), { aoTerminar: concluir });
}

/* Estado ou Exterior → Brasil: o mapa dos estados volta ao tamanho inteiro com o zoom ao contrário. */
function voltarAoBrasil() {
  if (estado.cargo === "presidente" && estado.uf !== "br") trocou("uf", "br");
  else if (estado.municipio) irParaCidade({ uf: estado.uf, codigo: "" });
  mostrarVista("brasil");
  const svg = mapaSvg && mapaSvg.svg;
  if (!svg) return;
  svg.classList.remove("focando");
  for (const caminho of mapaSvg.porUf.values()) caminho.classList.remove("alvo");
  marcarMunicipiosDaUf(estado.uf, false);
  const [largura, altura] = MAPA_VISTA;
  animarViewBox(svg, { x: 0, y: 0, width: largura, height: altura });
}

/* Onde a pessoa está: Brasil › Estado › Cidade, ou Brasil › Exterior › País. Cada passo é um botão que leva até lá. */
function pintarTrilha() {
  const nav = $("trilha");
  nav.hidden = !cargoComMapa();
  if (!cargoComMapa()) return;
  const passos = [["Brasil", palco.vista === "brasil" ? null : voltarAoBrasil]];
  if (palco.vista === "mundo") {
    passos.push(["Exterior", mundo.pais ? () => { mundo.pais = ""; pintarMundo(); pintarPais(); pintarTrilha(); } : null]);
    if (mundo.pais) passos.push([nomeDoPais(mundo.pais), null]);
  } else if (palco.vista === "uf") {
    passos.push([UFS[estado.uf] || estado.uf.toUpperCase(), estado.municipio ? () => irParaCidade({ uf: estado.uf, codigo: "" }) : null]);
    if (estado.municipio) passos.push([cidadeAtual() ? cidadeAtual().nome : "Cidade", null]);
  }
  const marca = passos.map(([texto, ao]) => `${texto}${ao ? "*" : ""}`).join("|");
  if (marca === nav.dataset.marca) return;     // nada mudou: não mexe no que está focado
  nav.dataset.marca = marca;
  nav.replaceChildren(criar("ol", {}, ...passos.map(([texto, ao], i) => {
    const item = criar("li", {}, ao ? criar("button", { class: "botao-link", type: "button" }, texto) : criar("span", { "aria-current": i === passos.length - 1 ? "page" : "false" }, texto));
    if (ao) item.firstChild.addEventListener("click", ao);
    return item;
  })));
}

aoMudarSelecao.push(function ajustarVista() {
  if (palco.vista === "uf" && !temMapaMun()) mostrarVista("brasil");   // trocou para um cargo sem mapa ou voltou para o Brasil no filtro
  pintarTrilha();
});
aoRenderizar.push(() => pintarTrilha());   // o nome da cidade só chega depois da lista de cidades
