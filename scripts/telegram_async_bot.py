#!/usr/bin/env python3
"""Telegram async bot using python-telegram-bot v20+ and SQLite.

Supports guided GPU browsing (Placas de video) with dynamic brand/family
extraction from `slug_busqueda`, MarkdownV2-safe rendering and pagination.

Usage: set `TELEGRAM_TOKEN` and (optionally) `PRODUCTS_DB` env var then run.
"""
from __future__ import annotations

import os
import re
import logging
import sqlite3
from typing import List, Tuple, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# DB path fallback: prefer environment, otherwise try package scraper_db
DB_PATH = os.environ.get(
    "PRODUCTS_DB",
    os.path.join(os.path.dirname(__file__), "..", "data", "products.db"),
)
try:
    # prefer project's storage.scraper_db.DB_PATH when available
    from storage import scraper_db as _sd

    DB_PATH = getattr(_sd, "DB_PATH", DB_PATH)
except Exception:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- Utilities -----------------------------------------------------------

def escape_md(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    if text is None:
        return ""
    s = str(text)
    # characters that must be escaped in MarkdownV2
    special = r"_ * [ ] ( ) ~ ` > # + - = | { } . !"
    chars = set(special.split())
    out = []
    for ch in s:
        if ch in chars:
            out.append('\\' + ch)
        else:
            out.append(ch)
    return "".join(out)


def escape_md_link(link: str) -> str:
    """Escape characters in a URL used as MarkdownV2 link destination.

    Telegram MarkdownV2 reserves parentheses and backslashes inside link
    destinations, so escape them to avoid "Can't parse entities" errors.
    """
    if not link:
        return ""
    s = str(link)
    # escape backslash first
    s = s.replace('\\', '\\\\')
    # characters that must be escaped in MarkdownV2 (also inside link destinations)
    special = r"_ * [ ] ( ) ~ ` > # + - = | { } . !"
    for ch in special.split():
        # we've already escaped backslashes
        if ch == '\\':
            continue
        s = s.replace(ch, '\\' + ch)
    return s


# ---- GPU brand / family detection ---------------------------------------

def detect_gpu_brands(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    """Detect present GPU brands from `slug_busqueda`.

    Returns list of (label, token) where token is the substring to match in
    `slug_busqueda` (e.g. 'rtx' -> label 'NVIDIA'). Only brands that exist in
    the DB (categoria='Placas de video', activo=1) are returned.
    """
    cur = conn.cursor()
    mapping = [("NVIDIA", "rtx"), ("NVIDIA", "gtx"), ("RADEON", "rx"), ("INTEL", "arc")]
    found = []

    # prefer legacy `productos` table if present, otherwise fallback to
    # `scraped_items` (newer schema). Check which table exists.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
    if cur.fetchone():
        for label, token in mapping:
            cur.execute(
                "SELECT 1 FROM productos WHERE categoria = ? AND activo = 1 AND lower(slug_busqueda) LIKE ? LIMIT 1",
                ("Placas de video", f"%{token}%"),
            )
            if cur.fetchone():
                found.append((label, token))
        return found

    # fallback: use `scraped_items` table and inspect `product_name` or `product_key`
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("scraped_items",))
    if cur.fetchone():
        for label, token in mapping:
            cur.execute(
                "SELECT 1 FROM scraped_items WHERE lower(product_name) LIKE ? LIMIT 1",
                (f"%{token}%",),
            )
            if cur.fetchone():
                found.append((label, token))
    return found


def detect_gpu_families(conn: sqlite3.Connection, brand_token: str) -> List[Tuple[str, str]]:
    """Detect families for a GPU brand token (e.g. 'rtx').

    Returns list of (label, family_key) where `family_key` is a short digit
    prefix used for matching in `slug_busqueda` (e.g. '50' for family 5000).
    The label is human friendly like 'RTX 5000'. Only families that exist in
    the DB are returned.
    """
    cur = conn.cursor()
    token = brand_token.lower()

    # If legacy `productos` table exists, use its slug column. Otherwise
    # gather lower(product_name) from `scraped_items`.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
    if cur.fetchone():
        cur.execute(
            "SELECT DISTINCT lower(slug_busqueda) as s FROM productos WHERE categoria = ? AND activo = 1 AND lower(slug_busqueda) LIKE ?",
            ("Placas de video", f"%{token}%"),
        )
        rows = [r["s"] for r in cur.fetchall()]
    else:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("scraped_items",))
        if cur.fetchone():
            cur.execute(
                "SELECT DISTINCT lower(product_name) as s FROM scraped_items WHERE lower(product_name) LIKE ?",
                (f"%{token}%",),
            )
            rows = [r["s"] for r in cur.fetchall()]
        else:
            rows = []
    families: Dict[str, None] = {}
    # Special-case: Intel ARC has no numeric family tiers (don't expose 'ARC 5000').
    if token == 'arc':
        # if any row contains 'arc', return single ARC family without numeric key
        if rows:
            return [("ARC", "")]
        else:
            return []

    # Find numeric model tokens after the brand token or anywhere in slug
    # Example: 'msi rtx 5080 16gb' -> captures 5080 -> family 5000 -> key '50'
    for s in rows:
        # try to find occurrences like 'rtx 5080' or 'rtx5080'
        for m in re.finditer(rf"{re.escape(token)}\D*(\d{{3,4}})", s):
            num = m.group(1)
            if not num:
                continue
            family_prefix = num[0]  # leading digit -> 5 -> 5000 family
            key = family_prefix + "0"  # '50' to search with LIKE '%50%'
            label = f"{token.upper()} {int(family_prefix) * 1000}"
            families[key] = label
        # fallback: any 4-digit sequence in slug (covers '5090' without prefix)
        for m in re.finditer(r"(\d{3,4})", s):
            num = m.group(1)
            # guard against capturing year-like numbers by ensuring proximity
            # to brand token or presence of token anywhere in slug (already ensured)
            family_prefix = num[0]
            key = family_prefix + "0"
            label = f"{token.upper()} {int(family_prefix) * 1000}"
            families[key] = label

    # Sort families descending (higher-tier first) by numeric family
    sorted_items = sorted(families.items(), key=lambda kv: -int(kv[0]))
    return [(label, key) for key, label in sorted_items]


