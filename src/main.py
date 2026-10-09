import asyncio
import base64
import os
import shutil
from datetime import datetime
from pathlib import Path

import flet as ft

try:
    import flet_camera as fc
except ImportError:
    fc = None

from db import history, init_db, last_price, merchants, product_history, save_ticket, ticket_duplicate
from ticket import Product, Ticket, to_db_products, validate_ticket
from ocr import OCRUnavailable, recognize_image
from parser import parse_argentine_receipt

APP_DATA = Path(os.getenv('FLET_APP_STORAGE_DATA') or Path.home() / '.lector_tickets')
PHOTOS = APP_DATA / 'ticket_photos'
PHOTOS.mkdir(parents=True, exist_ok=True)


def money(value):
    return f'$ {float(value or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def qty(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f'{value:g}'


def date_only(value):
    return str(value or '').split(' ')[0]


def main(page: ft.Page):
    init_db()
    page.title = 'LectorTickets'
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    pending: dict[str, Ticket | None] = {'ticket': None}
    status = ft.Text('Elegí una foto del ticket para comenzar.', color=ft.Colors.GREY_700, size=12)
    errors = ft.Column(spacing=4)
    preview = ft.Column(spacing=8)
    history_view = ft.Column(spacing=6)
    search_results = ft.Column(spacing=4)
    merchant_dropdown = ft.Dropdown(label='Filtrar por comercio', options=[ft.DropdownOption('Todos')], value='Todos', expand=True)
    home_sections = ft.Column()

    def snack(text, color=ft.Colors.GREEN_700):
        page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def show_error(text):
        errors.controls = [ft.Container(ft.Text(text, color=ft.Colors.RED_800, size=12), bgcolor=ft.Colors.RED_50, padding=8, border_radius=8)]
        page.update()

    def clear_preview():
        pending['ticket'] = None
        preview.controls.clear()
        errors.controls.clear()
        status.value = 'Elegí una foto del ticket para comenzar.'
        status.color = ft.Colors.GREY_700
        page.update()

    def render_ticket(ticket: Ticket):
        preview.controls.clear()
        rows = []
        for p in ticket.productos:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(p.nombre, size=11, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(money(p.precio_bruto), size=11)),
                ft.DataCell(ft.Text(qty(p.cantidad), size=11)),
                ft.DataCell(ft.Text(money(p.descuento), size=11)),
                ft.DataCell(ft.Text(money(p.precio_neto), size=11, weight=ft.FontWeight.BOLD)),
            ]))
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(x, size=10)) for x in ['Producto', 'P. Bruto', 'Cant.', 'Desc.', 'P. Neto']],
            rows=rows,
        )
        save_btn = ft.Button('Guardar', icon=ft.Icons.SAVE, on_click=save_pending)
        cancel_btn = ft.TextButton('Cancelar', on_click=lambda _: clear_preview())
        preview.controls.append(ft.Container(content=ft.Column([
            ft.Text('Revisión del ticket', size=16, weight=ft.FontWeight.BOLD),
            ft.Text(f'Comercio: {ticket.comercio}', size=12),
            ft.Text(f'Fecha: {date_only(ticket.fecha)}', size=12),
            ft.Text(f'Total: {money(ticket.total)}', size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
            ft.Row([table], scroll=ft.ScrollMode.AUTO), errors,
            ft.Row([save_btn, cancel_btn], alignment=ft.MainAxisAlignment.END),
        ]), bgcolor=ft.Colors.BLUE_50, border=ft.Border.all(1, ft.Colors.BLUE_200), border_radius=8, padding=10))
        page.update()

    def save_pending(e):
        ticket = pending['ticket']
        if not ticket:
            return
        validation = validate_ticket(ticket)
        if validation:
            show_error(' '.join(validation))
            return
        try:
            if ticket_duplicate(ticket.comercio, ticket.fecha, ticket.total):
                show_error('Este ticket ya parece estar registrado. Si es una compra distinta, revisá comercio, fecha y total antes de guardar.')
                return
            save_ticket(ticket.comercio, ticket.fecha, ticket.total, to_db_products(ticket), ticket.imagen_path)
            clear_preview()
            snack('Ticket guardado correctamente.')
        except Exception as ex:
            show_error(f'No se pudo guardar el ticket: {ex}')

    def reset_sections():
        home_sections.visible = True
        history_panel.visible = False

    async def process_photo(data: bytes, source_name='ticket'):
        if not data:
            show_error('No se recibió ninguna imagen.')
            return
        filename = f'{datetime.now():%Y%m%d_%H%M%S_%f}.jpg'
        path = PHOTOS / filename
        try:
            path.write_bytes(data)
            status.value = 'Procesando ticket con OCR…'
            status.color = ft.Colors.BLUE_800
            preview.controls = [ft.ProgressRing(), ft.Text('Leyendo comercio, fecha, productos y total…')]
            page.update()

            # ML Kit is native and local on Android; keep it off the UI thread.
            text = await asyncio.to_thread(recognize_image, str(path))
            ticket = parse_argentine_receipt(text, str(path))
            pending['ticket'] = ticket

            status.value = 'OCR completado. Revisá los datos antes de guardar.'
            status.color = ft.Colors.GREEN_800
            raw_preview = ft.ExpansionTile(
                title=ft.Text('Ver texto detectado', size=12),
                controls=[ft.Container(ft.Text(text, size=10, selectable=True), padding=8)],
            )
            preview.controls.clear()
            render_ticket(ticket)
            preview.controls.append(raw_preview)
            if not ticket.comercio or not ticket.productos or ticket.total <= 0:
                show_error('El OCR no pudo interpretar todo el ticket. Revisá el texto detectado y sacá otra foto si hace falta.')
            page.update()
        except OCRUnavailable as ex:
            status.value = 'No se pudo leer el ticket.'
            status.color = ft.Colors.RED_800
            show_error(str(ex))
            preview.controls = [ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_700),
                    ft.Text('La foto se guardó correctamente, pero el OCR no pudo interpretarla.', weight=ft.FontWeight.BOLD),
                    ft.Text(f'Imagen: {path.name}', size=11, color=ft.Colors.GREY_700),
                    ft.Text('Probá con el ticket completo, bien enfocado, sin reflejos y ocupando la mayor parte de la imagen.', size=11),
                ]), bgcolor=ft.Colors.RED_50, padding=10, border_radius=8,
            )]
            page.update()
        except Exception as ex:
            status.value = 'Error procesando el ticket.'
            status.color = ft.Colors.RED_800
            show_error(f'No se pudo procesar la imagen: {ex}')
            page.update()

    # Camera: optional dependency. If unavailable, the app remains usable instead of crashing.
    camera = None
    camera_status = ft.Text('', size=11, color=ft.Colors.GREY_700)
    if fc:
        camera = fc.Camera(preview_enabled=True, expand=True)

    async def open_camera(e):
        if camera is None:
            show_error('La función de cámara no está incluida en esta compilación. Podés cargar una imagen desde el dispositivo.')
            return
        try:
            cameras = await camera.get_available_cameras()
            if not cameras:
                show_error('No se encontró ninguna cámara disponible.')
                return
            await camera.initialize(description=cameras[0], resolution_preset=fc.ResolutionPreset.MEDIUM, enable_audio=False, image_format_group=fc.ImageFormatGroup.JPEG)
            dialog = ft.AlertDialog(modal=True, title=ft.Text('Fotografiar ticket'))
            capture = ft.Button('Capturar', icon=ft.Icons.PHOTO_CAMERA)
            close = ft.TextButton('Cerrar')
            async def take(_):
                try:
                    data = await camera.take_picture()
                    if isinstance(data, str):
                        data = base64.b64decode(data)
                    dialog.open = False
                    await process_photo(data)
                    page.update()
                except Exception as ex:
                    camera_status.value = f'No se pudo capturar la foto: {ex}'
                    page.update()
            async def close_camera(_):
                dialog.open = False
                try:
                    await camera.dispose()
                except Exception:
                    pass
                page.update()
            capture.on_click = take
            close.on_click = close_camera
            dialog.content = ft.Container(content=camera, width=320, height=430)
            dialog.actions = [close, capture]
            page.dialog = dialog
            dialog.open = True
            page.update()
        except Exception as ex:
            show_error(f'No se pudo abrir la cámara: {ex}')

    async def pick_image(e):
        try:
            result = await picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
            if result and result.files:
                f = result.files[0]
                if f.path:
                    await process_photo(Path(f.path).read_bytes(), f.name)
                elif f.bytes:
                    await process_photo(f.bytes, f.name)
                else:
                    show_error('El selector no devolvió datos de la imagen.')
        except Exception as ex:
            show_error(f'No se pudo cargar la imagen: {ex}')

    picker = ft.FilePicker()
    page.services.append(picker)

    async def search(e):
        search_results.controls.clear()
        q = (search_input.value or '').strip()
        if not q:
            page.update(); return
        try:
            row = last_price(q)
            if not row:
                search_results.controls.append(ft.Text('No se encontró ningún producto.', color=ft.Colors.GREY_700))
            else:
                name, code, price, date, merchant, gross, discount = row
                search_results.controls.append(ft.Container(content=ft.ListTile(
                    leading=ft.Icon(ft.Icons.SHOPPING_BAG),
                    title=ft.Text(name, weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(f'{merchant} · {date_only(date)}'),
                    trailing=ft.Text(money(price), weight=ft.FontWeight.BOLD),
                    on_click=lambda _: show_product_history(name),
                ), border=ft.Border.all(1, ft.Colors.GREEN_300), border_radius=8))
        except Exception as ex:
            search_results.controls.append(ft.Text(f'Error de búsqueda: {ex}', color=ft.Colors.RED_700))
        page.update()

    def show_product_history(name):
        rows = product_history(name)
        body = [ft.Text(f'Historial: {name}', weight=ft.FontWeight.BOLD)]
        for date, merchant, gross, count, discount, net in rows:
            body.append(ft.Text(f'{date_only(date)} · {merchant} · {qty(count)} × {money(net)}'))
        page.dialog = ft.AlertDialog(title=ft.Text('Historial'), content=ft.Column(body, scroll=ft.ScrollMode.AUTO), actions=[ft.TextButton('Cerrar', on_click=lambda _: close_dialog())])
        page.dialog.open = True
        page.update()

    def close_dialog():
        if page.dialog:
            page.dialog.open = False
            page.update()

    def load_history(e=None):
        history_view.controls.clear()
        try:
            rows = history(merchant_dropdown.value)
            if not rows:
                history_view.controls.append(ft.Text('No hay tickets registrados.', color=ft.Colors.GREY_700))
            else:
                for date, merchant, name, gross, count, discount, net in rows:
                    history_view.controls.append(ft.ListTile(
                        title=ft.Text(name, size=12, weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text(f'{date_only(date)} · {merchant} · Cant. {qty(count)}'),
                        trailing=ft.Text(money(net), weight=ft.FontWeight.BOLD),
                        on_click=lambda _, n=name: show_product_history(n),
                    ))
        except Exception as ex:
            history_view.controls.append(ft.Text(f'No se pudo cargar el historial: {ex}', color=ft.Colors.RED_700))
        page.update()

    def open_history(e):
        merchant_dropdown.options = [ft.DropdownOption('Todos')] + [ft.DropdownOption(m) for m in merchants()]
        merchant_dropdown.value = 'Todos'
        home_sections.visible = False
        history_panel.visible = True
        load_history()

    search_input = ft.TextField(label='Buscar producto...', expand=True, on_submit=search)
    search_btn = ft.IconButton(icon=ft.Icons.SEARCH, on_click=search)

    capture_card = ft.Card(content=ft.Container(content=ft.Column([
        ft.Text('1. Escanear / cargar ticket', size=16, weight=ft.FontWeight.BOLD),
        ft.Row([
            ft.Button('Tomar foto', icon=ft.Icons.CAMERA_ALT, on_click=open_camera),
            ft.Button('Cargar imagen', icon=ft.Icons.IMAGE, on_click=pick_image),
        ], wrap=True),
        camera_status, status, preview,
    ]), padding=10))

    search_card = ft.Column([
        ft.Divider(height=8), ft.Text('2. Consultar último precio', size=16, weight=ft.FontWeight.BOLD),
        ft.Row([search_input, search_btn]), search_results,
    ])
    history_button = ft.Button('Ver historial de compras', icon=ft.Icons.HISTORY, on_click=open_history)
    home_sections.controls = [capture_card, search_card, ft.Divider(height=8), ft.Text('3. Historial de compras', size=16, weight=ft.FontWeight.BOLD), history_button]

    history_panel = ft.Column([
        ft.Row([ft.Text('Historial de compras', size=16, weight=ft.FontWeight.BOLD), ft.TextButton('Volver', on_click=lambda _: reset_sections())], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        merchant_dropdown, history_view,
    ], visible=False)

    page.add(ft.Text('LectorTickets', size=22, weight=ft.FontWeight.BOLD), home_sections, history_panel)


if __name__ == '__main__':
    ft.run(main)
