let paperbuild = { products: [], settings: {} };
const $ = (selector, scope = document) => scope.querySelector(selector);

const money = (product) => product.is_free ? "Free" : `${paperbuild.settings.currency || "INR"} ${Number(product.price_inr || 0).toLocaleString("en-IN")}`;
const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));

async function loadPublicData() {
  try {
    const response = await fetch("/api/public", { headers: { "Accept": "application/json" } });
    if (!response.ok) return;
    paperbuild = await response.json();
    applySettings();
    renderDynamicPage();
  } catch (error) {
    console.warn("PaperBuild API unavailable", error);
  }
}

function applySettings() {
  const s = paperbuild.settings || {};
  if (s.primary_color) document.documentElement.style.setProperty("--blue", s.primary_color);
  if (s.secondary_color) document.documentElement.style.setProperty("--blue-dark", s.secondary_color);
  document.querySelectorAll("[data-brand], .brand").forEach((node) => {
    const mark = node.querySelector?.(".brand-mark");
    if (mark) node.innerHTML = `<span class="brand-mark" aria-hidden="true"></span>${escapeHtml(s.brand_name || "PaperBuild")}`;
    else node.textContent = s.brand_name || "PaperBuild";
  });
  document.querySelectorAll("[data-instagram], a[href='https://instagram.com/']").forEach((a) => { if (s.instagram_url) a.href = s.instagram_url; });
  document.querySelectorAll("[data-youtube], a[href='https://youtube.com/']").forEach((a) => { if (s.youtube_url) a.href = s.youtube_url; });
  if (s.favicon && !$("link[rel='icon']")) {
    const icon = document.createElement("link");
    icon.rel = "icon";
    icon.href = s.favicon;
    document.head.appendChild(icon);
  }
}

function productCard(product) {
  return `<article class="card">
    <a class="product-thumb" style="background-image:url('${escapeHtml(product.thumbnail || "/assets/paperbuild-hero.png")}')" href="/product/${escapeHtml(product.slug)}/" aria-label="${escapeHtml(product.name)}"></a>
    <div class="card-body"><h3>${escapeHtml(product.name)}</h3><p>${escapeHtml(product.description)}</p>
    <div class="meta"><span class="pill">${escapeHtml(product.difficulty)}</span><span class="pill">${escapeHtml(product.build_time)}</span></div>
    <div class="price-row"><span class="price">${money(product)}</span><a class="btn btn-secondary" href="/product/${escapeHtml(product.slug)}/">View Template</a></div></div>
  </article>`;
}

function renderDynamicPage() {
  const path = location.pathname;
  const products = paperbuild.products || [];
  if (path === "/" || path === "/index.html") renderHome(products);
  if (path.startsWith("/shop")) renderShop(products);
  if (path.startsWith("/free-templates")) renderFree(products.filter((p) => p.is_free));
  if ($("[data-page='product']")) renderProduct(products.find((p) => p.slug === $("[data-page='product']").dataset.slug));
  if (path.startsWith("/checkout")) renderCheckout(products.find((p) => !p.is_free) || products[0]);
  if (path.startsWith("/about")) renderAbout();
  if (path.startsWith("/contact")) renderContact();
}

function renderHome(products) {
  const s = paperbuild.settings;
  const heroTitle = $(".hero h1");
  const heroSubtitle = $(".hero .lead");
  const heroImage = $(".hero-image img");
  const homepageSummary = $(".homepage-sections .homepage-summary");
  if (heroTitle) heroTitle.textContent = s.hero_title || heroTitle.textContent;
  if (heroSubtitle) heroSubtitle.textContent = s.hero_subtitle || heroSubtitle.textContent;
  if (heroImage && s.hero_image) heroImage.src = s.hero_image;
  if (homepageSummary) homepageSummary.textContent = s.homepage_sections || homepageSummary.textContent;
  if (s.announcement) {
    if (!$(".announcement")) {
      document.body.insertAdjacentHTML("afterbegin", `<div class="announcement">${escapeHtml(s.announcement)}</div>`);
    }
  }
  const featured = products.filter((p) => p.is_featured).slice(0, 8);
  const cards = $(".section-soft .cards");
  if (cards && featured.length) cards.innerHTML = featured.map(productCard).join("");
}

function renderShop(products) {
  const grid = $(".cards");
  if (grid && products.length) grid.innerHTML = products.map(productCard).join("");
}

function renderFree(products) {
  const product = products[0];
  const form = $("[data-free-form]");
  const heroTitle = $(".page-hero h1");
  const heroSubtitle = $(".page-hero p");
  const image = $(".feature-image img");
  if (!form || !product) return;
  form.dataset.productId = product.id;
  if (heroTitle) heroTitle.textContent = product.name || heroTitle.textContent;
  if (heroSubtitle) heroSubtitle.textContent = product.description || heroSubtitle.textContent;
  if (image) image.src = product.thumbnail || image.src;
}

