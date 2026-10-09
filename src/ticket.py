from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Product:
    codigo_barras: str = ''
    nombre: str = ''
    precio_bruto: float = 0.0
    cantidad: float = 1.0
    descuento: float = 0.0
    precio_neto: float = 0.0


@dataclass
class Ticket:
    comercio: str
    fecha: str
    total: float
    productos: list[Product]
    imagen_path: str | None = None


def empty_demo_ticket() -> Ticket:
    # Kept only as a deterministic local test fixture. It is never used by the production capture button.
    products = [
        Product('7790001001234', 'Leche Entera 1L', 1200, 2, 200, 1000),
        Product('7791234567890', 'Café Molido 250g', 4500, 1, 500, 4000),
    ]
    return Ticket('Supermercado Disco', datetime.now().strftime('%Y-%m-%d %H:%M'), 10250, products)


def validate_ticket(ticket: Ticket) -> list[str]:
    errors = []
    if not ticket.comercio.strip():
        errors.append('Falta el comercio.')
    if not ticket.fecha.strip():
        errors.append('Falta la fecha.')
    if ticket.total < 0:
        errors.append('El total no puede ser negativo.')
    if not ticket.productos:
        errors.append('No se detectaron productos.')
    for i, p in enumerate(ticket.productos, 1):
        if not p.nombre.strip():
            errors.append(f'Producto {i}: falta el nombre.')
        if p.cantidad <= 0:
            errors.append(f'Producto {i}: la cantidad debe ser mayor a cero.')
        if p.precio_neto < 0:
            errors.append(f'Producto {i}: precio inválido.')
    return errors


def to_db_products(ticket: Ticket):
    return [asdict(p) for p in ticket.productos]
