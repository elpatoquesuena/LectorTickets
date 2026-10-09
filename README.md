# LectorTickets — versión estabilizada

Esta versión corrige los puntos de mayor riesgo del prototipo original:

- SQLite usa almacenamiento persistente privado de Flet.
- Las transacciones de SQLite tienen rollback automático ante errores.
- Se activa `foreign_keys`, `WAL` y `busy_timeout`.
- Se elimina el borrado automático de tickets al iniciar.
- Se evita el falso positivo de duplicados por hora exacta.
- Se agregan validaciones antes de guardar.
- Se manejan errores de cámara, archivos, búsqueda e historial sin cerrar la aplicación.
- La captura ya no inventa datos: guarda la foto y deja claro que falta el OCR.
- Se incorpora `pyproject.toml` para builds reproducibles de Android.

## Importante sobre el OCR

El repositorio original no tenía un OCR real: `procesar_ticket_capturado()` devolvía datos hardcodeados. Esta versión **no conserva ese comportamiento engañoso**.

Para completar LectorTickets como lector automático de tickets hay que conectar un motor OCR compatible con Android (por ejemplo una extensión Flutter/Flet basada en ML Kit). No conviene meter una API key de un servicio externo dentro del APK.

## Desarrollo

```bash
flet run --android
```

## APK

```bash
flet build apk --python-version 3.13
```

El build requiere JDK 17 y Android SDK; Flet puede instalar componentes faltantes durante el primer build.
