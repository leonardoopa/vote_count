/* Abas por cargo no topo. O select #cargo continua na página (escondido) e guarda o estado: a aba só muda o valor dele
   e dispara o "change", então tudo o que já reage à troca de cargo continua valendo. */
const ABAS = [
  { rotulo: "Presidente", cargos: ["presidente"] },
  { rotulo: "Governador", cargos: ["governador"] },
  { rotulo: "Senado", cargos: ["senador"] },
  { rotulo: "Deputados", cargos: ["deputado-federal", "deputado-estadual", "deputado-distrital"] },
];
const TIPOS_DE_DEPUTADO = [["deputado-federal", "Federal"], ["deputado-estadual", "Estadual"], ["deputado-distrital", "Distrital"]];

function escolherCargo(cargo) {
  if (cargo === estado.cargo) return;
  $("cargo").value = cargo;
  $("cargo").dispatchEvent(new Event("change", { bubbles: true }));
}

function botaoDeAba(rotulo, ativa, aoClicar) {
  const botao = criar("button", { type: "button", "aria-pressed": String(ativa) }, rotulo);
  botao.addEventListener("click", aoClicar);
  return botao;
}

function pintarAbas() {
  $("abas").replaceChildren(...ABAS.map(({ rotulo, cargos }) => botaoDeAba(rotulo, cargos.includes(estado.cargo), () => escolherCargo(cargos.includes(estado.cargo) ? estado.cargo : cargos[0]))));
  const deputado = estado.cargo.startsWith("deputado");
  $("abas-deputado").hidden = !deputado;
  if (deputado) $("abas-deputado").replaceChildren(...TIPOS_DE_DEPUTADO.map(([cargo, rotulo]) => botaoDeAba(rotulo, cargo === estado.cargo, () => escolherCargo(cargo))));
}
aoMudarSelecao.push(pintarAbas);
