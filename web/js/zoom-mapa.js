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
  /* Dá zoom até um retângulo do desenho (`c`: x, y, width, height), com animação. O zoom cresce em proporção, então a
     velocidade parece constante. Quem prefere menos movimento recebe o resultado direto. */
  const irPara = (c, { margem = 1.5, duracao = 750, aoTerminar = () => {} } = {}) => {
    const k = Math.min(maximo, Math.max(1, Math.min(largura / (c.width * margem), altura / (c.height * margem))));
    const alvo = { k, x: c.x + c.width / 2 - largura / k / 2, y: c.y + c.height / 2 - altura / k / 2 };
    const de = { ...vista };
    if (duracao <= 0 || matchMedia("(prefers-reduced-motion: reduce)").matches) { Object.assign(vista, alvo); aplicar(); aoTerminar(); return; }
    const inicio = performance.now();
    const passo = (agora) => {
      const t = Math.min(1, (agora - inicio) / duracao), e = 1 - Math.pow(1 - t, 3);   // desacelera no fim
      vista.k = de.k * Math.pow(alvo.k / de.k, e);
      vista.x = de.x + (alvo.x - de.x) * e;
      vista.y = de.y + (alvo.y - de.y) * e;
      aplicar();
      if (t < 1) requestAnimationFrame(passo);
      else aoTerminar();
    };
    requestAnimationFrame(passo);
  };

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
    vista, ampliar, reiniciar, irPara,
    unidadesPorPixel: () => largura / vista.k / (svg.getBoundingClientRect().width || 1),
    destruir() { clearTimeout(parou); clearTimeout(lembreteTimer); },
  };
}

/* Nomes escritos num mapa com zoom: só das formas largas o bastante na tela (então só com zoom) e dentro da janela.
   `mapa` guarda {zoom, caixas: Map(id -> retângulo no desenho), rotulos: <g>, textos: Map(id -> <text>)}; `nomes` é {id: nome}. */
function rotularMapa(mapa, nomes, largura, altura, { kMinimo = 2, maximo = 150, minimoPx = 44 } = {}) {
  const { x, y, k } = mapa.zoom.vista, janelaL = largura / k, janelaA = altura / k, porPixel = mapa.zoom.unidadesPorPixel();
  const querem = [];
  if (k >= kMinimo) {
    for (const [id, c] of mapa.caixas) {
      const nome = nomes[id], px = c.width / porPixel;
      if (!nome || px < minimoPx || px < nome.length * 6.4 + 8) continue;    // o nome não cabe dentro da forma
      if (c.x + c.width < x || c.x > x + janelaL || c.y + c.height < y || c.y > y + janelaA) continue;
      querem.push([id, c, nome]);
    }
  }
  const mostrar = new Set(querem.sort((a, b) => b[1].width - a[1].width).slice(0, maximo).map(([id]) => id));
  for (const [id, texto] of mapa.textos) if (!mostrar.has(id)) { texto.remove(); mapa.textos.delete(id); }
  for (const [id, c, nome] of querem) {
    if (!mostrar.has(id)) continue;
    let texto = mapa.textos.get(id);
    if (!texto) {
      texto = criarSvg("text", { x: c.x + c.width / 2, y: c.y + c.height / 2 }, nome);
      mapa.textos.set(id, texto);
      mapa.rotulos.append(texto);
    }
    texto.style.fontSize = `${12 * porPixel}px`;     // 12 px na tela, qualquer que seja o zoom
  }
}

/* Anima o viewBox de um svg até a janela `para` ({x, y, width, height}): é o zoom do mapa do Brasil ao entrar num estado.
   Quem prefere menos movimento recebe o resultado direto. */
function animarViewBox(svg, para, { duracao = 650, aoTerminar = () => {} } = {}) {
  const [x0, y0, l0, a0] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
  const aplicar = (x, y, l, a) => svg.setAttribute("viewBox", `${x} ${y} ${l} ${a}`);
  if (duracao <= 0 || matchMedia("(prefers-reduced-motion: reduce)").matches) { aplicar(para.x, para.y, para.width, para.height); aoTerminar(); return; }
  const inicio = performance.now();
  const passo = (agora) => {
    const t = Math.min(1, (agora - inicio) / duracao), e = 1 - Math.pow(1 - t, 3);
    aplicar(x0 + (para.x - x0) * e, y0 + (para.y - y0) * e, l0 + (para.width - l0) * e, a0 + (para.height - a0) * e);
    if (t < 1) requestAnimationFrame(passo);
    else aoTerminar();
  };
  requestAnimationFrame(passo);
}

/* A janela do svg (mesma proporção do desenho) que enquadra um retângulo `c` com folga. */
function janelaQueEnquadra(c, largura, altura, folga = 1.35) {
  const proporcao = largura / altura;
  const l = Math.max(c.width * folga, c.height * folga * proporcao), a = l / proporcao;
  return { x: c.x + c.width / 2 - l / 2, y: c.y + c.height / 2 - a / 2, width: l, height: a };
}
