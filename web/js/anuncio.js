/* Faixa de anúncio: o texto entra como texto puro e o link só vale com http(s). Com imagem, ela vem acima do texto; se não
   carregar, some e fica o texto. Link, quando há, cobre a faixa toda (imagem e texto): um link só para leitor de tela. */
const ehHttp = (endereco) => /^https?:\/\//i.test(endereco || "");
async function carregarAnuncio() {
  try {
    const corpo = await (await fetch("/api/anuncio", { cache: "no-store" })).json();
    const faixa = $("anuncio");
    faixa.hidden = !corpo.ativo;
    if (!corpo.ativo) return;
    const partes = [];
    if (ehHttp(corpo.imagem)) {
      const imagem = criar("img", { class: "anuncio-imagem", src: corpo.imagem, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
      imagem.addEventListener("error", () => { imagem.remove(); faixa.classList.remove("com-imagem"); });
      partes.push(imagem);
    }
    partes.push(criar("span", { class: "anuncio-texto" }, corpo.texto));
    const conteudo = ehHttp(corpo.link)
      ? criar("a", { class: "anuncio-conteudo", href: corpo.link, target: "_blank", rel: "sponsored noopener noreferrer" }, ...partes)
      : criar("div", { class: "anuncio-conteudo" }, ...partes);
    faixa.classList.toggle("com-imagem", ehHttp(corpo.imagem));
    faixa.replaceChildren(criar("span", { class: "anuncio-rotulo" }, corpo.rotulo), conteudo);
  } catch { /* sem faixa: o placar não depende dela */ }
}
carregarAnuncio();
setInterval(carregarAnuncio, 10 * 60 * 1000);
