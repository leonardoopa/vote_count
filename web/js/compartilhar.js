/* Compartilhar: o link desta tela (seleção e comparação) e o código para incorporá-la em outro site. */
const ALTURA_DO_INCORPORADO = 680;
const enderecoCompleto = (opcoes) => location.origin + location.pathname + enderecoDaTela(opcoes);

function codigoParaIncorporar() {
  const endereco = enderecoCompleto({ incorporado: true, comparacao: null }).replaceAll("&", "&amp;");
  return `<iframe src="${endereco}" title="Placar da apuração · Contador de votos" width="100%" height="${ALTURA_DO_INCORPORADO}" style="border:0;max-width:720px" loading="lazy"></iframe>`;
}

async function copiar(campo, mensagem) {
  try {
    await navigator.clipboard.writeText(campo.value);
    $("compartilhar-aviso").textContent = mensagem;
  } catch {
    campo.select();   // sem permissão (ou fora de https): o texto fica selecionado para copiar com Ctrl+C
    $("compartilhar-aviso").textContent = "Selecionei o texto: copie com Ctrl+C (⌘C no Mac).";
  }
}

$("abrir-compartilhar").addEventListener("click", () => {
  $("compartilhar-link").value = enderecoCompleto({ incorporado: false });
  $("compartilhar-codigo").value = codigoParaIncorporar();
  $("compartilhar-aviso").textContent = "";
  $("compartilhar-enviar").hidden = !navigator.share;
  $("compartilhar").showModal();
});
$("compartilhar-copiar-link").addEventListener("click", () => copiar($("compartilhar-link"), "Link copiado ✓"));
$("compartilhar-copiar-codigo").addEventListener("click", () => copiar($("compartilhar-codigo"), "Código copiado ✓"));
$("compartilhar-enviar").addEventListener("click", () => {
  navigator.share({ title: document.title, url: $("compartilhar-link").value }).catch(() => { /* fechou o menu de envio */ });
});
// Na página incorporada, o link de volta leva à mesma seleção, só que na página completa.
$("credito-link").addEventListener("click", () => { $("credito-link").href = enderecoCompleto({ incorporado: false }); });
