/** 广告位：页面底部、板块之间、宽屏侧栏。只有后台开启广告且填写了对应广告位时才会出现。 */
let googleLoaded = false;

function loadGoogle(client) {
  if (googleLoaded) return;
  googleLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.append(s);
}

/** 把广告商给的 HTML 代码放进容器，并让其中的 <script> 真正执行。 */
function injectCode(box, code) {
  const tmp = document.createElement("div");
  tmp.innerHTML = code;
  for (const node of [...tmp.childNodes]) {
    if (node.nodeName === "SCRIPT") {
      const s = document.createElement("script");
      for (const a of node.attributes) s.setAttribute(a.name, a.value);
      s.text = node.textContent;
      box.append(s);
    } else {
      box.append(node);
    }
  }
}

function fill(box, slot, client) {
  if (!box || box.dataset.filled) return;
  box.dataset.filled = "1";
  box.classList.add("on");
  const inner = document.createElement("div");
  inner.className = "ad-inner";
  box.append(Object.assign(document.createElement("span"), { className: "ad-label", textContent: "广告" }));
  box.append(inner);
  if (slot.provider === "google") {
    loadGoogle(client);
    const ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.dataset.adClient = client;
    ins.dataset.adSlot = slot.slot;
    ins.dataset.adFormat = "auto";
    ins.dataset.fullWidthResponsive = "true";
    inner.append(ins);
    (window.adsbygoogle = window.adsbygoogle || []).push({});
  } else {
    injectCode(inner, slot.code);
  }
}

export function mountAds(ads, doc) {
  if (!ads?.slots) return;
  const { slots, google_client: client } = ads;
  if (slots.footer) fill(doc.querySelector("[data-slot=footer]"), slots.footer, client);
  if (slots.side) fill(doc.querySelector("[data-slot=side]"), slots.side, client);
  if (slots.inline) {
    const view = doc.getElementById("view");
    const first = view?.firstElementChild;
    if (first && !view.querySelector("[data-slot=inline]")) {
      const box = document.createElement("div");
      box.className = "ad-slot";
      box.dataset.slot = "inline";
      first.after(box);
      fill(box, slots.inline, client);
    }
  }
}
