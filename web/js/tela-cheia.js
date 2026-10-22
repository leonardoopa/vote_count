/* Tela cheia: painel para TV. Mantém a tela acesa enquanto estiver aberto (quando o navegador deixa). */
let travaDeTela = null;
async function manterTelaLigada(ligar) {
  try {
    if (ligar && "wakeLock" in navigator) travaDeTela = await navigator.wakeLock.request("screen");
    else if (travaDeTela) { await travaDeTela.release(); travaDeTela = null; }
  } catch { /* sem trava: a tela pode apagar sozinha */ }
}
if (document.fullscreenEnabled) {
  $("tela-cheia").hidden = false;
  $("tela-cheia").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  });
  document.addEventListener("fullscreenchange", () => {
    const aberta = Boolean(document.fullscreenElement);
    $("tela-cheia").textContent = aberta ? "Sair da tela cheia" : "Tela cheia";
    manterTelaLigada(aberta);
  });
}
