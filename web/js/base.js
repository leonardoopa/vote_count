/* Constantes, utilitários, estado da seleção e ganchos que cada bloco da página usa. */
const CARGOS = {
  presidente: "Presidente",
  governador: "Governador",
  senador: "Senador",
  "deputado-federal": "Deputado federal",
  "deputado-estadual": "Deputado estadual",
  "deputado-distrital": "Deputado distrital",
};
const UFS = {
  ac: "Acre", al: "Alagoas", am: "Amazonas", ap: "Amapá", ba: "Bahia", ce: "Ceará", df: "Distrito Federal",
  es: "Espírito Santo", go: "Goiás", ma: "Maranhão", mg: "Minas Gerais", ms: "Mato Grosso do Sul",
  mt: "Mato Grosso", pa: "Pará", pb: "Paraíba", pe: "Pernambuco", pi: "Piauí", pr: "Paraná",
  rj: "Rio de Janeiro", rn: "Rio Grande do Norte", ro: "Rondônia", rr: "Roraima", rs: "Rio Grande do Sul",
  sc: "Santa Catarina", se: "Sergipe", sp: "São Paulo", to: "Tocantins",
};
/* Cor por partido, a mesma no mapa e nos gráficos: a cor segue o partido, nunca a posição na lista.
   PT em vermelho e PL em azul; as outras cores da paleta vão para partidos grandes e o resto cai em
   "outros". A leitura nunca depende só da cor: há rótulos, legenda e tabela ao lado. */
const COR_PARTIDO = {
  PT: "vermelho", PL: "azul", REPUBLICANOS: "laranja", PSD: "agua",
  PSB: "amarelo", PP: "magenta", MDB: "verde", UNIAO: "violeta",
};
const normalizarPartido = (partido) => partido.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9]/g, "");
const corDoPartido = (partido) => `var(--p-${COR_PARTIDO[normalizarPartido(partido)] || "outros"})`;

const ATUALIZAR_A_CADA = 5000;
const ATUALIZAR_EM_SEGUNDO_PLANO = 30000;   // só com os alertas ligados
const TOP_INICIAL = 15, TOP_PASSO = 30, TOP_MAXIMO = 100;

const $ = (id) => document.getElementById(id);
const criar = (tag, props = {}, ...filhos) => {
  const el = document.createElement(tag);
  for (const [chave, valor] of Object.entries(props)) el.setAttribute(chave, valor);
  el.append(...filhos);
  return el;
};
const criarSvg = (tag, props = {}, ...filhos) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [chave, valor] of Object.entries(props)) el.setAttribute(chave, valor);
  el.append(...filhos);
  return el;
};
const inteiro = (n) => n.toLocaleString("pt-BR");

/* Foto do candidato: um círculo com as iniciais e, por cima, a foto que o TSE publica (a página baixa direto de lá).
   Sem foto, ou se ela não carregar, ficam as iniciais. */
function fotoDoCandidato(c) {
  const iniciais = c.nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => [...p][0]).join("").toUpperCase();
  const el = criar("span", { class: "foto", "aria-hidden": "true" }, iniciais);
  if (typeof c.foto === "string" && c.foto.startsWith("https://")) {
    const img = criar("img", { src: c.foto, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer", width: "40", height: "40" });
    img.addEventListener("error", () => img.remove());
    el.append(img);
  }
  return el;
}
const pct = (n) => n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";

const params = new URLSearchParams(location.search);
const palco = { vista: "brasil" };   // qual mapa está na tela: "brasil", "uf" ou "mundo" (palco.js)
const embutido = params.get("embed") === "1";
if (embutido) document.documentElement.classList.add("embed");   // página dentro de um iframe de outro site: só o placar, sem filtros, mapas nem anúncio
const estado = {
  cargo: params.get("cargo") in CARGOS ? params.get("cargo") : "presidente",
  uf: (params.get("uf") || "").toLowerCase(),
  municipio: /^\d{5}$/.test(params.get("municipio") || "") ? params.get("municipio") : "",
  turno: params.get("turno") === "1" ? "1" : "2",   // quem entra sem escolher turno cai no 2º, que é o que as pessoas vêm ver
  ambiente: params.get("ambiente") === "simulado" ? "simulado" : "oficial",
  top: TOP_INICIAL,
  turnoPadrao: !params.has("turno"),   // o turno veio do padrão, não de uma escolha: se o cargo não tiver 2º turno ainda, mostra o 1º
};

/* Parâmetros da API para a seleção atual (sem `top`). `extra` sobrescreve ou acrescenta campos. */
const consultaSelecao = (extra = {}) => {
  const q = new URLSearchParams({ cargo: estado.cargo, uf: estado.uf, turno: estado.turno, ambiente: estado.ambiente, ...extra });
  if (estado.municipio) q.set("municipio", estado.municipio);
  return q;
};

/* Endereço da tela: a seleção, a comparação aberta (se houver) e o modo incorporado. Quem abre o link vê a mesma tela. */
const temChave = (objeto, chave) => Object.prototype.hasOwnProperty.call(objeto, chave);
/* A comparação vai no endereço como "cargo:uf:turno" ou "cargo:uf:turno:município". Devolve null se o texto não serve. */
function lerComparacao(texto) {
  const [cargo, uf, turno, municipio = ""] = (texto || "").split(":");
  const valida = temChave(CARGOS, cargo) && (uf === "br" || temChave(UFS, uf)) && (turno === "1" || turno === "2") && (!municipio || /^\d{5}$/.test(municipio));
  return valida ? { cargo, uf, turno, municipio } : null;
}
const escreverComparacao = (c) => [c.cargo, c.uf, c.turno, c.municipio].filter(Boolean).join(":");
let comparacaoAberta = null;   // a seleção do lado direito do Comparar, enquanto ele está aberto
function enderecoDaTela({ incorporado = embutido, comparacao = comparacaoAberta } = {}) {
  const q = consultaSelecao();
  if (comparacao) q.set("comparar", escreverComparacao(comparacao));
  if (incorporado) q.set("embed", "1");
  return "?" + q;
}
const atualizarEndereco = () => history.replaceState(null, "", enderecoDaTela());

let sequencia = 0, temporizador = null, ultimo = null, recebidoEm = 0, semConexao = false, alertasLigados = false;
let cidades = [];            // cidades da UF escolhida: [{codigo, nome, capital}]
let sequenciaCidades = 0;

/* Ganchos: cada bloco da página (mapa, evolução…) registra a sua função aqui e não mexe em
   renderizar() nem em trocou(). Um erro num bloco não derruba o placar. */
const aoRenderizar = [];    // (dados) depois que o placar foi pintado
const aoMudarSelecao = [];  // () quando cargo, território, cidade, turno ou ambiente mudam
const GANCHOS_DO_EMBUTIDO = ["pintarResumo", "pintarDuelo"];   // o que roda mesmo na página incorporada
const avisar = (ganchos, ...args) => {
  for (const gancho of ganchos) {
    if (embutido && !GANCHOS_DO_EMBUTIDO.includes(gancho.name)) continue;   // mapas, evolução e o resto nem carregam
    try { gancho(...args); } catch (erro) { console.error(erro); }
  }
};