function renderProduct(product) {
  const main = $("[data-page='product']");
  if (!main) return;
  if (!product) {
    main.innerHTML = `<section class="section"><div class="container"><h1>Product not found</h1><p class="lead">This template is unavailable.</p></div></section>`;
    return;
  }
  const previews = [product.thumbnail, ...(product.preview_images || [])].filter(Boolean);
  main.innerHTML = `<section class="page-hero"><div class="container"><span class="eyebrow">Product details</span><h1>${escapeHtml(product.name)}</h1><p>${escapeHtml(product.description)}</p></div></section>
  <section class="section"><div class="container detail-grid"><div><div class="preview-large"><img src="${escapeHtml(product.thumbnail || "/assets/paperbuild-hero.png")}" alt="${escapeHtml(product.name)} preview"></div>
  <div class="gallery">${previews.slice(0, 3).map((img) => `<div style="background-image:url('${escapeHtml(img)}')"></div>`).join("")}</div></div>
  <aside class="included"><div class="price-row"><h2>${money(product)}</h2><span class="pill">${product.is_free ? "Free template" : "Paid template"}</span></div>
  <div class="stats"><div class="stat"><b>Difficulty</b><span>${escapeHtml(product.difficulty)}</span></div><div class="stat"><b>Build time</b><span>${escapeHtml(product.build_time)}</span></div><div class="stat"><b>Format</b><span>Printable PDF</span></div><div class="stat"><b>Delivery</b><span>Secure download</span></div></div>
  <h3>What's Included</h3><ul><li>Printable PDF template</li><li>Step-by-step Build Guide</li><li>Secure download access</li></ul>
  <div class="actions">${product.is_free ? `<a class="btn btn-primary" href="/free-templates/">Get Free PDF</a>` : `<a class="btn btn-primary" href="/checkout/?product=${product.id}">Buy Now</a>`}<a class="btn btn-secondary" href="/shop/">Back to shop</a></div></aside></div></section>`;
}

function renderCheckout(fallback) {
  const params = new URLSearchParams(location.search);
  const product = paperbuild.products.find((p) => p.id == params.get("product")) || fallback;
  const form = $("[data-checkout]");
  const aside = $(".included");
  if (!form || !product) return;
  form.dataset.productId = product.id;
  form.dataset.amount = product.price_inr;
  if (aside) {
    aside.innerHTML = `<h2>${escapeHtml(product.name)}</h2><p>${escapeHtml(product.description)}</p><div class="summary-line"><span>Template pack</span><strong>${money(product)}</strong></div><div class="summary-line"><span>Payment</span><strong>UPI</strong></div><div class="summary-line"><span>Merchant UPI</span><strong>${escapeHtml(paperbuild.settings.upi_id || "chayan58@fam")}</strong></div><div class="summary-line"><span>Delivery</span><strong>After verification</strong></div><div class="summary-line"><span>Total</span><strong>${money(product)}</strong></div>`;
  }
}

function renderAbout() {
  const text = $(".page-hero p");
  if (text && paperbuild.settings.about_text) text.textContent = paperbuild.settings.about_text;
}

function renderContact() {
  const text = $(".page-hero p");
  if (text && paperbuild.settings.contact_info) text.textContent = paperbuild.settings.contact_info;
}

function navInit() {
  const toggle = $(".mobile-toggle");
  const links = $(".nav-links");
  if (!toggle || !links) return;
  toggle.addEventListener("click", () => {
    const open = links.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(open));
  });
}

function formsInit() {
  document.addEventListener("submit", async (event) => {
    const freeForm = event.target.closest("[data-free-form]");
    const checkout = event.target.closest("[data-checkout]");
    if (freeForm) {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(freeForm).entries());
      payload.productId = Number(freeForm.dataset.productId || paperbuild.products.find((p) => p.is_free)?.id);
      const result = await postJson("/api/free-download", payload);
      location.href = result.downloadUrl;
    }
    if (checkout) {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(checkout).entries());
      payload.productId = Number(checkout.dataset.productId);
      const result = await postJson("/api/orders", payload);
      const payee = paperbuild.settings.upi_id || "chayan58@fam";
      const amount = checkout.dataset.amount || result.amount;
      const note = encodeURIComponent(`PaperBuild ${result.orderId}`);
      const upiUrl = `upi://pay?pa=${encodeURIComponent(payee)}&pn=${encodeURIComponent(paperbuild.settings.brand_name || "PaperBuild")}&am=${amount}&cu=INR&tn=${note}`;
      const panel = $("[data-upi-panel]", checkout);
      const intent = $("[data-upi-intent]", checkout);
      const qr = $("[data-upi-qr]", checkout);
      const status = $("[data-payment-status]", checkout);
      if (intent) intent.href = upiUrl;
      if (qr) qr.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(upiUrl)}`;
      if (panel) panel.hidden = false;
      if (status) status.textContent = `Order ${result.orderId} created. Downloads unlock only after verified payment.`;
    }
  });

  document.querySelectorAll("[data-newsletter], [data-contact]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const success = form.parentElement.querySelector(".success") || form.querySelector(".success");
      if (success) success.classList.add("is-visible");
      form.reset();
    });
  });
}

async function postJson(url, payload) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}

function downloadInit() {
  const panel = $("[data-download-panel]");
  if (!panel) return;
  const token = new URLSearchParams(location.search).get("token");
  if (!token) return;
  panel.innerHTML = `<span class="eyebrow">Unlocked download</span><h1>Your files are ready</h1><p class="lead">Download access is token-protected. PDF URLs are never shown directly.</p><div class="actions"><a class="btn btn-primary" href="/download/file/${encodeURIComponent(token)}?kind=template">Download Template</a><a class="btn btn-secondary" href="/download/file/${encodeURIComponent(token)}?kind=guide">Download Build Guide</a></div>`;
}

function shareInit() {
  document.querySelectorAll("[data-share]").forEach((link) => {
    const target = encodeURIComponent(window.location.href);
    const title = encodeURIComponent(document.title);
    if (link.dataset.share === "twitter") link.href = `https://twitter.com/intent/tweet?url=${target}&text=${title}`;
    if (link.dataset.share === "facebook") link.href = `https://www.facebook.com/sharer/sharer.php?u=${target}`;
    if (link.dataset.share === "whatsapp") link.href = `https://wa.me/?text=${title}%20${target}`;
  });
}

navInit();
formsInit();
downloadInit();
shareInit();
loadPublicData();
