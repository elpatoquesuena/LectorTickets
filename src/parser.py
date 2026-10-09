"""Heuristics for converting OCR text from Argentine receipts into ticket data."""
from __future__ import annotations

import re
from datetime import datetime

from ticket import Product, Ticket

MONEY_RE = r"(?:\$\s*)?(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+(?:[.,]\d{2})?)"
DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b")
BARCODE_RE = re.compile(r"\b\d{8,14}\b")

_EXCLUDE = re.compile(
    r"\b(total|importe|subtotal|sub-total|iva|percep|percepc|cambio|efectivo|tarjeta|d[eé]bito|cr[eé]dito|vuelto|ahorro|descuento|descuento|\bneto\b|\bcajero\b|ticket|factura|fecha|hora|afip|cuit|ingresos brutos)\b",
    re.I,
)


def money_number(value: str) -> float:
    value = value.replace("$", "").replace(" ", "").strip()
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    return float(value)


def _money_at_end(line: str):
    m = re.search(rf"(?:\s|^){MONEY_RE}\s*$", line)
    return (money_number(m.group(1)), m.start()) if m else (None, None)


def parse_argentine_receipt(text: str, image_path: str | None = None) -> Ticket:
    raw_lines = [re.sub(r"\s+", " ", x).strip(" |_") for x in text.splitlines()]
    lines = [x for x in raw_lines if x]

    # Merchant: the first substantial non-administrative line is usually the store name.
    merchant = ""
    for line in lines[:12]:
        if len(line) < 3 or DATE_RE.search(line) or _EXCLUDE.search(line):
            continue
        if re.search(r"\b(cuit|tel|telefono|domicilio|av\.?|avenida|calle|cp\b)\b", line, re.I):
            continue
        merchant = line[:80]
        break

    date = ""
    date_match = next((DATE_RE.search(line) for line in lines if DATE_RE.search(line)), None)
    if date_match:
        d, m, y = date_match.groups()
        if len(y) == 2:
            y = "20" + y
        date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        time_match = TIME_RE.search(date_match.string[date_match.end():]) or TIME_RE.search(date_match.string)
        if time_match:
            date += f" {time_match.group(1).zfill(2)}:{time_match.group(2)}:{(time_match.group(3) or '00')}"
    if not date:
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = None
    total_candidates = []
    for line in lines:
        if re.search(r"\b(total|importe\s+total|total\s+a\s+pagar|a\s+pagar)\b", line, re.I):
            amount, _ = _money_at_end(line)
            if amount is not None:
                total_candidates.append(amount)
    if total_candidates:
        total = total_candidates[-1]

    products: list[Product] = []
    for line in lines:
        amount, pos = _money_at_end(line)
        if amount is None or amount <= 0 or _EXCLUDE.search(line):
            continue
        prefix = line[:pos].strip(" -:")
        if not prefix or len(prefix) < 2:
            continue
        if DATE_RE.search(prefix) or TIME_RE.search(prefix):
            continue
        # Ignore lines that are clearly tax/administrative amounts.
        if re.fullmatch(r"[\d\s./-]+", prefix):
            continue

        barcode_match = BARCODE_RE.search(prefix)
        barcode = barcode_match.group(0) if barcode_match else ""
        name = BARCODE_RE.sub("", prefix).strip(" -*:")

        quantity = 1.0
        qty_match = re.search(r"^(\d+(?:[.,]\d+)?)\s*[xX*]\s*", name)
        if qty_match:
            quantity = float(qty_match.group(1).replace(",", "."))
            name = name[qty_match.end():].strip()
        else:
            qty_match = re.search(r"\s+[xX]\s*(\d+(?:[.,]\d+)?)$", name)
            if qty_match:
                quantity = float(qty_match.group(1).replace(",", "."))
                name = name[:qty_match.start()].strip()

        if len(name) < 2 or len(name) > 100:
            continue
        products.append(Product(barcode, name, amount / quantity if quantity else amount, quantity, 0.0, amount))

    # Remove likely total line accidentally parsed as a product and duplicate rows.
    if total is not None:
        products = [p for p in products if abs(p.precio_neto - total) > 0.005 or len(p.nombre) > 8]

    if total is None and products:
        total = round(sum(p.precio_neto for p in products), 2)
    if total is None:
        total = 0.0

    # Deduplicate adjacent OCR repeats.
    unique = []
    seen = set()
    for p in products:
        key = (p.codigo_barras, p.nombre.lower(), round(p.precio_neto, 2), p.cantidad)
        if key not in seen:
            unique.append(p)
            seen.add(key)

    return Ticket(merchant, date, total, unique, image_path)
