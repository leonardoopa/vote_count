/* Service worker do Contador de votos: deixa a página instalável e abrir sem rede.
   Os dados (/api/*) nunca são guardados: placar velho enganaria. Só a página é copiada, e só como reserva. */
const RESERVA = "contador-votos-pagina-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (evento) => {
  evento.waitUntil(Promise.all([
    caches.keys().then((nomes) => Promise.all(nomes.filter((n) => n !== RESERVA).map((n) => caches.delete(n)))),
    self.clients.claim(),
  ]));
});

self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET" || pedido.mode !== "navigate") return;   // só a abertura da página
  evento.respondWith(
    fetch(pedido)
      .then((resposta) => {
        if (resposta.ok) { const copia = resposta.clone(); caches.open(RESERVA).then((c) => c.put("/", copia)); }
        return resposta;
      })
      .catch(() => caches.match("/").then((guardada) => guardada || new Response("Sem conexão. Abra de novo quando a rede voltar.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } }))),
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
