/* Resumo da disputa e exportação do placar em CSV e JSON. */
const MAJORITARIOS = ["presidente", "governador", "senador"];
const pontosPct = (n) => n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " pontos";

/* Resumo: a diferença que decide a disputa (1º e 2º; no Senado, 2º e 3º) e a participação do eleitor. */
function pintarResumo(d) {
  const vagas = estado.cargo === "senador" ? 2 : 1;
  const dentro = d.candidatos[vagas - 1], fora = d.candidatos[vagas];
  const nome = (c) => `${c.nome} (${c.partido})`;
  const [rotulo, valor, detalhe] = d.votos.total === 0
    ? ["Resumo do placar", "Apuração não começou", "Os números aparecem com a primeira totalização."]
    : MAJORITARIOS.includes(estado.cargo) && dentro && fora
      ? [vagas === 1 ? "Diferença entre o 1º e o 2º" : "Diferença entre o 2º (última vaga) e o 3º",
        dentro.votos === fora.votos ? "Empate" : pontosPct(dentro.percentual - fora.percentual),
        `${inteiro(dentro.votos - fora.votos)} votos · ${nome(dentro)} à frente de ${nome(fora)}`]
      : ["Votos apurados", inteiro(d.votos.total), `${inteiro(d.total_candidatos)} candidatos na disputa`];
  $("resumo-rotulo").textContent = rotulo;
  $("resumo-valor").textContent = valor;
  $("resumo-detalhe").textContent = detalhe;
  const destaque = (rotuloDoNumero, percentual, votos) => criar("div", {},
    criar("div", { class: "rotulo" }, rotuloDoNumero), criar("div", { class: "valor" }, pct(percentual)), criar("div", { class: "detalhe" }, `${inteiro(votos)} ${votos === 1 ? "voto" : "votos"}`));
  $("resumo-destaques").replaceChildren(
    destaque("Comparecimento", d.eleitores.pct_comparecimento, d.eleitores.comparecimento),
    destaque("Brancos", d.votos.pct_brancos, d.votos.brancos),
    destaque("Nulos", d.votos.pct_nulos, d.votos.nulos));
  $("resumo").hidden = false;
}
aoRenderizar.push(pintarResumo);
aoMudarSelecao.push(() => { $("resumo").hidden = true; });

/* Exportar: CSV para planilha brasileira (";" e vírgula decimal, com BOM) e JSON com tudo que está na tela. */
function celulaCsv(valor) {
  let texto = String(valor ?? "");
  if (/^[=+\-@\t\r]/.test(texto)) texto = "'" + texto;   // planilha não executa fórmula vinda de dado
  return /[";\n\r]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

function montarCsv(candidatos) {
  const linhas = [["posicao", "numero", "nome", "partido", "votos", "percentual", "situacao"],
    ...candidatos.map((c) => [c.posicao, c.numero, c.nome, c.partido, c.votos, String(c.percentual).replace(".", ","), c.situacao])];
  return "﻿" + linhas.map((linha) => linha.map(celulaCsv).join(";")).join("\r\n") + "\r\n";
}

function baixar(conteudo, tipo, extensao) {
  const lugar = [estado.cargo, estado.uf, estado.municipio, `${estado.turno}turno`].filter(Boolean).join("-");
  const agora = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
  const link = criar("a", { href: url, download: `placar-${lugar}-${agora}.${extensao}` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("exportar-csv").addEventListener("click", () => { if (ultimo) baixar(montarCsv(ultimo.candidatos), "text/csv;charset=utf-8", "csv"); });
$("exportar-json").addEventListener("click", () => {
  if (!ultimo) return;
  const tudo = {
    exportado_em: new Date().toISOString(),
    selecao: { cargo: estado.cargo, uf: estado.uf, municipio: estado.municipio || null, turno: Number(estado.turno), ambiente: estado.ambiente },
    placar: ultimo, evolucao: evo, mapa: mapaDados, regioes: regioesDados, disputas: disputasDados,
  };
  baixar(JSON.stringify(tudo, null, 2), "application/json;charset=utf-8", "json");
});
aoRenderizar.push(() => { $("exportar").hidden = false; });
aoMudarSelecao.push(() => { $("exportar").hidden = true; });