# ---- Product query & pagination -----------------------------------------

def query_products_for_gpu_family(conn: sqlite3.Connection, brand_token: str, family_key: str) -> List[dict]:
    """Query distinct products for given GPU brand token and family key.

    Uses DISTINCT `nombre`, `precio`, `link` to avoid duplicates.
    `family_key` is a short digits prefix like '50' meaning family 5000.
    """
    cur = conn.cursor()
    brand_like = f"%{brand_token}%"
    family_like = f"%{family_key}%"

    # Prefer legacy `productos` table when present
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
    if cur.fetchone():
        cur.execute(
            """
            SELECT DISTINCT nombre, precio, link, tienda_nombre, stock
            FROM productos
            WHERE categoria = ?
              AND activo = 1
              AND lower(slug_busqueda) LIKE ?
              AND lower(slug_busqueda) LIKE ?
            ORDER BY precio ASC
            """,
            ("Placas de video", brand_like, family_like),
        )
        rows = cur.fetchall()
    else:
        # fallback to `scraped_items` schema
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("scraped_items",))
        if cur.fetchone():
            cur.execute(
                """
                SELECT DISTINCT product_name as nombre, price as precio, product_url as link, shop_name as tienda_nombre, stock
                FROM scraped_items
                WHERE lower(product_name) LIKE ?
                  AND lower(product_name) LIKE ?
                ORDER BY price ASC
                """,
                (brand_like, family_like),
            )
            rows = cur.fetchall()
        else:
            rows = []
    results = []
    seen = set()
    for r in rows:
        key = (r["nombre"], r["precio"], r["link"])  # dedupe tuple
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "nombre": r["nombre"],
                "precio": r["precio"],
                "link": r["link"],
                "tienda_nombre": r["tienda_nombre"],
                "stock": r["stock"],
            }
        )
    return results


