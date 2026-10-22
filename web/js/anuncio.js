/* Faixa de anúncio: o texto entra como texto puro e o link só vale com http(s). */
async function carregarAnuncio() {
  try {
    const corpo = await (await fetch("/api/anuncio", { cache: "no-store" })).json();
    const faixa = $("anuncio");
    faixa.hidden = !corpo.ativo;
    if (!corpo.ativo) return;
    const texto = corpo.link && /^https?:\/\//i.test(corpo.link)
      ? criar("a", { href: corpo.link, target: "_blank", rel: "sponsored noopener noreferrer" }, corpo.texto)
      : criar("span", {}, corpo.texto);
    faixa.replaceChildren(criar("span", { class: "anuncio-rotulo" }, corpo.rotulo), texto);
  } catch { /* sem faixa: o placar não depende dela */ }
}
carregarAnuncio();
setInterval(carregarAnuncio, 10 * 60 * 1000);
