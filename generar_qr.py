# -*- coding: utf-8 -*-
"""
generar_qr.py
=============
Crea la imagen "instructivo_app.png" con el codigo QR de la app y los pasos
para agregarla a la pantalla de inicio del celular. Se manda por WhatsApp.

Ejecutar:  python generar_qr.py https://asistencia-donmanuel.streamlit.app
"""

import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

URL = sys.argv[1] if len(sys.argv) > 1 else "https://asistencia-donmanuel.streamlit.app"
SALIDA = Path(__file__).resolve().parent / "instructivo_app.png"

ANCHO, ALTO = 1080, 1500
FONDO = "#ffffff"
TINTA = "#0f172a"
ACENTO = "#2563eb"
GRIS = "#475569"


def fuente(tam, negrita=False):
    for nombre in (["segoeuib.ttf", "arialbd.ttf"] if negrita else ["segoeui.ttf", "arial.ttf"]):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default()


img = Image.new("RGB", (ANCHO, ALTO), FONDO)
d = ImageDraw.Draw(img)

# Encabezado
d.rectangle([0, 0, ANCHO, 150], fill=ACENTO)
d.text((ANCHO // 2, 55), "Mercados Don Manuel", fill="white", font=fuente(48, True), anchor="mm")
d.text((ANCHO // 2, 108), "App de asistencia — entrada y salida", fill="white", font=fuente(32), anchor="mm")

# QR
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
qr.add_data(URL)
qr.make(fit=True)
qr_img = qr.make_image(fill_color=TINTA, back_color="white").convert("RGB").resize((520, 520))
img.paste(qr_img, ((ANCHO - 520) // 2, 190))
d.text((ANCHO // 2, 740), "Escanea con la cámara del celular", fill=GRIS, font=fuente(30), anchor="mm")
d.text((ANCHO // 2, 785), URL, fill=ACENTO, font=fuente(30, True), anchor="mm")

# Pasos
y = 860
d.text((80, y), "Para que quede como una app en tu celular:", fill=TINTA, font=fuente(34, True))
y += 70
pasos = [
    ("iPhone", ["Abre el enlace en Safari.",
                "Toca el botón Compartir (cuadrado con flecha ↑).",
                "Elige \"Agregar a pantalla de inicio\" → Agregar."]),
    ("Android", ["Abre el enlace en Chrome.",
                 "Toca el menú de tres puntos (arriba a la derecha).",
                 "Elige \"Agregar a pantalla de inicio\" o \"Instalar app\"."]),
]
for titulo, lista in pasos:
    d.text((80, y), titulo, fill=ACENTO, font=fuente(32, True))
    y += 48
    for i, p in enumerate(lista, 1):
        d.text((110, y), f"{i}. {p}", fill=TINTA, font=fuente(28))
        y += 42
    y += 24

d.text((80, y + 10), "Para marcar: elige tu nombre → PIN → Tomar foto → Confirmar.", fill=GRIS, font=fuente(27))
d.text((80, y + 50), "En \"Mi horario de esta semana\" ves tus turnos.", fill=GRIS, font=fuente(27))

img.save(SALIDA)
print(f"Listo: {SALIDA}")