def _build_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Anterior", callback_data="page_prev"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ Siguiente", callback_data="page_next"))
    if nav:
        buttons.append(nav)
    # single Volver button (go back to families)
    buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="back_to_familias")])
    return InlineKeyboardMarkup(buttons)


async def render_products_page(query, context: ContextTypes.DEFAULT_TYPE):
    """Render current results page (MarkdownV2) and always edit the message.

    Expects `context.user_data['results']` and `context.user_data['page']`.
    """
    results = context.user_data.get("results", [])
    page = int(context.user_data.get("page", 0))
    per_page = 5
    total = len(results)
    total_pages = (total + per_page - 1) // per_page if total else 1
    start = page * per_page
    end = start + per_page
    items = results[start:end]

    lines = []
    for it in items:
        nombre = escape_md(it.get("nombre") or "")
        tienda = escape_md(it.get("tienda_nombre") or "")
        precio = it.get("precio")
        try:
            precio_int = int(precio) if precio is not None else 0
            precio_str = f"${precio_int:,}"
        except Exception:
            precio_str = escape_md(str(precio or ""))
        precio_esc = escape_md(precio_str)
        stock = it.get("stock")
        stock_text = "En stock" if stock and int(stock) > 0 else "Sin stock"
        stock_esc = escape_md(stock_text)
        link = it.get("link") or ""
        # Escape URL parentheses/backslashes for MarkdownV2 link destination
        link_esc = escape_md_link(link)
        lines.append(f"🔹 *{nombre}*\n🏪 {tienda}\n💰 Precio: {precio_esc}\n📦 {stock_esc}\n🔗 [Ver producto]({link_esc})")

    header = escape_md(f"Resultados (página {page+1}/{max(total_pages,1)})") + "\n\n"
    text = header + "\n\n".join(lines) if lines else escape_md('⚠️ No hay productos para esta familia.')
    if len(text) > 3800:
        text = text[:3800] + "\n\n" + escape_md("(Más resultados omitidos)")

    kb = _build_pagination_keyboard(page, total_pages)
    # Always use edit_message_text per requirement
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN_V2)


# ---- Handlers -----------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Show options: Tiendas (list stores), Procesadores (cpu brand flow), Placas de video (gpu flow)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Tiendas", callback_data="categoria:tiendas"),
            InlineKeyboardButton("Placas de video", callback_data="categoria:gpu"),
        ],
        [InlineKeyboardButton("Procesadores", callback_data="categoria:cpu")],
    ])
    if update.message:
        await update.message.reply_text("¿Qué querés buscar?", reply_markup=kb)
    else:
        # fallback for callbacks
        await update.callback_query.edit_message_text("¿Qué querés buscar?", reply_markup=kb)


