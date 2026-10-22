/* Zoom e arrasto de um mapa SVG, feitos só no viewBox: traços e textos não engrossam. A rolagem comum continua
   rolando a página. Ampliam: Ctrl/⌘ + rolagem, pinça, os botões e as teclas + − 0. Arrastar (ou as setas) move.
   `caixa` é o elemento que contém o `svg`; os botões entram nela. `aoParar(vista)` roda 250 ms depois do último gesto. */
function ativarZoom(caixa, svg, largura, altura, { maximo = 40, aoParar = () => {} } = {}) {
  const vista = { x: 0, y: 0, k: 1 };   // canto do recorte e ampliação, em unidades do desenho
  const dedos = new Map();               // ponteiros apoiados no mapa: id -> {x, y, x0, y0} (pixels da tela)
  let parou = 0, lembreteTimer = 0, lembreteEm = 0, moveu = false, ultimaDistancia = 0, ultimoCentro = null;

  const botao = (texto, rotulo, ao) => {
    const b = criar("button", { class: "botao", type: "button", "aria-label": rotulo, title: rotulo }, texto);
    b.addEventListener("click", ao);
    return b;
  };
  const tudo = botao("Ver tudo", "Voltar ao mapa inteiro", () => reiniciar());
  tudo.hidden = true;
  const lembrete = criar("div", { class: "mapa-dica", role: "status", hidden: "" }, "Segure Ctrl (⌘ no Mac) e role para ampliar.");
  caixa.classList.add("mapa-zoom");
  caixa.append(criar("div", { class: "zoom-botoes" }, botao("+", "Ampliar o mapa", () => ampliar(1.6)), botao("−", "Reduzir o mapa", () => ampliar(1 / 1.6)), tudo), lembrete);

  const limitar = () => {
    vista.k = Math.min(maximo, Math.max(1, vista.k));
    vista.x = Math.min(largura - largura / vista.k, Math.max(0, vista.x));
    vista.y = Math.min(altura - altura / vista.k, Math.max(0, vista.y));
  };
  const aplicar = () => {
    limitar();
    svg.setAttribute("viewBox", `${vista.x} ${vista.y} ${largura / vista.k} ${altura / vista.k}`);
    caixa.classList.toggle("ampliado", vista.k > 1);
    tudo.hidden = vista.k === 1;
    clearTimeout(parou);
    parou = setTimeout(() => aoParar(vista), 250);
  };
  const noDesenho = (x, y) => {           // onde o ponteiro está: fração do mapa na tela e ponto do desenho embaixo dele
    const r = svg.getBoundingClientRect();
    const fx = r.width ? (x - r.left) / r.width : 0.5, fy = r.height ? (y - r.top) / r.height : 0.5;
    return { fx, fy, ux: vista.x + fx * largura / vista.k, uy: vista.y + fy * altura / vista.k };
  };
  const ampliar = (fator, x, y) => {      // o ponto sob (x, y) fica parado; sem ponto, vale o centro do mapa
    const r = svg.getBoundingClientRect();
    const { fx, fy, ux, uy } = noDesenho(x ?? r.left + r.width / 2, y ?? r.top + r.height / 2);
    vista.k = Math.min(maximo, Math.max(1, vista.k * fator));
    vista.x = ux - fx * largura / vista.k;
    vista.y = uy - fy * altura / vista.k;
    aplicar();
  };
  const mover = (dx, dy) => {             // deslocamento em pixels da tela
    const r = svg.getBoundingClientRect();
    if (!r.width) return;
    vista.x -= dx / r.width * largura / vista.k;
    vista.y -= dy / r.height * altura / vista.k;
    aplicar();
  };
  const reiniciar = () => { Object.assign(vista, { x: 0, y: 0, k: 1 }); aplicar(); };

  svg.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey)) {      // rolagem comum: a página rola e o mapa só lembra como ampliar (no máximo a cada 8 s)
      if (Date.now() - lembreteEm < 8000) return;
      lembreteEm = Date.now();
      lembrete.hidden = false;
      clearTimeout(lembreteTimer);
      lembreteTimer = setTimeout(() => { lembrete.hidden = true; }, 2200);
      return;
    }
    e.preventDefault();
    ampliar(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.15 : 0.004)), e.clientX, e.clientY);
  }, { passive: false });

  const doisDedos = () => [...dedos.values()].slice(0, 2);
  const distancia = () => { const [a, b] = doisDedos(); return Math.hypot(a.x - b.x, a.y - b.y); };
  const centro = () => { const [a, b] = doisDedos(); return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
  svg.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    dedos.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY });
    moveu = false;
    if (dedos.size === 2) { ultimaDistancia = distancia(); ultimoCentro = centro(); }
  });
  svg.addEventListener("pointermove", (e) => {
    const dedo = dedos.get(e.pointerId);
    if (!dedo) return;
    const antes = { x: dedo.x, y: dedo.y };
    dedo.x = e.clientX;
    dedo.y = e.clientY;
    if (dedos.size >= 2) {                // pinça: amplia pelo afastamento dos dedos e move pelo deslocamento do meio
      const d = distancia(), c = centro();
      if (ultimaDistancia) ampliar(d / ultimaDistancia, c.x, c.y);
      if (ultimoCentro) mover(c.x - ultimoCentro.x, c.y - ultimoCentro.y);
      ultimaDistancia = d;
      ultimoCentro = c;
      moveu = true;
      return;
    }
    if (!moveu && Math.hypot(e.clientX - dedo.x0, e.clientY - dedo.y0) < 5) return;   // ainda é um clique
    if (!moveu) {
      moveu = true;
      try { svg.setPointerCapture(e.pointerId); } catch { /* sem captura: o arrasto segue enquanto o ponteiro estiver no mapa */ }
      caixa.classList.add("arrastando");
    }
    if (vista.k > 1) mover(e.clientX - antes.x, e.clientY - antes.y);
  });
  const soltar = (e) => {
    dedos.delete(e.pointerId);
    ultimaDistancia = 0;
    ultimoCentro = null;
    if (!dedos.size) {
      caixa.classList.remove("arrastando");
      setTimeout(() => { moveu = false; }, 0);   // o clique que vem logo depois de um arrasto ainda enxerga `moveu`
    }
  };
  svg.addEventListener("pointerup", soltar);
  svg.addEventListener("pointercancel", soltar);
  svg.addEventListener("click", (e) => { if (moveu) { e.stopPropagation(); e.preventDefault(); } }, true);   // arrastar não escolhe cidade

  svg.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const seta = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[e.key];
    if (e.key === "+" || e.key === "=") ampliar(1.6);
    else if (e.key === "-" || e.key === "_") ampliar(1 / 1.6);
    else if (e.key === "0") reiniciar();
    else if (seta && vista.k > 1) { const r = svg.getBoundingClientRect(); mover(seta[0] * r.width * 0.15, seta[1] * r.height * 0.15); }
    else return;
    e.preventDefault();
  });

  return {
    vista, ampliar, reiniciar,
    unidadesPorPixel: () => largura / vista.k / (svg.getBoundingClientRect().width || 1),
    destruir() { clearTimeout(parou); clearTimeout(lembreteTimer); },
  };
}
