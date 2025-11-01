// live clock
function tickClock(){
  const el = document.getElementById('liveClock');
  if(!el) return;
  const d = new Date();
  const hh = String(d.getHours()).padStart(2,'0');
  const mm = String(d.getMinutes()).padStart(2,'0');
  const ss = String(d.getSeconds()).padStart(2,'0');
  el.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(tickClock, 1000); tickClock();

// PWA service worker + install prompt
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js');
}
let deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.getElementById('pwaInstallBtn');
  if(btn){ btn.disabled = false; btn.addEventListener('click', async () => {
    btn.disabled = true;
    if(deferredPrompt){ deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt = null; }
  });}
});

// copy coupon message
window.copyMsg = (btn) => {
  const text = btn.getAttribute('data-msg') || '';
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '✅ Copied';
    setTimeout(()=>{ btn.textContent = '📋 Copy'; }, 1500);
  });
};

// WhatsApp share
window.waShare = (btn) => {
  const text = encodeURIComponent(btn.getAttribute('data-msg') || '');
  const phone = (btn.getAttribute('data-phone') || '').replace('+','');
  const url = `https://wa.me/${phone}?text=${text}`;
  window.open(url, '_blank');
};