async def categoria_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":", 1)[1]
    context.user_data["categoria"] = data
    # Map short tokens to DB category names used in `scraped_items`/`productos`
    category_map = {"cpu": "Procesadores", "gpu": "Placas de video"}
    cat_name = category_map.get(data, data)
    # CPU category: offer Intel/AMD brand chooser (explicit)
    if data == "cpu":
        keyboard = [
            [InlineKeyboardButton("Intel", callback_data="marca:Intel"), InlineKeyboardButton("AMD", callback_data="marca:AMD")],
            [InlineKeyboardButton("Volver", callback_data="back_to_categorias"), InlineKeyboardButton("Cancelar", callback_data="cancel")],
        ]
        await query.edit_message_text('Elegí marca de procesador:', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Tiendas: list all stores (no category filter)
    if data == "tiendas":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
            if cur.fetchone():
                cur.execute('SELECT DISTINCT tienda_nombre FROM productos WHERE activo = 1 ORDER BY tienda_nombre')
                marcas = [r['tienda_nombre'] for r in cur.fetchall()]
            else:
                cur.execute('SELECT DISTINCT shop_name as tienda_nombre FROM scraped_items ORDER BY shop_name')
                marcas = [r['tienda_nombre'] for r in cur.fetchall()]
        except Exception:
            logger.exception('DB error fetching tiendas')
            marcas = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not marcas:
            await query.edit_message_text('No hay tiendas registradas.')
            return

        keyboard = []
        row = []
        for m in marcas:
            row.append(InlineKeyboardButton(m, callback_data=f'marca:{m}'))
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton('Cancelar', callback_data='cancel')])
        await query.edit_message_text('Elige tienda:', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # GPU category: detect brands dynamically from DB
    if data == "gpu":
        try:
            conn = get_conn()
            brands = detect_gpu_brands(conn)
        except Exception:
            logger.exception("DB error detecting gpu brands")
            brands = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not brands:
            await query.edit_message_text("No hay marcas registradas para Placas de video.")
            return

        keyboard = []
        row = []
        for label, token in brands:
            # display label (e.g. NVIDIA) but send token (e.g. 'rtx') as callback
            row.append(InlineKeyboardButton(label, callback_data=f"marca:{token}"))
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
        await query.edit_message_text("Elige marca:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Fallback: handle other categories similar to previous implementation
    try:
        conn = get_conn()
        cur = conn.cursor()
        # prefer legacy `productos` table
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
        if cur.fetchone():
            cur.execute('SELECT DISTINCT tienda_nombre FROM productos WHERE categoria = ? AND activo = 1 ORDER BY tienda_nombre', (cat_name,))
            marcas = [r['tienda_nombre'] for r in cur.fetchall()]
        else:
            # fallback to scraped_items (use case-insensitive match on `category`)
            cur.execute('SELECT DISTINCT shop_name as tienda_nombre FROM scraped_items WHERE lower(category) = lower(?) ORDER BY shop_name', (cat_name,))
            marcas = [r['tienda_nombre'] for r in cur.fetchall()]
    except Exception:
        logger.exception('DB error fetching marcas')
        marcas = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not marcas:
        await query.edit_message_text('No hay marcas registradas para esa categoría.')
        return

    keyboard = []
    row = []
    for m in marcas:
        row.append(InlineKeyboardButton(m, callback_data=f'marca:{m}'))
        if len(row) >= 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton('Cancelar', callback_data='cancel')])
    await query.edit_message_text('Elige marca:', reply_markup=InlineKeyboardMarkup(keyboard))


