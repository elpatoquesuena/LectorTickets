import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

APP_DATA = Path(os.getenv('FLET_APP_STORAGE_DATA') or Path.home() / '.lector_tickets')
APP_DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DATA / 'tickets.db'


def _normalize(value: str | None) -> str:
    if not value:
        return ''
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', str(value)) if unicodedata.category(c) != 'Mn').lower().strip()


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA busy_timeout = 10000')
    conn.create_function('SIN_ACENTOS', 1, _normalize)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comercio TEXT NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL CHECK(total >= 0),
            imagen_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER NOT NULL REFERENCES compras(id) ON DELETE CASCADE,
            codigo_barras TEXT DEFAULT '',
            nombre TEXT NOT NULL,
            precio_bruto REAL NOT NULL DEFAULT 0,
            cantidad REAL NOT NULL DEFAULT 1,
            descuento REAL NOT NULL DEFAULT 0,
            precio_neto REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_compras_fecha ON compras(fecha DESC);
        CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos(nombre);
        CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo_barras);
        ''')
        # Safe migration for databases created by the old version.
        cols = {row[1] for row in conn.execute('PRAGMA table_info(compras)')}
        if 'imagen_path' not in cols:
            conn.execute('ALTER TABLE compras ADD COLUMN imagen_path TEXT')
        if 'created_at' not in cols:
            conn.execute('ALTER TABLE compras ADD COLUMN created_at TEXT')
            conn.execute("UPDATE compras SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)")


def ticket_duplicate(comercio: str, fecha: str, total: float) -> bool:
    with connection() as conn:
        row = conn.execute('''
            SELECT 1 FROM compras
            WHERE LOWER(TRIM(comercio)) = LOWER(TRIM(?))
              AND DATE(fecha) = DATE(?)
              AND ABS(total - ?) < 0.01
            LIMIT 1
        ''', (comercio, fecha, total)).fetchone()
        return row is not None


def save_ticket(comercio: str, fecha: str, total: float, products: Iterable[dict], image_path: str | None = None) -> int:
    products = list(products)
    if not comercio or not fecha:
        raise ValueError('El comercio y la fecha son obligatorios.')
    if total < 0:
        raise ValueError('El total no puede ser negativo.')
    if not products:
        raise ValueError('El ticket no contiene productos.')

    with connection() as conn:
        cur = conn.execute(
            'INSERT INTO compras(comercio, fecha, total, imagen_path) VALUES (?, ?, ?, ?)',
            (comercio.strip(), fecha, float(total), image_path),
        )
        ticket_id = cur.lastrowid
        conn.executemany('''
            INSERT INTO productos(compra_id, codigo_barras, nombre, precio_bruto, cantidad, descuento, precio_neto)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', [(
            ticket_id,
            str(p.get('codigo_barras') or ''),
            str(p.get('nombre') or 'Producto sin nombre').strip(),
            float(p.get('precio_bruto') or 0),
            float(p.get('cantidad') or 1),
            float(p.get('descuento') or 0),
            float(p.get('precio_neto') or 0),
        ) for p in products])
        return int(ticket_id)


def last_price(query: str):
    q = _normalize(query)
    if not q:
        return None
    with connection() as conn:
        return conn.execute('''
            SELECT p.nombre, p.codigo_barras, p.precio_neto, c.fecha, c.comercio,
                   p.precio_bruto, p.descuento
            FROM productos p JOIN compras c ON c.id = p.compra_id
            WHERE SIN_ACENTOS(p.nombre) LIKE ? OR SIN_ACENTOS(p.codigo_barras) LIKE ?
            ORDER BY c.fecha DESC, p.id DESC LIMIT 1
        ''', (f'%{q}%', f'%{q}%')).fetchone()


def product_history(name: str):
    with connection() as conn:
        return conn.execute('''
            SELECT c.fecha, c.comercio, p.precio_bruto, p.cantidad, p.descuento, p.precio_neto
            FROM productos p JOIN compras c ON c.id = p.compra_id
            WHERE SIN_ACENTOS(p.nombre) = ?
            ORDER BY c.fecha DESC, p.id DESC
        ''', (_normalize(name),)).fetchall()


def merchants():
    with connection() as conn:
        return [r[0] for r in conn.execute('SELECT DISTINCT comercio FROM compras ORDER BY comercio').fetchall()]


def history(merchant: str | None = None):
    with connection() as conn:
        if merchant and merchant != 'Todos':
            return conn.execute('''
                SELECT c.fecha, c.comercio, p.nombre, p.precio_bruto, p.cantidad, p.descuento, p.precio_neto
                FROM productos p JOIN compras c ON c.id = p.compra_id
                WHERE c.comercio = ? ORDER BY c.fecha DESC, p.id ASC
            ''', (merchant,)).fetchall()
        return conn.execute('''
            SELECT c.fecha, c.comercio, p.nombre, p.precio_bruto, p.cantidad, p.descuento, p.precio_neto
            FROM productos p JOIN compras c ON c.id = p.compra_id
            ORDER BY c.fecha DESC, p.id ASC
        ''').fetchall()
