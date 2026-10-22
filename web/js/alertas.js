/* App instalável (PWA) e alertas. O service worker só guarda a página, nunca os dados. */
if ("serviceWorker" in navigator && (location.protocol === "https:" || ["localhost", "127.0.0.1"].includes(location.hostname))) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* sem app instalável: a página funciona igual */ });
}

/* Alertas: avisam quando a apuração começa e quando o resultado fica definido. Funcionam com a página aberta,
   também em segundo plano (a página volta a buscar a cada 30 s). Sem servidor de push, fechar a aba para os alertas. */
const CHAVE_ALERTAS = "contador-alertas";
let alertaAntes = null;   // o que a página viu na leitura anterior da mesma seleção

function preferenciaDeAlertas(novo) {
  try {
    if (novo === undefined) return localStorage.getItem(CHAVE_ALERTAS) === "1";
    localStorage.setItem(CHAVE_ALERTAS, novo ? "1" : "0");
  } catch { /* sem armazenamento: vale só nesta visita */ }
  return novo;
}

function pintarBotaoDeAlertas() {
  const botao = $("alertas");
  botao.textContent = alertasLigados ? "Alertas: ligados" : "Alertas: desligados";
  botao.setAttribute("aria-pressed", String(alertasLigados));
}

async function alternarAlertas() {
  if (alertasLigados) {
    alertasLigados = false;
    preferenciaDeAlertas(false);
  } else {
    let permissao = Notification.permission;
    if (permissao === "default") permissao = await Notification.requestPermission();
    if (permissao !== "granted") {
      mostrarAviso("O navegador não deixou o site enviar notificações. Libere nas configurações do navegador para ligar os alertas.");
      return;
    }
    alertasLigados = true;
    alertaAntes = null;
    preferenciaDeAlertas(true);
    if (!document.hidden) carregar();
  }
  pintarBotaoDeAlertas();
}

async function mostrarAlerta(tituloDoAlerta, texto) {
  const opcoes = { body: texto, icon: "/icone-192.png", badge: "/icone-192.png", tag: "contador-votos" };
  try {
    const registro = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
    if (registro) await registro.showNotification(tituloDoAlerta, opcoes);
    else new Notification(tituloDoAlerta, opcoes);
  } catch { /* sem notificação: o placar na tela continua certo */ }
}

function conferirAlertas(d) {
  if (!alertasLigados || Notification.permission !== "granted") { alertaAntes = null; return; }
  const chave = [estado.cargo, estado.uf, estado.municipio, estado.turno, estado.ambiente].join("|");
  const eleitos = d.candidatos.filter((c) => c.eleito);
  const segundoTurno = d.candidatos.filter((c) => !c.eleito && c.situacao.startsWith("2"));
  const agora = { chave, total: d.votos.total, final: d.final, definidos: [...eleitos, ...segundoTurno].map((c) => c.numero).sort().join(",") };
  const antes = alertaAntes;
  alertaAntes = agora;
  if (!antes || antes.chave !== chave) return;   // primeira leitura desta seleção: só guarda
  const nomes = (lista) => lista.map((c) => `${c.nome} (${c.partido})`).join(" e ");
  if (antes.total === 0 && agora.total > 0) {
    mostrarAlerta("A apuração começou", `${titulo()}: ${pct(d.secoes.percentual)} das seções apuradas.`);
  } else if (agora.definidos && agora.definidos !== antes.definidos) {
    const texto = [eleitos.length ? `Eleito: ${nomes(eleitos)}.` : "", segundoTurno.length ? `Vão ao 2º turno: ${nomes(segundoTurno)}.` : ""].filter(Boolean).join(" ");
    mostrarAlerta("Resultado definido", `${titulo()}. ${texto}`);
  } else if (!antes.final && agora.final) {
    mostrarAlerta("Apuração concluída", `${titulo()}: ${pct(d.secoes.percentual)} das seções apuradas.`);
  }
}

if ("Notification" in window) {
  alertasLigados = preferenciaDeAlertas() && Notification.permission === "granted";
  $("alertas").hidden = false;
  pintarBotaoDeAlertas();
  $("alertas").addEventListener("click", alternarAlertas);
  aoRenderizar.push(conferirAlertas);
  aoMudarSelecao.push(() => { alertaAntes = null; });
}