async def marca_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payload = query.data.split(":", 1)[1]
    categoria = context.user_data.get("categoria")
    context.user_data["marca"] = payload
    # CPU brand flow: show explicit families for Intel/AMD
    if categoria == 'cpu' and payload.lower() in ('intel', 'amd'):
        brand = payload.lower()
        if brand == 'amd':
            familias = ['Ryzen 3', 'Ryzen 5', 'Ryzen 7', 'Ryzen 9']
        else:
            familias = ['Pentium', 'Celeron', 'i3', 'i5', 'i7', 'i9']

        keyboard = []
        row = []
        for f in familias:
            row.append(InlineKeyboardButton(f, callback_data=f'familia:{f}'))
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton('Volver', callback_data='back_to_categorias'), InlineKeyboardButton('Cancelar', callback_data='cancel')])
        await query.edit_message_text(f'Seleccionaste {escape_md(payload)} — elige familia:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # GPU brand flow: payload is brand token like 'rtx', 'rx', 'arc'
    if categoria == 'gpu' and payload in ('rtx', 'gtx', 'rx', 'arc'):
        try:
            conn = get_conn()
            families = detect_gpu_families(conn, payload)
        except Exception:
            logger.exception('DB error detecting gpu families')
            families = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not families:
            await query.edit_message_text('No hay familias disponibles para esa marca.')
            return

        keyboard = []
        row = []
        for label, key in families:
            # show labels like 'RTX 5000' and send family key like '50'
            row.append(InlineKeyboardButton(label, callback_data=f'familia:{label}::{key}'))
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton('Volver', callback_data='back_to_categorias'), InlineKeyboardButton('Cancelar', callback_data='cancel')])
        await query.edit_message_text(f'Seleccionaste {escape_md(payload.upper())} — elige familia:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Non-GPU brands: reuse generic family detection (best-effort)
    try:
        conn = get_conn()
        cur = conn.cursor()
        # Map category token to DB category name
        category_map = {"cpu": "Procesadores", "gpu": "Placas de video"}
        cat_name = category_map.get(categoria, categoria)
        # prefer productos.slug_busqueda, otherwise use scraped_items.product_name
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
        if cur.fetchone():
            cur.execute('SELECT DISTINCT lower(slug_busqueda) as s FROM productos WHERE categoria = ? AND activo = 1 ORDER BY s', (cat_name,))
            rows = [r['s'] for r in cur.fetchall()]
        else:
            cur.execute('SELECT DISTINCT lower(product_name) as s FROM scraped_items WHERE lower(category) = lower(?) ORDER BY s', (cat_name,))
            rows = [r['s'] for r in cur.fetchall()]
        familias = []
        for s in rows:
            parts = s.split()
            if parts:
                candidate = parts[0]
                if candidate not in familias:
                    familias.append(candidate)
    except Exception:
        logger.exception('DB error fetching familias')
        familias = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not familias:
        await query.edit_message_text('No hay familias disponibles para esa marca.')
        return

    keyboard = []
    row = []
    for f in familias:
        row.append(InlineKeyboardButton(f, callback_data=f'familia:{f}'))
        if len(row) >= 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton('Volver', callback_data='back_to_categorias'), InlineKeyboardButton('Cancelar', callback_data='cancel')])
    await query.edit_message_text(f'Seleccionaste {escape_md(payload)} — elige familia:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)


async def familia_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payload = query.data.split(":", 1)[1]
    # payload for GPU families was encoded as 'LABEL::key' (e.g. 'RTX 5000::50')
    if '::' in payload:
        label, family_key = payload.split('::', 1)
    else:
        label = payload
        family_key = None

    categoria = context.user_data.get('categoria')
    marca = context.user_data.get('marca')

    # GPU family selection
    if categoria == 'gpu' and marca in ('rtx', 'rx', 'arc'):
        if not family_key:
            # try to extract numeric prefix from label
            nums = re.findall(r"(\d{2,4})", label)
            family_key = nums[0][:2] if nums else ''
        # Normalize family_key to two-digit prefix (e.g. '50')
        family_key = (family_key or '')[:2]

        try:
            conn = get_conn()
            rows = query_products_for_gpu_family(conn, marca, family_key)
        except Exception:
            logger.exception('DB error fetching products for gpu family')
            rows = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not rows:
            await query.edit_message_text('⚠️ No se encontraron productos disponibles para esa familia.', parse_mode=ParseMode.MARKDOWN_V2)
            return

        # store results and initialize pagination
        context.user_data['results'] = rows
        context.user_data['page'] = 0
        # always edit the same message
        await render_products_page(query, context)
        return

    # Non-GPU family handling (generic)
    # Best-effort query: slug contains family label
    try:
        conn = get_conn()
        cur = conn.cursor()
        # prefer productos table, otherwise scraped_items
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("productos",))
        if cur.fetchone():
            # map category token to DB category name
            category_map = {"cpu": "Procesadores", "gpu": "Placas de video"}
            cat_name = category_map.get(categoria, categoria.title() if categoria else categoria)
            cur.execute(
                "SELECT DISTINCT nombre, precio, link, tienda_nombre, stock FROM productos WHERE categoria = ? AND activo = 1 AND lower(slug_busqueda) LIKE ? ORDER BY precio ASC",
                (cat_name, f"%{label.lower()}%"),
            )
            rows = cur.fetchall()
        else:
            category_map = {"cpu": "Procesadores", "gpu": "Placas de video"}
            cat_name = category_map.get(categoria, categoria)
            cur.execute(
                "SELECT DISTINCT product_name as nombre, price as precio, product_url as link, shop_name as tienda_nombre, stock FROM scraped_items WHERE lower(category) = lower(?) AND lower(product_name) LIKE ? ORDER BY price ASC",
                (cat_name, f"%{label.lower()}%"),
            )
            rows = cur.fetchall()
    except Exception:
        logger.exception('DB error fetching products')
        rows = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    results = []
    seen = set()
    for r in rows:
        key = (r['nombre'], r['precio'], r['link'])
        if key in seen:
            continue
        seen.add(key)
        results.append({'nombre': r['nombre'], 'tienda_nombre': r['tienda_nombre'], 'precio': r['precio'], 'stock': r['stock'], 'link': r['link']})

    if not results:
        await query.edit_message_text('⚠️ No se encontraron productos disponibles.', parse_mode=ParseMode.MARKDOWN_V2)
        return

    context.user_data['results'] = results
    context.user_data['page'] = 0
    await render_products_page(query, context)


