/* Modo claro e modo escuro. Sem escolha, a página segue o sistema; o botão grava a escolha (data-tema no <html> e no
   localStorage) e avisa quem pinta com cores lidas da CSS (o canvas dos municípios) pelo evento "tema". */
const CHAVE_TEMA = "contador-tema";
const sistemaEscuro = matchMedia("(prefers-color-scheme: dark)");

function temaEscolhido() {
  try { return localStorage.getItem(CHAVE_TEMA); } catch { return null; }   // sem armazenamento: segue o sistema
}

const temaEscuro = () => (document.documentElement.dataset.tema || (sistemaEscuro.matches ? "escuro" : "claro")) === "escuro";

function pintarBotaoDoTema() {
  const botao = document.getElementById("tema");
  if (!botao) return;
  const escuro = temaEscuro();
  botao.textContent = escuro ? "Modo claro" : "Modo escuro";   // o botão diz para onde vai
  botao.setAttribute("aria-pressed", String(escuro));
}

function aplicarTema(tema, avisar = true) {
  if (tema === "claro" || tema === "escuro") document.documentElement.dataset.tema = tema;
  else delete document.documentElement.dataset.tema;
  pintarBotaoDoTema();
  if (avisar) window.dispatchEvent(new Event("tema"));   // na carga ninguém pintou ainda: não há o que avisar
}

aplicarTema(temaEscolhido(), false);
sistemaEscuro.addEventListener("change", () => { if (!temaEscolhido()) aplicarTema(null); });
document.addEventListener("DOMContentLoaded", () => {
  pintarBotaoDoTema();
  document.getElementById("tema").addEventListener("click", () => {
    const novo = temaEscuro() ? "claro" : "escuro";
    try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* vale só nesta visita */ }
    aplicarTema(novo);
  });
});
