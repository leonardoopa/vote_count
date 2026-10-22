/* Service worker do Contador de votos: deixa a página instalável e abrir sem rede.
   Os dados (/api/*) nunca são guardados: placar velho enganaria. Só a página e os arquivos dela (estilo e scripts)
   são copiados, e só como reserva: com rede, vale sempre a resposta do servidor. */
const RESERVA = "contador-votos-pagina-v2";
const ARQUIVOS_DA_PAGINA = /^\/(estilo\.css|js\/[a-z0-9-]+\.js)$/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (evento) => {
  evento.waitUntil(Promise.all([
    caches.keys().then((nomes) => Promise.all(nomes.filter((n) => n !== RESERVA).map((n) => caches.delete(n)))),
    self.clients.claim(),
  ]));
});

self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET") return;
  const url = new URL(pedido.url);
  const abertura = pedido.mode === "navigate" && url.pathname === "/";   // qualquer link da página, com ou sem seleção
  if (url.origin !== location.origin || !(abertura || ARQUIVOS_DA_PAGINA.test(url.pathname))) return;
  const chave = abertura ? "/" : url.pathname;
  evento.respondWith(
    fetch(pedido)
      .then((resposta) => {
        if (resposta.ok) { const copia = resposta.clone(); caches.open(RESERVA).then((c) => c.put(chave, copia)); }
        return resposta;
      })
      .catch(() => caches.match(chave).then((guardada) => guardada || new Response("Sem conexão. Abra de novo quando a rede voltar.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } }))),
  );
});

/* Toque na notificação: volta para a aba aberta ou abre a página. */
self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  evento.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
    for (const janela of janelas) if ("focus" in janela) return janela.focus();
    return self.clients.openWindow("/");
  }));
});