async def pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    page = int(context.user_data.get('page', 0))
    results = context.user_data.get('results', [])
    per_page = 5
    total_pages = (len(results) + per_page - 1) // per_page if results else 1

    if action == 'page_next' and page < total_pages - 1:
        context.user_data['page'] = page + 1
    elif action == 'page_prev' and page > 0:
        context.user_data['page'] = page - 1
    elif action == 'back_to_familias':
        # return to family selection for the current marca
        marca = context.user_data.get('marca')
        if not marca:
            await query.edit_message_text('Contexto perdido. Empezá de nuevo con /start')
            return
        try:
            conn = get_conn()
            families = detect_gpu_families(conn, marca)
        except Exception:
            logger.exception('DB error fetching families for back')
            families = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not families:
            await query.edit_message_text('No hay familias disponibles para esa marca.')
            return

        keyboard = []
        row = []
        for label, key in families:
            row.append(InlineKeyboardButton(label, callback_data=f'familia:{label}::{key}'))
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton('Volver', callback_data='back_to_categorias'), InlineKeyboardButton('Cancelar', callback_data='cancel')])
        await query.edit_message_text('Elige familia:', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await render_products_page(query, context)


async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == 'back_to_categorias':
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('Procesadores', callback_data='categoria:cpu'), InlineKeyboardButton('Placas de video', callback_data='categoria:gpu')]])
        await query.edit_message_text('¿Qué querés buscar?', reply_markup=kb)
        return

    await query.edit_message_text('Acción no reconocida.')


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text('Operación cancelada.')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception('Update caused error: %s', context.error)


# ---- Main ---------------------------------------------------------------

def main():
    token = os.environ.get('TELEGRAM_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_TOKEN env var missing')

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(categoria_handler, pattern=r'^categoria:'))
    app.add_handler(CallbackQueryHandler(marca_handler, pattern=r'^marca:'))
    app.add_handler(CallbackQueryHandler(familia_handler, pattern=r'^familia:'))
    app.add_handler(CallbackQueryHandler(pagination_handler, pattern=r'^(page_next|page_prev|back_to_familias)$'))
    app.add_handler(CallbackQueryHandler(back_handler, pattern=r'^back_to_'))
    app.add_handler(CallbackQueryHandler(cancel_handler, pattern=r'^cancel$'))
    app.add_error_handler(error_handler)

    logger.info('Starting bot...')
    app.run_polling()


if __name__ == '__main__':
    main()
