import sqlite3
import unicodedata
from datetime import datetime
import flet as ft

# --- 1. FUNCIONES DE NORMALIZACIÓN Y FORMATO ---
def quitar_acentos(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize('NFD', str(texto))
    return "".join(c for c in texto if unicodedata.category(c) != 'Mn').lower()

def formatear_moneda(valor):
    if valor is None:
        valor = 0.0
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatear_cantidad(valor):
    if valor is None:
        valor = 0
    return f"{int(valor):,}".replace(",", ".")

def formatear_solo_fecha(cadena_fecha):
    if not cadena_fecha:
        return ""
    return cadena_fecha.split(" ")[0]

# --- 2. BASE DE DATOS LOCAL (SQLite) ---
def obtener_conexion():
    conn = sqlite3.connect("tickets.db")
    conn.create_function("SIN_ACENTOS", 1, quitar_acentos)
    return conn

def init_db():
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comercio TEXT,
            fecha TEXT,
            total REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER,
            codigo_barras TEXT,
            nombre TEXT,
            precio_bruto REAL,
            cantidad REAL,
            descuento REAL,
            precio_neto REAL,
            FOREIGN KEY (compra_id) REFERENCES compras (id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("PRAGMA table_info(productos)")
    columnas_existentes = [col[1] for col in cursor.fetchall()]
    
    nuevas_columnas = {
        "codigo_barras": "TEXT",
        "precio_bruto": "REAL",
        "cantidad": "REAL",
        "descuento": "REAL",
        "precio_neto": "REAL"
    }
    
    for col_nombre, col_tipo in nuevas_columnas.items():
        if col_nombre not in columnas_existentes:
            try:
                cursor.execute(f"ALTER TABLE productos ADD COLUMN {col_nombre} {col_tipo}")
            except sqlite3.OperationalError:
                pass

    cursor.execute("""
        DELETE FROM compras 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM compras 
            GROUP BY LOWER(TRIM(comercio)), DATE(fecha), ROUND(total, 2)
        )
    """)
    cursor.execute("""
        DELETE FROM productos 
        WHERE compra_id NOT IN (SELECT id FROM compras)
    """)

    conn.commit()
    conn.close()

def existe_ticket_duplicado(comercio, fecha_hora, total):
    conn = obtener_conexion()
    cursor = conn.cursor()
    solo_fecha = formatear_solo_fecha(fecha_hora)
    cursor.execute("""
        SELECT id FROM compras 
        WHERE LOWER(TRIM(comercio)) = LOWER(TRIM(?)) 
          AND (fecha = ? OR DATE(fecha) = DATE(?)) 
          AND ROUND(total, 2) = ROUND(?, 2)
    """, (comercio, fecha_hora, solo_fecha, total))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

def guardar_ticket_completo(comercio, fecha_hora, total, lista_productos):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO compras (comercio, fecha, total) VALUES (?, ?, ?)", (comercio, fecha_hora, total))
    compra_id = cursor.lastrowid

    for prod in lista_productos:
        cursor.execute("""
            INSERT INTO productos (compra_id, codigo_barras, nombre, precio_bruto, cantidad, descuento, precio_neto)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            compra_id,
            prod.get("codigo_barras", ""),
            prod.get("nombre", ""),
            prod.get("precio_bruto", 0.0),
            prod.get("cantidad", 1.0),
            prod.get("descuento", 0.0),
            prod.get("precio_neto", 0.0)
        ))
    conn.commit()
    conn.close()
    return compra_id

def buscar_ultimo_precio_producto(query):
    query_limpia = quitar_acentos(query)
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.nombre, p.codigo_barras, p.precio_neto, c.fecha, c.comercio, p.precio_bruto, p.descuento
        FROM productos p
        JOIN compras c ON p.compra_id = c.id
        WHERE SIN_ACENTOS(p.nombre) LIKE ? OR SIN_ACENTOS(p.codigo_barras) LIKE ?
        ORDER BY c.fecha DESC
        LIMIT 1
    """, (f"%{query_limpia}%", f"%{query_limpia}%"))
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def obtener_historial_producto(nombre_producto):
    nombre_limpio = quitar_acentos(nombre_producto)
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.fecha, c.comercio, p.precio_bruto, p.cantidad, p.descuento, p.precio_neto
        FROM productos p
        JOIN compras c ON p.compra_id = c.id
        WHERE SIN_ACENTOS(p.nombre) = ?
        ORDER BY c.fecha DESC
    """, (nombre_limpio,))
    filas = cursor.fetchall()
    conn.close()
    return filas

def obtener_comercios_registrados():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT comercio FROM compras ORDER BY comercio ASC")
    filas = cursor.fetchall()
    conn.close()
    return [f[0] for f in filas if f[0]]

def obtener_tabla_historial_completo(filtro_comercio=None):
    conn = obtener_conexion()
    cursor = conn.cursor()
    query = """
        SELECT c.fecha, c.comercio, p.nombre, p.precio_bruto, p.cantidad, p.descuento, p.precio_neto
        FROM productos p
        JOIN compras c ON p.compra_id = c.id
    """
    if filtro_comercio and filtro_comercio != "Todos":
        query += " WHERE c.comercio = ? ORDER BY c.fecha DESC, p.id ASC"
        cursor.execute(query, (filtro_comercio,))
    else:
        query += " ORDER BY c.fecha DESC, p.id ASC"
        cursor.execute(query)
    filas = cursor.fetchall()
    conn.close()
    return filas

def procesar_imagen_capturada(nombre_archivo):
    fecha_ticket = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "comercio": f"Comercio detectado ({nombre_archivo[:10]})",
        "fecha": fecha_ticket,
        "total": 14250.00,
        "productos": [
            {"codigo_barras": "7790001001234", "nombre": "Leche Entera 1L", "precio_bruto": 1200.00, "cantidad": 2, "descuento": 200.00, "precio_neto": 1000.00},
            {"codigo_barras": "7791234567890", "nombre": "Café Molido 250g", "precio_bruto": 4500.00, "cantidad": 1, "descuento": 500.00, "precio_neto": 4000.00},
            {"codigo_barras": "7799876543210", "nombre": "Galletitas Dulces", "precio_bruto": 1850.00, "cantidad": 3, "descuento": 300.00, "precio_neto": 1550.00}
        ]
    }

# --- 3. INTERFAZ GRÁFICA MÓVIL ESTABLE ---
def main(page: ft.Page):
    page.title = "Control de Tickets"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 12
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.scroll = ft.ScrollMode.AUTO

    init_db()

    ticket_pendiente = {"datos": None}

    texto_estado = ft.Text("Toca el botón para tomar la foto del ticket", color=ft.Colors.GREY, size=12)
    contenedor_resumen = ft.Column()
    mensaje_alerta = ft.Column()
    contenedor_historial = ft.Column()

    def cerrar_dialogo(e):
        if page.dialog:
            page.dialog.open = False
            page.update()

    def abrir_historial_producto_modal(nombre_producto):
        registros = obtener_historial_producto(nombre_producto)
        filas_modal = []
        for reg in registros:
            fecha_str, comercio, p_bruto, cant, desc, p_neto = reg
            desc_txt = f"-{formatear_moneda(desc)}" if desc and desc > 0 else "$ 0,00"
            desc_col = ft.Colors.RED_600 if desc and desc > 0 else ft.Colors.GREY
            
            filas_modal.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(formatear_solo_fecha(fecha_str), size=11)),
                    ft.DataCell(ft.Text(comercio, size=11)),
                    ft.DataCell(ft.Text(formatear_moneda(p_bruto), size=11)),
                    ft.DataCell(ft.Text(formatear_cantidad(cant), size=11)),
                    ft.DataCell(ft.Text(desc_txt, color=desc_col, size=11)),
                    ft.DataCell(ft.Text(formatear_moneda(p_neto), weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700, size=11)),
                ])
            )

        tabla_modal = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Fecha", size=11)),
                ft.DataColumn(ft.Text("Comercio", size=11)),
                ft.DataColumn(ft.Text("P. Bruto", size=11)),
                ft.DataColumn(ft.Text("Cant.", size=11)),
                ft.DataColumn(ft.Text("Descuento", size=11)),
                ft.DataColumn(ft.Text("P. Neto", size=11)),
            ],
            rows=filas_modal
        )

        dialogo = ft.AlertDialog(
            title=ft.Text(f"Historial: {nombre_producto}", weight=ft.FontWeight.BOLD, size=14),
            content=ft.Container(
                content=ft.Row([tabla_modal], scroll=ft.ScrollMode.AUTO),
                width=320,
                height=260
            ),
            actions=[ft.TextButton("Cerrar", on_click=cerrar_dialogo)]
        )

        page.dialog = dialogo
        dialogo.open = True
        page.update()

    # BUSCADOR ADAPTATIVO
    input_busqueda_prod = ft.TextField(
        label="Buscar producto...",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        height=45,
        text_size=13
    )

    card_resultado = ft.Column()

    def realizar_busqueda(e):
        card_resultado.controls.clear()
        query = input_busqueda_prod.value.strip() if input_busqueda_prod.value else ""

        if not query:
            page.update()
            return

        resultado = buscar_ultimo_precio_producto(query)

        if resultado:
            nombre, codigo, precio_neto, fecha, comercio, precio_bruto, descuento = resultado
            p_bruto_val = precio_bruto if precio_bruto is not None else 0.0
            desc_val = descuento if descuento is not None else 0.0
            p_neto_val = precio_neto if precio_neto is not None else 0.0

            card_resultado.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.SHOPPING_BAG, color=ft.Colors.GREEN_600, size=24),
                            title=ft.Text(f"{nombre}", weight=ft.FontWeight.BOLD, size=14),
                            subtitle=ft.Text(f"Lugar: {comercio} | Fecha: {formatear_solo_fecha(fecha)}", size=11),
                            trailing=ft.Text(formatear_moneda(p_neto_val), weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.GREEN_700),
                            on_click=lambda _, n=nombre: abrir_historial_producto_modal(n)
                        )
                    ]),
                    border=ft.Border.all(1, ft.Colors.GREEN_300),
                    bgcolor=ft.Colors.GREEN_50,
                    border_radius=8,
                    padding=4
                )
            )
        else:
            card_resultado.controls.append(
                ft.Container(
                    content=ft.Text("No se encontró ningún producto.", color=ft.Colors.RED_600, italic=True, size=12),
                    padding=4
                )
            )
        page.update()

    btn_buscar = ft.IconButton(
        icon=ft.Icons.SEARCH,
        icon_color=ft.Colors.BLUE_700,
        on_click=realizar_busqueda
    )

    input_busqueda_prod.on_submit = realizar_busqueda

    seccion_buscador = ft.Column([
        ft.Divider(height=10),
        ft.Text("2. Consultar Último Precio", size=15, weight=ft.FontWeight.BOLD),
        ft.Row([input_busqueda_prod, btn_buscar], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        card_resultado
    ])

    dropdown_comercios = ft.Dropdown(
        label="Filtrar por comercio",
        expand=True,
        text_size=13
    )

    def cargar_vista_historial(e=None):
        comercio_sel = dropdown_comercios.value
        registros = obtener_tabla_historial_completo(comercio_sel)
        contenedor_historial.controls.clear()
        
        if not registros:
            contenedor_historial.controls.append(
                ft.Text("No hay productos registrados.", color=ft.Colors.GREY_700, italic=True, size=12)
            )
        else:
            filas_tabla = []
            for reg in registros:
                fecha, comercio, nombre, p_bruto, cant, desc, p_neto = reg
                desc_txt = f"-{formatear_moneda(desc)}" if desc and desc > 0 else "$ 0,00"
                desc_col = ft.Colors.RED_600 if desc and desc > 0 else ft.Colors.GREY

                def crear_handler_modal(prod_nombre):
                    return lambda _: abrir_historial_producto_modal(prod_nombre)

                btn_accion_historial = ft.IconButton(
                    icon=ft.Icons.ANALYTICS_OUTLINED,
                    icon_color=ft.Colors.BLUE_700,
                    tooltip="Ver historial",
                    on_click=crear_handler_modal(nombre)
                )

                filas_tabla.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(formatear_solo_fecha(fecha), size=10)),
                            ft.DataCell(ft.Text(comercio, size=10)),
                            ft.DataCell(ft.Text(nombre, weight=ft.FontWeight.BOLD, size=10)),
                            ft.DataCell(ft.Text(formatear_moneda(p_bruto), size=10)),
                            ft.DataCell(ft.Text(formatear_cantidad(cant), size=10)),
                            ft.DataCell(ft.Text(desc_txt, color=desc_col, size=10)),
                            ft.DataCell(ft.Text(formatear_moneda(p_neto), weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700, size=10)),
                            ft.DataCell(btn_accion_historial)
                        ]
                    )
                )

            tabla_historial = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Fecha", size=10)),
                    ft.DataColumn(ft.Text("Comercio", size=10)),
                    ft.DataColumn(ft.Text("Producto", size=10)),
                    ft.DataColumn(ft.Text("P. Bruto", size=10)),
                    ft.DataColumn(ft.Text("Cant.", size=10)),
                    ft.DataColumn(ft.Text("Descuento", size=10)),
                    ft.DataColumn(ft.Text("P. Neto", size=10)),
                    ft.DataColumn(ft.Text("Hist.", size=10)),
                ],
                rows=filas_tabla,
            )
            contenedor_historial.controls.append(ft.Row([tabla_historial], scroll=ft.ScrollMode.AUTO))
        page.update()

    dropdown_comercios.on_change = cargar_vista_historial

    def ocultar_historial(e):
        seccion_historial_panel.visible = False
        seccion_carrusel_inicio.visible = True
        seccion_buscador.visible = True
        seccion_historial_inicio.visible = True
        page.update()

    seccion_historial_panel = ft.Column([
        ft.Divider(height=10),
        ft.Row([
            ft.Text("Historial Completo", size=15, weight=ft.FontWeight.BOLD),
            ft.TextButton("Volver", icon=ft.Icons.ARROW_BACK, on_click=ocultar_historial)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        dropdown_comercios,
        contenedor_historial
    ], visible=False)

    def mostrar_historial(e):
        comercios = obtener_comercios_registrados()
        dropdown_comercios.options = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(c) for c in comercios]
        dropdown_comercios.value = "Todos"
        limpiar_vista_previa()
        seccion_carrusel_inicio.visible = True
        seccion_buscador.visible = False
        seccion_historial_inicio.visible = False
        seccion_historial_panel.visible = True
        cargar_vista_historial()

    btn_ver_historial = ft.Button(
        "Ver historial de compras",
        icon=ft.Icons.HISTORY,
        on_click=mostrar_historial
    )

    seccion_historial_inicio = ft.Column([
        ft.Divider(height=10),
        ft.Text("3. Historial de Compras", size=15, weight=ft.FontWeight.BOLD),
        btn_ver_historial
    ])

    def limpiar_vista_previa():
        ticket_pendiente["datos"] = None
        texto_estado.value = "Toca el botón para tomar la foto del ticket"
        texto_estado.color = ft.Colors.GREY
        contenedor_resumen.controls.clear()
        mensaje_alerta.controls.clear()
        seccion_carrusel_inicio.visible = True
        seccion_buscador.visible = True
        seccion_historial_inicio.visible = True
        seccion_historial_panel.visible = False
        page.update()

    def cancelar_registro(e):
        limpiar_vista_previa()
        page.snack_bar = ft.SnackBar(ft.Text("Procesamiento cancelado"), bgcolor=ft.Colors.GREY_800)
        page.snack_bar.open = True
        page.update()

    def confirmar_guardado(e):
        datos = ticket_pendiente.get("datos")
        if not datos:
            return

        if existe_ticket_duplicado(datos["comercio"], datos["fecha"], datos["total"]):
            mensaje_alerta.controls.clear()
            mensaje_alerta.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.RED_700, size=20),
                        ft.Text("¡Atención! Este ticket ya está registrado.", color=ft.Colors.RED_800, weight=ft.FontWeight.BOLD, size=11)
                    ]),
                    bgcolor=ft.Colors.RED_100,
                    border=ft.Border.all(1, ft.Colors.RED_400),
                    border_radius=8,
                    padding=6
                )
            )
            page.update()
            return

        guardar_ticket_completo(datos["comercio"], datos["fecha"], datos["total"], datos["productos"])
        limpiar_vista_previa()
        page.snack_bar = ft.SnackBar(content=ft.Text("¡Ticket registrado correctamente!", weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.GREEN_700)
        page.snack_bar.open = True
        page.update()

    # --- SEECTOR MULTIMEDIA NATIVO PARA CÁMARA ---
    def on_picker_result(e: ft.FilePickerResultEvent):
        if e.files:
            archivo = e.files[0]
            nombre_archivo = archivo.name
            texto_estado.value = f"Foto capturada: {nombre_archivo}"
            texto_estado.color = ft.Colors.GREEN_700
            mensaje_alerta.controls.clear()

            seccion_buscador.visible = False
            seccion_historial_inicio.visible = False
            seccion_historial_panel.visible = False

            datos = procesar_imagen_capturada(nombre_archivo)
            ticket_pendiente["datos"] = datos

            filas_tabla = []
            for p in datos["productos"]:
                desc_texto = f"-{formatear_moneda(p['descuento'])}" if p['descuento'] > 0 else "$ 0,00"
                desc_col = ft.Colors.RED_600 if p['descuento'] > 0 else ft.Colors.GREY

                filas_tabla.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(p["nombre"], weight=ft.FontWeight.BOLD, size=11)),
                            ft.DataCell(ft.Text(formatear_moneda(p['precio_bruto']), size=11)),
                            ft.DataCell(ft.Text(formatear_cantidad(p['cantidad']), size=11)),
                            ft.DataCell(ft.Text(desc_texto, color=desc_col, size=11)),
                            ft.DataCell(ft.Text(formatear_moneda(p['precio_neto']), weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700, size=11)),
                        ]
                    )
                )

            tabla_productos = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Producto", size=11)),
                    ft.DataColumn(ft.Text("P. Bruto", size=11)),
                    ft.DataColumn(ft.Text("Cant.", size=11)),
                    ft.DataColumn(ft.Text("Descuento", size=11)),
                    ft.DataColumn(ft.Text("P. Neto", size=11)),
                ],
                rows=filas_tabla,
            )

            btn_guardar_bd = ft.Button("Guardar", icon=ft.Icons.SAVE, on_click=confirmar_guardado)
            btn_cancelar_bd = ft.Button("Cancelar", icon=ft.Icons.CANCEL, on_click=cancelar_registro)

            contenedor_resumen.controls.clear()
            contenedor_resumen.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.RECEIPT_LONG, color=ft.Colors.BLUE_700, size=22),
                            ft.Text("Vista Previa del Ticket", size=15, weight=ft.FontWeight.BOLD)
                        ]),
                        ft.Divider(),
                        ft.Row([
                            ft.Text(f"Comercio: {datos['comercio']}", weight=ft.FontWeight.BOLD, size=12),
                            ft.Text(f"Fecha: {formatear_solo_fecha(datos['fecha'])}", color=ft.Colors.GREY_700, size=11),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(f"Total: {formatear_moneda(datos['total'])}", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                        ft.Divider(),
                        ft.Text("Detalle:", weight=ft.FontWeight.BOLD, size=12),
                        ft.Row([tabla_productos], scroll=ft.ScrollMode.AUTO),
                        mensaje_alerta,
                        ft.Divider(),
                        ft.Row([btn_guardar_bd, btn_cancelar_bd], alignment=ft.MainAxisAlignment.END, spacing=5)
                    ]),
                    border=ft.Border.all(1, ft.Colors.BLUE_200),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=8,
                    padding=8
                )
            )
            page.update()

    # Añadimos el selector multimedia estándar y seguro de Flet
    file_picker = ft.FilePicker(on_result=on_picker_result)
    page.overlay.append(file_picker)

    btn_abrir_camara = ft.Button(
        "Tomar foto del ticket",
        icon=ft.Icons.CAMERA_ALT,
        on_click=lambda _: file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
    )

    seccion_carrusel_inicio = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("1. Escanear / Cargar Ticket", size=15, weight=ft.FontWeight.BOLD),
                btn_abrir_camara,
                texto_estado,
                contenedor_resumen
            ]),
            padding=10
        )
    )

    page.add(
        ft.Text("Digitalizador de Tickets", size=18, weight=ft.FontWeight.BOLD),
        seccion_carrusel_inicio,
        seccion_buscador,
        seccion_historial_inicio,
        seccion_historial_panel
    )

if __name__ == "__main__":
    ft.run(main)
