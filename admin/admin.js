const app = document.querySelector("#app");
let state = { view: "Dashboard", data: null };
const views = ["Dashboard","Products","Orders","Customers","Free Downloads","Analytics","Website","Settings"];
const money = (n) => `INR ${Number(n || 0).toLocaleString("en-IN")}`;

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

async function boot() {
  const me = await api("/api/admin/me");
  if (me.setupRequired) return renderAuth("Create admin password", "setup");
  if (!me.authenticated) return renderAuth("Admin login", "login");
  await load();
}

function renderAuth(title, mode) {
  app.innerHTML = `<main class="login"><form><h1>${title}</h1><p class="muted">${mode === "setup" ? "This one-time setup stores a secure password hash in the database." : "Sign in to manage PaperBuild."}</p><label>Password<input class="input" type="password" name="password" minlength="8" required></label><button class="btn primary">${mode === "setup" ? "Create Admin" : "Login"}</button><p class="error"></p></form></main>`;
  app.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/api/admin/${mode}`, { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(e.target))), headers: { "Content-Type": "application/json" } });
      await boot();
    } catch (err) { app.querySelector(".error").textContent = err.message; }
  });
}

async function load() {
  state.data = await api("/api/admin/data");
  render();
}

function shell(content) {
  app.innerHTML = `<div class="app"><aside class="sidebar"><div class="brand">${state.data.settings.brand_name || "PaperBuild"}</div><div class="nav">${views.map(v => `<button class="${state.view===v?"active":""}" data-view="${v}">${v}</button>`).join("")}</div></aside><main class="main"><div class="top"><h1>${state.view}</h1><button class="btn" data-logout>Logout</button></div>${content}</main></div>`;
  app.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { state.view = b.dataset.view; render(); });
  app.querySelector("[data-logout]").onclick = async () => { await api("/api/admin/logout", { method: "POST" }); boot(); };
}

function render() {
  const d = state.data;
  if (state.view === "Dashboard") return shell(`<div class="grid cards">${metric("Total sales", d.analytics.totalSales)}${metric("Revenue", money(d.analytics.totalRevenue))}${metric("Free downloads", d.analytics.freeDownloads)}${metric("Customers", d.analytics.totalCustomers)}</div><section class="panel" style="margin-top:16px"><h2>Recent orders</h2>${ordersTable(d.orders.slice(0,8))}</section>`);
  if (state.view === "Products") return renderProducts();
  if (state.view === "Orders") return shell(`<section class="panel">${ordersTable(d.orders, true)}</section>`);
  if (state.view === "Customers") return shell(`<div class="toolbar"><a class="btn primary" href="/api/admin/export/customers.csv">Export CSV</a></div><section class="panel">${customersTable(d.customers)}</section>`);
  if (state.view === "Free Downloads") return renderFreeDownloads();
  if (state.view === "Analytics") return shell(`<div class="grid cards">${metric("Total sales", d.analytics.totalSales)}${metric("Revenue", money(d.analytics.totalRevenue))}${metric("Conversion", d.analytics.conversionRate + "%")}${metric("Best seller", d.analytics.bestSellingProduct)}</div><section class="panel" style="margin-top:16px"><h2>Simple sales chart</h2><div class="chart">${d.products.map(p => `<div class="bar" title="${p.name}" style="height:${Math.max(6,d.orders.filter(o=>o.product_id===p.id&&o.payment_status==="Paid").length*30)}px"></div>`).join("")}</div></section>`);
  if (state.view === "Website") return renderSettings(["hero_title","hero_subtitle","hero_image","announcement","homepage_sections","about_text","contact_info","instagram_url","youtube_url"], "Website content");
  if (state.view === "Settings") return renderSettings(["brand_name","logo","primary_color","secondary_color","favicon","currency","upi_id"], "Brand settings");
}

function metric(label, value) { return `<section class="panel metric"><span class="muted">${label}</span><b>${value}</b></section>`; }

function renderProducts(edit = null) {
  const product = edit || {};
  shell(`<div class="toolbar"><button class="btn primary" data-new>New product</button></div><section class="panel"><h2>${product.id ? "Edit product" : "Add product"}</h2>${productForm(product)}</section><section class="panel" style="margin-top:16px"><h2>Products</h2>${productsTable(state.data.products)}</section>`);
  app.querySelector("[data-new]").onclick = () => renderProducts({});
  bindProductForm();
}

function renderFreeDownloads() {
  shell(`<section class="panel"><div class="toolbar"><button class="btn primary" data-add-free>Add free template</button></div><p class="muted">Free templates are products marked as Free. Downloads and collected emails are counted here.</p>${downloadsTable(state.data.downloads)}<section class="panel" style="margin-top:16px"><h2>Free download records</h2>${freeDownloadRecordsTable(state.data.freeDownloadRecords)}</section></section>`);
  app.querySelector("[data-add-free]").onclick = () => {
    state.view = "Products";
    renderProducts({ is_free: 1, enabled: 1, is_featured: 0, price_inr: 0, difficulty: "Easy" });
  };
  app.querySelectorAll("[data-edit]").forEach(b => {
    b.onclick = () => {
      state.view = "Products";
      renderProducts(state.data.products.find(p => p.id == b.dataset.edit));
    };
  });
  app.querySelectorAll("[data-delete]").forEach(b => b.onclick = async () => { if(confirm("Delete this free template?")) { await api(`/api/admin/products/${b.dataset.delete}`, { method:"DELETE" }); await load(); } });
}

function productForm(p) {
  return `<form class="form" data-product-form enctype="multipart/form-data">${p.id ? `<input type="hidden" name="id" value="${p.id}">` : ""}<label>Name<input class="input" name="name" value="${esc(p.name)}" required></label><label>Slug<input class="input" name="slug" value="${esc(p.slug)}"></label><label>Price in INR<input class="input" type="number" name="price_inr" value="${p.price_inr || 0}"></label><label>Difficulty<input class="input" name="difficulty" value="${esc(p.difficulty || "Easy")}"></label><label>Build time<input class="input" name="build_time" value="${esc(p.build_time || "")}"></label><label>Order<input class="input" type="number" name="sort_order" value="${p.sort_order || 0}"></label><label class="full">Description<textarea name="description">${esc(p.description)}</textarea></label><div class="checkrow full"><label><input type="checkbox" name="enabled" ${p.enabled !== 0 ? "checked" : ""}> Enabled</label><label><input type="checkbox" name="is_free" ${p.is_free ? "checked" : ""}> Free</label><label><input type="checkbox" name="is_featured" ${p.is_featured ? "checked" : ""}> Featured</label></div><label>Thumbnail<input type="file" name="thumbnail" accept="image/*"></label><label>Preview images<input type="file" name="preview_images" accept="image/*" multiple></label><label>Printable PDF<input type="file" name="template_pdf" accept="application/pdf"></label><label>Build guide PDF<input type="file" name="guide_pdf" accept="application/pdf"></label><button class="btn primary full">Save product</button></form>`;
}

function bindProductForm() {
  app.querySelector("[data-product-form]").onsubmit = async (e) => { e.preventDefault(); await fetch("/api/admin/products", { method: "POST", body: new FormData(e.target) }); await load(); };
  app.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => renderProducts(state.data.products.find(p => p.id == b.dataset.edit)));
  app.querySelectorAll("[data-delete]").forEach(b => b.onclick = async () => { if(confirm("Delete this product?")) { await api(`/api/admin/products/${b.dataset.delete}`, { method:"DELETE" }); await load(); } });
}

function productsTable(rows) {
  return `<div class="table-wrap"><table class="table"><thead><tr><th></th><th>Name</th><th>Price</th><th>Status</th><th>Order</th><th></th></tr></thead><tbody>${rows.map(p => `<tr><td>${p.thumbnail ? `<img class="preview" src="${p.thumbnail}">` : ""}</td><td>${esc(p.name)}<br><span class="muted">${esc(p.slug)}</span></td><td>${p.is_free ? "Free" : money(p.price_inr)}</td><td><span class="pill">${p.enabled ? "Enabled" : "Disabled"}</span> ${p.is_featured ? `<span class="pill">Featured</span>` : ""}</td><td>${p.sort_order}</td><td><button class="btn" data-edit="${p.id}">Edit</button> <button class="btn danger" data-delete="${p.id}">Delete</button></td></tr>`).join("")}</tbody></table></div>`;
}

function ordersTable(rows, editable = false) {
  return `<div class="table-wrap"><table class="table"><thead><tr><th>Order ID</th><th>Customer</th><th>Product</th><th>Amount</th><th>Payment</th><th>Date</th><th>Download</th></tr></thead><tbody>${rows.map(o => `<tr><td>${esc(o.order_id)}</td><td>${esc(o.customer_name || "")}<br><span class="muted">${esc(o.customer_email || "")}</span></td><td>${esc(o.product_name || "")}</td><td>${money(o.amount)}</td><td>${editable ? statusSelect(o) : esc(o.payment_status)}</td><td>${esc(o.created_at)}</td><td>${esc(o.download_status)}${o.download_token ? `<br><span class="muted">Token active</span>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

function statusSelect(o) { return `<select data-order="${o.id}">${["Pending","Paid","Failed","Refunded"].map(s => `<option ${o.payment_status===s?"selected":""}>${s}</option>`).join("")}</select>`; }
function customersTable(rows) { return `<div class="table-wrap"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>WhatsApp</th><th>Date joined</th><th>Free downloads</th><th>Purchased</th></tr></thead><tbody>${rows.map(c => `<tr><td>${esc(c.name)}</td><td>${esc(c.email)}</td><td>${esc(c.whatsapp)}</td><td>${esc(c.created_at)}</td><td>${c.free_downloads}</td><td>${c.products_purchased}</td></tr>`).join("")}</tbody></table></div>`; }
function downloadsTable(rows) {
  return `<div class="table-wrap"><table class="table"><thead><tr><th></th><th>Name</th><th>Price</th><th>Downloads</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(p => `<tr><td>${p.thumbnail ? `<img class="preview" src="${p.thumbnail}">` : ""}</td><td>${esc(p.name)}<br><span class="muted">${esc(p.slug)}</span></td><td>${p.is_free ? "Free" : money(p.price_inr)}</td><td>${p.downloads || 0}</td><td><span class="pill">${p.enabled ? "Enabled" : "Disabled"}</span></td><td><button class="btn" data-edit="${p.id}">Edit</button> <button class="btn danger" data-delete="${p.id}">Delete</button></td></tr>`).join('')}</tbody></table></div>`;
}

function freeDownloadRecordsTable(rows) {
  return `<div class="table-wrap"><table class="table"><thead><tr><th>Date</th><th>Name</th><th>Email</th><th>WhatsApp</th><th>Template</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.created_at)}</td><td>${esc(r.customer_name)}</td><td>${esc(r.customer_email)}</td><td>${esc(r.whatsapp)}</td><td>${esc(r.product_name)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderSettings(keys, title) {
  const s = state.data.settings;
  shell(`<section class="panel"><h2>${title}</h2><form class="form" data-settings enctype="multipart/form-data">${keys.map(k => field(k, s[k] || "")).join("")}<button class="btn primary full">Save changes</button></form></section>`);
  app.querySelector("[data-settings]").onsubmit = async (e) => { e.preventDefault(); await fetch("/api/admin/settings", { method:"POST", body:new FormData(e.target) }); await load(); };
}

function field(k, v) {
  const label = k.replaceAll("_"," ");
  if (["logo","favicon","hero_image"].includes(k)) return `<label>${label}<input type="file" name="${k}" accept="image/*">${v ? `<span class="muted">${esc(v)}</span>` : ""}</label>`;
  if (["about_text","homepage_sections","contact_info","hero_subtitle","announcement"].includes(k)) return `<label class="full">${label}<textarea name="${k}">${esc(v)}</textarea></label>`;
  const type = k.includes("color") ? "color" : "text";
  return `<label>${label}<input class="input" type="${type}" name="${k}" value="${esc(v)}"></label>`;
}

app.addEventListener("change", async (e) => {
  if (e.target.dataset.order) {
    await api("/api/admin/orders", { method:"POST", body: JSON.stringify({ id:e.target.dataset.order, payment_status:e.target.value }), headers:{ "Content-Type":"application/json" } });
    await load();
  }
});
function esc(v="") { return String(v).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
boot();
