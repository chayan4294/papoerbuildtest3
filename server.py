from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import base64
import csv
import hashlib
import hmac
import html
import io
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "paperbuild.db")
PUBLIC_UPLOADS = os.path.join(ROOT, "uploads")
PRIVATE_UPLOADS = os.path.join(ROOT, "private_uploads")
SESSION_TTL = 60 * 60 * 12


def ensure_dirs():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(PUBLIC_UPLOADS, exist_ok=True)
    os.makedirs(PRIVATE_UPLOADS, exist_ok=True)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    ensure_dirs()
    with db() as conn:
        conn.executescript(
            """
            create table if not exists admins (
              id integer primary key, username text unique not null,
              password_hash text not null, created_at text not null
            );
            create table if not exists sessions (
              token text primary key, admin_id integer not null,
              expires_at integer not null
            );
            create table if not exists products (
              id integer primary key, slug text unique not null, name text not null,
              price_inr integer not null default 0, description text not null default '',
              thumbnail text, preview_images text not null default '[]',
              template_pdf text, guide_pdf text, difficulty text not null default 'Easy',
              build_time text not null default '45 min', is_free integer not null default 1,
              is_featured integer not null default 0, enabled integer not null default 1,
              sort_order integer not null default 0, created_at text not null
            );
            create table if not exists customers (
              id integer primary key, name text, email text unique not null,
              whatsapp text, created_at text not null
            );
            create table if not exists orders (
              id integer primary key, order_id text unique not null,
              customer_id integer, product_id integer not null, amount integer not null,
              payment_status text not null default 'Pending',
              download_status text not null default 'Locked',
              download_token text unique, created_at text not null
            );
            create table if not exists free_downloads (
              id integer primary key, customer_id integer, product_id integer not null,
              download_token text unique not null, created_at text not null
            );
            create table if not exists settings (
              key text primary key, value text not null
            );
            """
        )
        defaults = {
            "brand_name": "PaperBuild",
            "primary_color": "#7DB9E8",
            "secondary_color": "#4A92CA",
            "currency": "INR",
            "upi_id": "chayan58@fam",
            "hero_title": "Turn Paper Into Something Amazing.",
            "hero_subtitle": "Printable papercraft templates designed to be easy, fun, and satisfying to build.",
            "hero_image": "/assets/paperbuild-hero.png",
            "announcement": "",
            "homepage_sections": "Download, print, cut, fold, and build polished paper models at home.",
            "about_text": "PaperBuild creates minimal, cute, premium printable papercraft PDF templates for satisfying creative builds.",
            "contact_info": "Questions about templates or downloads? Contact the PaperBuild desk.",
            "instagram_url": "https://instagram.com/",
            "youtube_url": "https://youtube.com/",
            "logo": "",
            "favicon": "",
        }
        for key, value in defaults.items():
            conn.execute("insert or ignore into settings(key,value) values(?,?)", (key, value))
        count = conn.execute("select count(*) from products").fetchone()[0]
        if count == 0:
            seed_products(conn)


def seed_products(conn):
    rows = [
        ("coffee-papercraft", "Coffee Papercraft", 0, "Free cozy desk model for your first PaperBuild project.", "Easy", "45 min", 1, 1, 1),
        ("cute-cat-pack", "Cute Cat Pack", 99, "Three expressive paper cats with matching build guide.", "Easy", "1.5 hrs", 0, 1, 2),
        ("mini-car-pack", "Mini Car Pack", 149, "Small vehicle models with neat fold geometry.", "Medium", "2 hrs", 0, 1, 3),
        ("character-collection", "Character Collection", 199, "A display-ready collection for confident beginners.", "Medium", "3 hrs", 0, 1, 4),
    ]
    now = iso_now()
    for row in rows:
        conn.execute(
            """insert into products(slug,name,price_inr,description,difficulty,build_time,is_free,is_featured,sort_order,created_at,thumbnail)
               values(?,?,?,?,?,?,?,?,?,?,?)""",
            (*row, now, "/assets/paperbuild-hero.png"),
        )


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210000)
    return f"pbkdf2_sha256${salt}${base64.b64encode(digest).decode()}"


