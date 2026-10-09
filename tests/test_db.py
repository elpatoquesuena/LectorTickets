import os
import sys
from pathlib import Path

os.environ['FLET_APP_STORAGE_DATA'] = '/tmp/lector-tickets-test'
sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))

from db import DB_PATH, history, init_db, last_price, save_ticket, ticket_duplicate


def setup_function():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()


def test_save_and_search():
    save_ticket('Super', '2026-10-07 15:30', 1000, [{
        'nombre': 'Café', 'precio_bruto': 1200, 'cantidad': 1, 'descuento': 200, 'precio_neto': 1000,
    }])
    assert ticket_duplicate('Super', '2026-10-07 16:00', 1000)
    assert last_price('cafe')[0] == 'Café'
    assert len(history()) == 1