def check_password(password, encoded):
    try:
        _, salt, digest = encoded.split("$", 2)
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except ValueError:
        return False


def rowdict(row):
    item = dict(row)
    if "preview_images" in item:
        item["preview_images"] = json.loads(item["preview_images"] or "[]")
    return item


class App(BaseHTTPRequestHandler):
    server_version = "PaperBuild/1.0"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api_get(path)
        if path.startswith("/admin/") and os.path.splitext(path)[1]:
            return self.serve_static(path)
        if path == "/admin" or path.startswith("/admin/"):
            return self.serve_file(os.path.join(ROOT, "admin", "index.html"))
        if path.startswith("/download/file/"):
            return self.download_file(path)
        if path.startswith("/product/") and path.rstrip("/") != "/product":
            return self.product_page(path)
        return self.serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api_post(path)
        self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/admin/products/"):
            if not self.require_admin():
                return
            product_id = path.rsplit("/", 1)[-1]
            with db() as conn:
                conn.execute("delete from products where id=?", (product_id,))
            return self.json({"ok": True})
        self.send_error(404)

    def json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def cookie(self, name):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                if key == name:
                    return value
        return ""

    def current_admin(self):
        token = self.cookie("pb_admin")
        if not token:
            return None
        with db() as conn:
            row = conn.execute("select * from sessions where token=? and expires_at>?", (token, int(time.time()))).fetchone()
            return row

    def require_admin(self):
        if self.current_admin():
            return True
        self.json({"error": "Admin login required"}, 401)
        return False

    def api_get(self, path):
        if path == "/api/public":
            return self.public_data()
        if path == "/api/orders/status":
            return self.order_status()
        if path == "/api/admin/me":
            with db() as conn:
                has_admin = conn.execute("select count(*) from admins").fetchone()[0] > 0
            return self.json({"authenticated": bool(self.current_admin()), "setupRequired": not has_admin})
        if path == "/api/admin/export/customers.csv":
            if not self.require_admin():
                return
            return self.export_customers()
        if path == "/api/admin/data":
            if not self.require_admin():
                return
            return self.admin_data()
        self.send_error(404)

    def api_post(self, path):
        if path == "/api/admin/setup":
            return self.setup_admin()
        if path == "/api/admin/login":
            return self.login()
        if path == "/api/admin/logout":
            return self.logout()
        if path == "/api/free-download":
            return self.free_download()
        if path == "/api/orders":
            return self.create_order()
        if not self.require_admin():
            return
        if path == "/api/admin/products":
            return self.save_product()
        if path == "/api/admin/settings":
            return self.save_settings()
        if path == "/api/admin/orders":
            return self.update_order()
        self.send_error(404)

    def public_data(self):
        with db() as conn:
            products = [rowdict(r) for r in conn.execute("select * from products where enabled=1 order by sort_order,id")]
            settings = {r["key"]: r["value"] for r in conn.execute("select * from settings")}
        for product in products:
            product.pop("template_pdf", None)
            product.pop("guide_pdf", None)
        return self.json({"products": products, "settings": settings})

    def admin_data(self):
        with db() as conn:
            products = [rowdict(r) for r in conn.execute("select * from products order by sort_order,id")]
            orders = [rowdict(r) for r in conn.execute(
                """select o.*, c.name customer_name, c.email customer_email, p.name product_name
                   from orders o left join customers c on c.id=o.customer_id left join products p on p.id=o.product_id
                   order by o.id desc"""
            )]
            customers = [rowdict(r) for r in conn.execute(
                """select c.*, count(distinct fd.id) free_downloads, count(distinct case when o.payment_status='Paid' then o.id end) products_purchased
                   from customers c left join free_downloads fd on fd.customer_id=c.id left join orders o on o.customer_id=c.id
                   group by c.id order by c.id desc"""
            )]
            downloads = [rowdict(r) for r in conn.execute(
                """select p.*, count(fd.id) downloads from products p left join free_downloads fd on fd.product_id=p.id
                   where p.is_free=1 group by p.id order by p.sort_order,p.id"""
            )]
            free_download_records = [rowdict(r) for r in conn.execute(
                """select fd.id, fd.created_at, c.name customer_name, c.email customer_email, c.whatsapp,
                   p.name product_name from free_downloads fd
                   join customers c on c.id=fd.customer_id join products p on p.id=fd.product_id
                   order by fd.id desc"""
            )]
            settings = {r["key"]: r["value"] for r in conn.execute("select * from settings")}
            totals = conn.execute(
                """select count(*) orders, coalesce(sum(case when payment_status='Paid' then amount end),0) revenue,
                   sum(case when payment_status='Paid' then 1 else 0 end) paid_orders from orders"""
            ).fetchone()
            order_count = conn.execute("select count(*) from orders").fetchone()[0]
            customer_count = conn.execute("select count(*) from customers").fetchone()[0]
            best = conn.execute(
                """select p.name, count(o.id) sales from products p join orders o on o.product_id=p.id and o.payment_status='Paid'
                   group by p.id order by sales desc limit 1"""
            ).fetchone()
        conversion = round((totals["paid_orders"] / order_count) * 100, 1) if order_count else 0
        return self.json({
            "products": products, "orders": orders, "customers": customers, "downloads": downloads,
            "freeDownloadRecords": free_download_records, "settings": settings,
            "analytics": {
                "totalSales": totals["paid_orders"], "totalRevenue": totals["revenue"], "freeDownloads": len(free_download_records),
                "paidOrders": totals["paid_orders"], "conversionRate": conversion, "totalCustomers": customer_count,
                "bestSellingProduct": best["name"] if best else "None"
            }
        })

    def setup_admin(self):
        data = self.read_json()
        with db() as conn:
            if conn.execute("select count(*) from admins").fetchone()[0] > 0:
                return self.json({"error": "Admin already exists"}, 409)
            password = data.get("password", "")
            if len(password) < 8:
                return self.json({"error": "Use at least 8 characters"}, 400)
            cur = conn.execute("insert into admins(username,password_hash,created_at) values(?,?,?)",
                         ("admin", hash_password(password), iso_now()))
            admin_id = cur.lastrowid
        token = secrets.token_urlsafe(32)
        with db() as conn:
            conn.execute("insert into sessions(token,admin_id,expires_at) values(?,?,?)",
                         (token, admin_id, int(time.time()) + SESSION_TTL))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", f"pb_admin={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}")
        body = b'{"ok":true}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def login(self):
        data = self.read_json()
        with db() as conn:
            admin = conn.execute("select * from admins where username='admin'").fetchone()
            if not admin or not check_password(data.get("password", ""), admin["password_hash"]):
                return self.json({"error": "Invalid password"}, 401)
            token = secrets.token_urlsafe(32)
            conn.execute("insert into sessions(token,admin_id,expires_at) values(?,?,?)",
                         (token, admin["id"], int(time.time()) + SESSION_TTL))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", f"pb_admin={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}")
        body = b'{"ok":true}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def logout(self):
        token = self.cookie("pb_admin")
        with db() as conn:
            conn.execute("delete from sessions where token=?", (token,))
        self.send_response(200)
        self.send_header("Set-Cookie", "pb_admin=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def upsert_customer(self, conn, name, email, whatsapp=""):
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("Email is required")
        row = conn.execute("select id from customers where email=?", (email,)).fetchone()
        if row:
            conn.execute("update customers set name=coalesce(nullif(?,''),name), whatsapp=coalesce(nullif(?,''),whatsapp) where id=?",
                         (name or "", whatsapp or "", row["id"]))
            return row["id"]
        cur = conn.execute("insert into customers(name,email,whatsapp,created_at) values(?,?,?,?)", (name or "", email, whatsapp or "", iso_now()))
        return cur.lastrowid

    def free_download(self):
        data = self.read_json()
        token = secrets.token_urlsafe(28)
        with db() as conn:
            product = conn.execute("select * from products where id=? and is_free=1 and enabled=1", (data.get("productId"),)).fetchone()
            if not product:
                return self.json({"error": "Free product not found"}, 404)
            customer_id = self.upsert_customer(conn, data.get("name"), data.get("email"), data.get("whatsapp"))
            conn.execute("insert into free_downloads(customer_id,product_id,download_token,created_at) values(?,?,?,?)",
                         (customer_id, product["id"], token, iso_now()))
        return self.json({"downloadUrl": f"/download/?token={token}&type=free"})

    def create_order(self):
        data = self.read_json()
        with db() as conn:
            product = conn.execute("select * from products where id=? and is_free=0 and enabled=1", (data.get("productId"),)).fetchone()
            if not product:
                return self.json({"error": "Paid product not found"}, 404)
            customer_id = self.upsert_customer(conn, data.get("name"), data.get("email"), data.get("whatsapp"))
            order_id = "PB-" + str(int(time.time()))[-7:] + secrets.token_hex(2).upper()
            conn.execute(
                "insert into orders(order_id,customer_id,product_id,amount,payment_status,download_status,created_at) values(?,?,?,?,?,?,?)",
                (order_id, customer_id, product["id"], product["price_inr"], "Pending", "Locked", iso_now()),
            )
        return self.json({"orderId": order_id, "amount": product["price_inr"]})

    def update_order(self):
        data = self.read_json()
        status = data.get("payment_status", "Pending")
        allowed = {"Pending", "Paid", "Failed", "Refunded"}
        if status not in allowed:
            return self.json({"error": "Invalid status"}, 400)
        token = secrets.token_urlsafe(28) if status == "Paid" else None
        with db() as conn:
            if token:
                conn.execute("update orders set payment_status=?, download_status='Unlocked', download_token=? where id=?",
                             (status, token, data.get("id")))
            else:
                conn.execute("update orders set payment_status=?, download_status='Locked', download_token=null where id=?",
                             (status, data.get("id")))
        return self.json({"ok": True})

    def order_status(self):
        query = parse_qs(urlparse(self.path).query)
        order_id = query.get("order_id", [""])[0]
        email = (query.get("email", [""])[0] or "").strip().lower()
        if not order_id or not email:
            return self.json({"error": "Order ID and email are required"}, 400)
        with db() as conn:
            order = conn.execute(
                "select o.*, c.email customer_email, p.name product_name, p.template_pdf, p.guide_pdf from orders o "
                "join customers c on c.id=o.customer_id join products p on p.id=o.product_id "
                "where o.order_id=? and lower(c.email)=?",
                (order_id, email)
            ).fetchone()
            if not order:
                return self.json({"error": "Order not found"}, 404)
            payload = {
                "orderId": order["order_id"],
                "payment_status": order["payment_status"],
                "download_status": order["download_status"],
                "product_name": order["product_name"],
                "amount": order["amount"]
            }
            if order["payment_status"] == "Paid" and order["download_token"]:
                payload["downloadUrl"] = f"/download/?token={order['download_token']}&type=template"
                payload["guideUrl"] = f"/download/?token={order['download_token']}&type=guide"
        return self.json(payload)

    def save_settings(self):
        fields, files = self.parse_form()
        with db() as conn:
            for key, value in fields.items():
                conn.execute("insert into settings(key,value) values(?,?) on conflict(key) do update set value=excluded.value", (key, value))
            for key in ("logo", "favicon", "hero_image"):
                if key in files:
                    conn.execute("insert into settings(key,value) values(?,?) on conflict(key) do update set value=excluded.value",
                                 (key, self.store_upload(files[key], public=True)))
        return self.json({"ok": True})

    def save_product(self):
        fields, files = self.parse_form()
        slug = slugify(fields.get("slug") or fields.get("name") or "product")
        preview_images = []
        for key, filedata in files.items():
            if key.startswith("preview_images"):
                items = filedata if isinstance(filedata, list) else [filedata]
                preview_images.extend(self.store_upload(item, public=True) for item in items)
        existing = None
        with db() as conn:
            if fields.get("id"):
                existing = conn.execute("select * from products where id=?", (fields["id"],)).fetchone()
                if existing and not preview_images:
                    preview_images = json.loads(existing["preview_images"] or "[]")
            values = (
                slug, fields.get("name", ""), int(fields.get("price_inr") or 0), fields.get("description", ""),
                self.store_upload(files["thumbnail"], True) if "thumbnail" in files else (existing["thumbnail"] if existing else ""),
                json.dumps(preview_images),
                self.store_upload(files["template_pdf"], False) if "template_pdf" in files else (existing["template_pdf"] if existing else ""),
                self.store_upload(files["guide_pdf"], False) if "guide_pdf" in files else (existing["guide_pdf"] if existing else ""),
                fields.get("difficulty", "Easy"), fields.get("build_time", ""),
                1 if fields.get("is_free") == "on" else 0,
                1 if fields.get("is_featured") == "on" else 0,
                1 if fields.get("enabled") == "on" else 0,
                int(fields.get("sort_order") or 0),
            )
            if existing:
                conn.execute(
                    """update products set slug=?,name=?,price_inr=?,description=?,thumbnail=?,preview_images=?,template_pdf=?,guide_pdf=?,
                       difficulty=?,build_time=?,is_free=?,is_featured=?,enabled=?,sort_order=? where id=?""",
                    (*values, fields["id"]),
                )
            else:
                conn.execute(
                    """insert into products(slug,name,price_inr,description,thumbnail,preview_images,template_pdf,guide_pdf,difficulty,build_time,
                       is_free,is_featured,enabled,sort_order,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*values, iso_now()),
                )
        return self.json({"ok": True})

    def parse_form(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not ctype.startswith("multipart/form-data"):
            return {}, {}
        boundary = ("--" + ctype.split("boundary=", 1)[1]).encode()
        fields, files = {}, {}
        for part in raw.split(boundary):
            part = part.strip(b"\r\n-")
            if not part or b"\r\n\r\n" not in part:
                continue
            head, body = part.split(b"\r\n\r\n", 1)
            body = body.rstrip(b"\r\n")
            header = head.decode(errors="ignore")
            name = filename = None
            for piece in header.split(";"):
                piece = piece.strip()
                if piece.startswith("name="):
                    name = piece.split("=", 1)[1].strip('"')
                if piece.startswith("filename="):
                    filename = os.path.basename(piece.split("=", 1)[1].strip('"'))
            if not name:
                continue
            if filename:
                if body:
                    item = {"filename": filename, "body": body}
                    if name in files:
                        if isinstance(files[name], list):
                            files[name].append(item)
                        else:
                            files[name] = [files[name], item]
                    else:
                        files[name] = item
            else:
                fields[name] = body.decode(errors="ignore")
        return fields, files

    def store_upload(self, filedata, public):
        ext = os.path.splitext(filedata["filename"])[1].lower()
        if not ext:
            ext = ".bin"
        safe = secrets.token_hex(12) + ext
        folder = PUBLIC_UPLOADS if public else PRIVATE_UPLOADS
        with open(os.path.join(folder, safe), "wb") as f:
            f.write(filedata["body"])
        return f"/uploads/{safe}" if public else safe

    def download_file(self, path):
        token = path.rsplit("/", 1)[-1]
        qs = parse_qs(urlparse(self.path).query)
        kind = qs.get("kind", ["template"])[0]
        with db() as conn:
            product = None
            fd = conn.execute("select product_id from free_downloads where download_token=?", (token,)).fetchone()
            if fd:
                product = conn.execute("select * from products where id=?", (fd["product_id"],)).fetchone()
            else:
                order = conn.execute("select product_id from orders where download_token=? and payment_status='Paid'", (token,)).fetchone()
                if order:
                    product = conn.execute("select * from products where id=?", (order["product_id"],)).fetchone()
            if not product:
                return self.send_error(403)
            filename = product["guide_pdf"] if kind == "guide" else product["template_pdf"]
        if not filename:
            return self.send_error(404, "No PDF uploaded yet")
        return self.serve_file(os.path.join(PRIVATE_UPLOADS, filename), download=True)

    def product_page(self, path):
        slug = path.strip("/").split("/")[1]
        body = public_shell("Product details", f'<main data-page="product" data-slug="{html.escape(slug)}"></main>')
        self.send_html(body)

    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        blocked = ("/data/", "/private_uploads/", "/server.py")
        normalized = "/" + path.lstrip("/").replace("\\", "/")
        if normalized.startswith(blocked) or normalized in blocked:
            return self.send_error(403)
        fs = os.path.abspath(os.path.join(ROOT, path.lstrip("/")))
        if not fs.startswith(ROOT) or os.path.isdir(fs):
            fs = os.path.join(fs, "index.html")
        protected = (os.path.join(ROOT, "data"), PRIVATE_UPLOADS)
        if any(os.path.commonpath([fs, folder]) == folder for folder in protected):
            return self.send_error(403)
        return self.serve_file(fs)

    def serve_file(self, fs, download=False):
        if not os.path.exists(fs) or not os.path.isfile(fs):
            return self.send_error(404)
        ctype = mimetypes.guess_type(fs)[0] or "application/octet-stream"
        with open(fs, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if download:
            self.send_header("Content-Disposition", "attachment")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, body):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def export_customers(self):
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Name", "Email", "WhatsApp", "Date joined", "Free downloads", "Products purchased"])
        with db() as conn:
            for r in conn.execute(
                """select c.name,c.email,c.whatsapp,c.created_at,count(distinct fd.id) free_downloads,
                   count(distinct case when o.payment_status='Paid' then o.id end) products_purchased
                   from customers c left join free_downloads fd on fd.customer_id=c.id left join orders o on o.customer_id=c.id
                   group by c.id order by c.id desc"""
            ):
                writer.writerow([r["name"], r["email"], r["whatsapp"], r["created_at"], r["free_downloads"], r["products_purchased"]])
        body = out.getvalue().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=paperbuild-customers.csv")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def slugify(value):
    out = []
    for ch in value.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(filter(None, "".join(out).split("-"))) or "product"


def public_shell(title, main):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} | PaperBuild</title><link rel="stylesheet" href="/assets/styles.css"></head><body>
<header class="site-header"><nav class="container nav" aria-label="Main navigation"><a class="brand" href="/"><span class="brand-mark" aria-hidden="true"></span><span data-brand>PaperBuild</span></a><button class="mobile-toggle" type="button" aria-label="Open navigation" aria-expanded="false">&#9776;</button><div class="nav-links"><a href="/">Home</a><a href="/free-templates/">Free Templates</a><a href="/shop/">Shop</a><a href="/about/">About</a><a href="/contact/">Contact</a></div></nav></header>
{main}<footer class="footer"><div class="container footer-inner"><span>&copy; 2026 <span data-brand>PaperBuild</span>.</span><div class="socials"><a data-instagram href="#">Instagram</a><a data-youtube href="#">YouTube</a></div></div></footer><script src="/assets/app.js"></script></body></html>"""


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    print(f"PaperBuild running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), App).serve_forever()
