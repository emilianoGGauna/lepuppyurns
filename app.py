from flask import Flask, request, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from tempfile import NamedTemporaryFile
from functools import wraps
from flask import session, redirect, url_for, flash
import os
import logging
from pymongo import MongoClient
from dotenv import load_dotenv
from PasswordManager import PasswordManager
import hashlib
from datetime import datetime
import urllib.parse
import pandas as pd
import random
import string
import base64
from jinja2 import TemplateNotFound
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, PatternFill
# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

# Cargar variables de entorno desde .env
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
APP_KEY = os.getenv("APP_KEY")

if not MONGO_URI:
    logger.error("La variable MONGO_URI no está configurada en el archivo .env")
    raise ValueError("La variable MONGO_URI no está configurada en el archivo .env")

# Configuración de Flask
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = APP_KEY

# Conexión a la base de datos MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client["lepuppy"]
    usuarios_collection = db["usuarios"]
    catalogo_collection = db["catalogo"]
    logger.info("Conexión a la base de datos establecida correctamente.")
except Exception as e:
    logger.error(f"Error al conectar con la base de datos MongoDB: {e}")
    raise

# Instanciar PasswordManager
password_manager = PasswordManager()

# Middleware para verificar roles
def role_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_role" not in session or session["user_role"] != role:
                flash("Acceso denegado.")
                return redirect(url_for("login"))
            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Por favor, complete todos los campos.")
            return redirect(url_for("login"))

        try:
            contraseña_encriptada_ingresada = password_manager.encrypt_password(password)
            usuario = usuarios_collection.find_one({
                "email": email,
                "contraseña": contraseña_encriptada_ingresada
            })
        except Exception as e:
            flash("Error al conectar con la base de datos.")
            logger.error(f"Error: {e}")
            return redirect(url_for("login"))

        if usuario:
            session["user_role"] = usuario.get("access")
            session["user_name"] = usuario.get("client_name", "Usuario")
            session["user_id"] = str(usuario["_id"])  # Asegúrate de convertir el ID a string
            if usuario["access"] == "admin":
                return redirect(url_for("adminplatform"))
            elif usuario["access"] == "cliente":
                return redirect(url_for("clientecatalogo"))
        else:
            flash("Usuario o contraseña incorrectos.")
            return redirect(url_for("login"))
    return render_template("login.html")
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
## CLient PLATFORM
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@app.route("/clientecatalogo")
def clientecatalogo():
    try:
        catalogos = list(catalogo_collection.find({}, {"_id": 0, "Tipo de Modelo": 1, "img": 1, "model-uuid": 1}))
        logger.info(f"Catálogo cargado correctamente")
        return render_template("cliente/clientecatalogo.html", catalogos=catalogos)
    except Exception as e:
        flash(f"Error al cargar el catálogo.")
        logger.error(f"Error al cargar el catálogo: {e}")
        return redirect(url_for("login"))


@app.route("/clienteforms/<model_uuid>", methods=["GET", "POST"])
def clienteforms(model_uuid):
    if request.method == "GET":
        try:
            logger.info(f"Buscando modelo con UUID: {model_uuid}")
            
            # Buscar modelo en la base de datos
            model = catalogo_collection.find_one({"model-uuid": model_uuid}, {"_id": 0})
            
            if model:
                logger.info(f"Modelo encontrado: {model.get('Tipo de Modelo', 'Desconocido')}")

                # Validar si el modelo tiene 'Forms' y manejar el caso de que falte 'Tipo Urna'
                forms = model.get("Forms", {})
                if not isinstance(forms, dict):
                    logger.warning(f"'Forms' no es válido para el modelo con UUID: {model_uuid}")
                    model["Forms"] = {}

                if "Tipo Urna" not in model["Forms"]:
                    logger.warning(f"'Tipo Urna' no encontrado en el modelo con UUID: {model_uuid}")
                    model["Forms"]["Tipo Urna"] = {}  # Valor por defecto vacío

                return render_template("cliente/clienteforms.html", model=model)

            else:
                flash("Modelo no encontrado.")
                logger.warning(f"Modelo no encontrado para UUID: {model_uuid}")
                return redirect(url_for("clientecatalogo"))

        except Exception as e:
            flash("Error al cargar el formulario. Intente nuevamente.")
            logger.error(f"Error al cargar el formulario para UUID {model_uuid}: {e}")
            return redirect(url_for("clientecatalogo"))

@app.route("/add_to_cart/<model_uuid>", methods=["POST"])
def add_to_cart(model_uuid):
    if "user_id" not in session:  # Cambia a verificar el ID del cliente
        flash("Por favor, inicie sesión para añadir al carrito.")
        return redirect(url_for("login"))

    try:
        # Obtener datos del formulario
        cantidad = request.form.get("cantidad", type=int)
        client_id = session.get("user_id")  # Recuperar el ID del cliente desde la sesión
        model = catalogo_collection.find_one({"model-uuid": model_uuid}, {"_id": 0})
        forms_data = {key: value for key, value in request.form.items() if key != "cantidad"}

        if not model:
            flash("Modelo no encontrado.")
            return redirect(url_for("clientecatalogo"))

        # Crear un identificador único para la combinación de opciones
        forms_hash = hashlib.sha256(str(forms_data).encode()).hexdigest()

        # Crear/Actualizar el carrito en MongoDB
        carrito_collection = db["carrito"]
        carrito_collection.update_one(
            {"client_id": client_id, "model_uuid": model_uuid, "forms_hash": forms_hash},
            {"$set": {
                "model": model,
                "client_id": client_id,
                "model_uuid": model_uuid,
                "cantidad": cantidad,
                "forms_data": forms_data,
                "forms_hash": forms_hash  # Almacenar el hash en la BD
            }},
            upsert=True
        )
        flash("Producto añadido al carrito.")
        return redirect(url_for("clientecatalogo"))
    except Exception as e:
        logger.error(f"Error al añadir al carrito: {e}")
        flash("Ocurrió un error al añadir al carrito.")
        return redirect(url_for("clientecatalogo"))


@app.route("/clientecarrito")
def clientecarrito():
    if "user_id" not in session:  # Asegurarse de que el usuario esté autenticado
        flash("Por favor, inicie sesión para ver su carrito.")
        return redirect(url_for("login"))

    try:
        # Recuperar el ID del cliente desde la sesión
        client_id = session.get("user_id")
        
        # Consultar los objetos del carrito de este cliente
        carrito_collection = db["carrito"]
        carrito_items = list(carrito_collection.find({"client_id": client_id}, {"_id": 0}))

        if not carrito_items:
            flash("Su carrito está vacío.")
            return render_template("cliente/clientecarrito.html", carrito=[])

        # Renderizar la plantilla del carrito
        return render_template("cliente/clientecarrito.html", carrito=carrito_items)
    except Exception as e:
        logger.error(f"Error al cargar el carrito: {e}")
        flash("Ocurrió un error al cargar su carrito.")
        return redirect(url_for("clientecatalogo"))
    
@app.route("/update_cart", methods=["POST"])
def update_cart():
    if "user_id" not in session:
        flash("Por favor, inicie sesión para editar su carrito.")
        return redirect(url_for("login"))

    try:
        client_id = session.get("user_id")
        model_uuid = request.form.get("model_uuid")
        forms_hash = request.form.get("forms_hash")  # Recuperar el hash único
        new_quantity = int(request.form.get("cantidad"))

        carrito_collection = db["carrito"]
        carrito_collection.update_one(
            {"client_id": client_id, "model_uuid": model_uuid, "forms_hash": forms_hash},
            {"$set": {"cantidad": new_quantity}}
        )
        flash("Cantidad actualizada exitosamente.")
    except Exception as e:
        logger.error(f"Error al actualizar el carrito: {e}")
        flash("Ocurrió un error al actualizar su carrito.")

    return redirect(url_for("clientecarrito"))

@app.route("/delete_from_cart", methods=["POST"])
def delete_from_cart():
    if "user_id" not in session:
        flash("Por favor, inicie sesión para editar su carrito.")
        return redirect(url_for("login"))

    try:
        client_id = session.get("user_id")
        model_uuid = request.form.get("model_uuid")

        # Debug log to ensure correct model_uuid is received
        logger.info(f"Attempting to delete item with model_uuid: {model_uuid} for client_id: {client_id}")

        # Ensure model_uuid exists in the form
        if not model_uuid:
            flash("Error: Producto no encontrado.")
            return redirect(url_for("clientecarrito"))

        carrito_collection = db["carrito"]
        result = carrito_collection.delete_one({"client_id": client_id, "model_uuid": model_uuid})

        if result.deleted_count > 0:
            flash("Producto eliminado del carrito.")
        else:
            flash("El producto no pudo ser eliminado. Verifique nuevamente.")
    except Exception as e:
        logger.error(f"Error al eliminar producto del carrito: {e}")
        flash("Ocurrió un error al eliminar el producto.")

    return redirect(url_for("clientecarrito"))


from bson import ObjectId  # Importar para manejar ObjectId en MongoDB

@app.route("/finalizar-compra", methods=["POST"])
def finalizar_compra():
    if "user_id" not in session:
        flash("Por favor, inicie sesión para completar su compra.")
        return redirect(url_for("login"))

    try:
        client_id = session.get("user_id")
        carrito_collection = db["carrito"]
        pedidos_collection = db["pedidos"]
        usuarios_collection = db["usuarios"]
        catalogo_collection = db["catalogo"]

        # Verificar si la colección 'pedidos' existe, si no, crearla
        if "pedidos" not in db.list_collection_names():
            pedidos_collection = db.create_collection("pedidos")
            logger.info("La colección 'pedidos' no existía y ha sido creada.")

        # Fetch the cart for the user
        orden = list(carrito_collection.find({"client_id": client_id}))

        if not orden:
            flash("No hay productos en tu carrito.")
            return redirect(url_for("clientecarrito"))

        # Convertir client_id a ObjectId
        try:
            client_object_id = ObjectId(client_id)
        except Exception as e:
            logger.error(f"Error al convertir client_id a ObjectId: {e}")
            flash("Error interno. Contacta al soporte.")
            return redirect(url_for("clientecarrito"))

        # Fetch user details
        cliente_info = usuarios_collection.find_one({"_id": client_object_id})
        if not cliente_info:
            logger.error(f"No se encontró un usuario con ID: {client_id}")
            flash("Error al procesar tu información de cliente.")
            return redirect(url_for("clientecarrito"))

        client_name = cliente_info.get("client_name", "Cliente Desconocido")

        # Prepare the order
        time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        orden_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        pedidos = []
        for item in orden:
            # Get the model name from the catalog
            model_uuid = item["model_uuid"]
            modelo = catalogo_collection.find_one({"model-uuid": model_uuid})
            nombre_modelo = modelo.get("Tipo de Modelo", "Modelo Desconocido") if modelo else "Modelo Desconocido"

            pedidos.append({
                "model_uuid": model_uuid,
                "modelo": nombre_modelo,
                "cantidad": item["cantidad"],
                "atributos": item["forms_data"]
            })

        # Create the order
        order_data = {
            "orden-id": orden_id,
            "cliente-id": client_id,
            "cliente-nombre": client_name,
            "time-stamp": time_stamp,
            "Estado": "En proceso",
            "pedidos": pedidos
        }

        # Insert order into pedidos collection
        pedidos_collection.insert_one(order_data)

        # Clear the cart
        carrito_collection.delete_many({"client_id": client_id})

        # Prepare WhatsApp message
        mensaje = (
            f"Hola, soy {client_name}.\n"
            f"Orden ID: {orden_id}\n"
            f"Fecha de compra: {time_stamp}\n"
            f"He realizado {len(pedidos)} pedido(s):\n\n"
        )
        for i, pedido in enumerate(pedidos, start=1):
            atributos = '\n'.join([f"{k}: {v}" for k, v in pedido['atributos'].items()])
            mensaje += (f"Pedido {i}:\n"
                        f"- Modelo: {pedido['modelo']}\n"
                        f"- Cantidad: {pedido['cantidad']}\n"
                        f"- Atributos:\n{atributos}\n\n")

        mensaje_codificado = urllib.parse.quote(mensaje)
        whatsapp_link = f"https://api.whatsapp.com/send?phone=3326374701&text={mensaje_codificado}"

        return redirect(whatsapp_link)

    except Exception as e:
        logger.error(f"Error al finalizar la compra: {e}")
        flash("Ocurrió un error al finalizar tu compra.")
        return redirect(url_for("clientecarrito"))


##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
## ADMIN PLATFORM
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

def generate_page_one(ws, pedido):
    """Genera la primera página del pedido con estilo mejorado."""
    # Estilo para el encabezado
    bold_font = Font(bold=True, size=14, color="FFFFFF")
    header_fill = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    center_alignment = Alignment(horizontal="center", vertical="center")

    # Agregar encabezado general
    ws.merge_cells("A1:F1")
    ws["A1"] = "Resumen del Pedido"
    ws["A1"].font = Font(bold=True, size=18)
    ws["A1"].alignment = center_alignment
    ws["A1"].fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")

    # Calcular la cantidad total y el número de modelos
    total_cantidad = sum(item["cantidad"] for item in pedido["pedidos"])
    total_modelos = len(pedido["pedidos"])

    # Información principal del pedido
    info_pedido = [
        ["Orden ID", pedido.get("orden-id", "-")],
        ["Cliente Nombre", pedido.get("cliente-nombre", "-")],
        ["Fecha", pedido.get("time-stamp", "-")],
        ["Cantidad Total", total_cantidad],
        ["Número de Modelos", total_modelos]
    ]

    row = 2  # Comenzar en la fila 2
    for key, value in info_pedido:
        ws[f"A{row}"] = key
        ws[f"A{row}"].font = Font(bold=True)
        ws[f"B{row}"] = value
        row += 1

    # Espaciado entre secciones
    row += 1

    # Crear conjunto único de todos los atributos dinámicos en los modelos
    all_attributes = set()
    for item in pedido["pedidos"]:
        all_attributes.update(item.get("atributos", {}).keys())

    # Encabezados para la tabla
    headers = ["Modelo", "Cantidad"] + sorted(all_attributes)  # Ordenar atributos alfabéticamente
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col)
        cell.value = header
        cell.font = bold_font
        cell.fill = header_fill
        cell.alignment = center_alignment

    # Agregar filas con datos de los modelos en el pedido
    row += 1
    for item in pedido["pedidos"]:
        data_row = [
            item.get("modelo", "-"),
            item.get("cantidad", 0),
        ]
        # Agregar valores de atributos dinámicos en el orden de los encabezados
        for attr in sorted(all_attributes):
            data_row.append(item.get("atributos", {}).get(attr, "-"))
        for col, value in enumerate(data_row, start=1):
            cell = ws.cell(row=row, column=col)
            cell.value = value
        row += 1

    # Ajustar ancho de columnas automáticamente
    for col_num, column_cells in enumerate(ws.iter_cols(min_row=1, max_row=row, min_col=1, max_col=len(headers)), start=1):
        max_length = max((len(str(cell.value)) for cell in column_cells if cell.value), default=10)
        ws.column_dimensions[get_column_letter(col_num)].width = max_length + 2

def generate_page_two(wb, pedido, catalogo_collection):
    """Genera la segunda página con información detallada de Corte Láser."""
    bold_font = Font(bold=True, size=14, color="FFFFFF")
    header_fill = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    center_alignment = Alignment(horizontal="center", vertical="center")

    # Crear hoja 'Corte Láser'
    ws_laser = wb.create_sheet(title="Corte Láser")

    # Normalizar claves (unificar nombres de atributos similares)
    def normalize_key(key):
        return key.strip().lower().replace(" ", "_")

    # Recopilar todos los atributos posibles de los cortes láser y atributos del formulario
    all_attributes = set()
    for item in pedido["pedidos"]:
        modelo = item.get("modelo", "-")
        catalogo_item = catalogo_collection.find_one({"Tipo de Modelo": modelo})
        if catalogo_item and isinstance(catalogo_item.get("corte_lazer"), dict):
            all_attributes.update(normalize_key(k) for k in catalogo_item["corte_lazer"].keys())
        if isinstance(item.get("atributos"), dict):
            all_attributes.update(normalize_key(k) for k, v in item["atributos"].items() if k.lower() != "color")

    # Excluir columnas específicas
    excluded_columns = {"modelo", "color"}
    all_attributes = [attr for attr in sorted(all_attributes) if attr not in excluded_columns]

    # Asegurar que solo se incluya "tipo-urna"
    all_attributes = [attr for attr in all_attributes if attr != "tipo_urna"] + ["tipo-urna"]

    # Crear encabezados dinámicos
    headers_laser = ["Cantidad"] + all_attributes
    for col, header in enumerate(headers_laser, start=1):
        cell = ws_laser.cell(row=1, column=col)
        cell.value = header
        cell.font = bold_font
        cell.fill = header_fill
        cell.alignment = center_alignment

    # Agregar filas con los datos
    row_num = 2
    for item in pedido["pedidos"]:
        cantidad = item.get("cantidad", 0)

        # Buscar en el catálogo usando Tipo de Modelo
        modelo = item.get("modelo", "-")
        catalogo_item = catalogo_collection.find_one({"Tipo de Modelo": modelo})
        corte_lazer = {normalize_key(k): v for k, v in catalogo_item.get("corte_lazer", {}).items()} if catalogo_item else {}
        atributos_form = {normalize_key(k): v for k, v in item.get("atributos", {}).items() if k.lower() != "color"}

        # Construir la fila con los datos
        data_row = [cantidad]  # Inicia con la cantidad
        for attr in all_attributes:
            value = atributos_form.get(attr, corte_lazer.get(attr, "-"))
            data_row.append(value)

        # Escribir la fila en la hoja
        for col, value in enumerate(data_row, start=1):
            cell = ws_laser.cell(row=row_num, column=col)
            cell.value = value

        row_num += 1

    # Eliminar columnas con valores nulos
    for col in range(len(headers_laser), 0, -1):
        if all(
            ws_laser.cell(row=row, column=col).value in [None, "-", ""] for row in range(2, row_num)
        ):
            ws_laser.delete_cols(col)

    # Combinar filas duplicadas (excepto la columna "Cantidad")
    row_data = []
    for row in ws_laser.iter_rows(min_row=2, max_row=row_num - 1, min_col=1, max_col=len(headers_laser)):
        row_values = [cell.value for cell in row]
        row_data.append(row_values)

    unique_rows = {}
    for row in row_data:
        key = tuple(row[1:])  # Excluir la cantidad para crear la clave
        cantidad = int(row[0]) if isinstance(row[0], int) else 0
        if key in unique_rows:
            unique_rows[key] += cantidad
        else:
            unique_rows[key] = cantidad

    # Escribir filas únicas de vuelta
    ws_laser.delete_rows(2, ws_laser.max_row)
    row_num = 2
    for key, cantidad in unique_rows.items():
        data_row = [cantidad] + list(key)
        for col, value in enumerate(data_row, start=1):
            cell = ws_laser.cell(row=row_num, column=col)
            cell.value = value
        row_num += 1

    # Ajustar ancho de columnas automáticamente
    for col_num, column_cells in enumerate(ws_laser.iter_cols(min_row=1, max_row=row_num - 1, min_col=1, max_col=len(headers_laser)), start=1):
        max_length = max((len(str(cell.value)) for cell in column_cells if cell.value), default=10)
        ws_laser.column_dimensions[get_column_letter(col_num)].width = max_length + 2

    # Eliminar encabezados duplicados
    seen_headers = set()
    duplicate_columns = []
    for col in range(1, len(headers_laser) + 1):
        header_value = ws_laser.cell(row=1, column=col).value
        if header_value in seen_headers:
            duplicate_columns.append(col)
        else:
            seen_headers.add(header_value)

    # Eliminar columnas duplicadas
    for col in reversed(duplicate_columns):
        ws_laser.delete_cols(col)
    
    # Diccionario de mapeo para cambiar nombres de columnas
    column_mapping = {
        "¿quieres_el_logo_de_tu_empresa?": "logo_grabado",
        "tipo-urna": "tipo-madera"
    }

    # Cambiar los nombres de las columnas basados en el mapeo
    for col in range(1, ws_laser.max_column + 1):
        cell_value = ws_laser.cell(row=1, column=col).value
        if cell_value in column_mapping:
            ws_laser.cell(row=1, column=col).value = column_mapping[cell_value]
    # Ajustar ancho de columnas automáticamente y permitir salto de línea
    for col_num, column_cells in enumerate(
        ws_laser.iter_cols(min_row=1, max_row=row_num - 1, min_col=1, max_col=ws_laser.max_column), start=1
    ):
        max_length = max((len(str(cell.value)) for cell in column_cells if cell.value), default=10)
        column_letter = get_column_letter(col_num)
        ws_laser.column_dimensions[column_letter].width = max_length + 2

        # Estilo para cada celda de la columna
        for cell in column_cells:
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Ajustar el alto de las filas automáticamente
    for row in ws_laser.iter_rows(min_row=1, max_row=row_num - 1, min_col=1, max_col=ws_laser.max_column):
        for cell in row:
            if cell.value:
                ws_laser.row_dimensions[cell.row].height = 15  # Ajusta la altura según sea necesario
@app.route("/export_pedido/<orden_id>", methods=["GET"])
def export_pedido(orden_id):
    try:
        pedidos_collection = db["pedidos"]
        catalogo_collection = db["catalogo"]
        pedido = pedidos_collection.find_one({"orden-id": orden_id})

        if not pedido:
            flash("Pedido no encontrado.")
            return redirect(url_for("adminplatform"))

        # Crear un nuevo archivo Excel con openpyxl
        wb = Workbook()
        ws = wb.active
        ws.title = "Resumen del Pedido"

        # Generar página 1
        generate_page_one(ws, pedido)

        # Generar página 2
        generate_page_two(wb, pedido, catalogo_collection)

        # Guardar el archivo temporalmente
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            wb.save(temp_file.name)
            temp_file_path = temp_file.name

        # Descargar el archivo
        response = send_file(
            temp_file_path,
            as_attachment=True,
            download_name=f"pedido_{orden_id}.xlsx"
        )
        response.call_on_close(lambda: os.unlink(temp_file_path))  # Eliminar archivo al terminar
        return response

    except Exception as e:
        logger.error(f"Error al exportar pedido {orden_id}: {e}")
        flash("Ocurrió un error al exportar el pedido.")
        return redirect(url_for("adminplatform"))


@app.route("/test_pedidos", methods=["GET"])
def test_pedidos():
    pedidos_collection = db["pedidos"]
    pedidos = list(pedidos_collection.find({}))
    return jsonify(pedidos)  # Devuelve los datos en formato JSON para verificar

@app.route("/adminplatform", methods=["GET"])
def adminplatform():
    try:
        # Acceder a la colección de pedidos
        pedidos_collection = db["pedidos"]
        pedidos = list(pedidos_collection.find({}))  # Obtener todos los pedidos

        # Preparar datos para mostrar una sola fila por Orden ID
        pedidos_resumidos = []
        for pedido in pedidos:
            total_cantidad = sum(item["cantidad"] for item in pedido["pedidos"])  # Sumar todas las cantidades
            total_pedidos = len(pedido["pedidos"])  # Contar el total de pedidos en la orden
            pedidos_resumidos.append({
                "Orden ID": pedido.get("orden-id", "-"),
                "Cliente Nombre": pedido.get("cliente-nombre", "-"),
                "Fecha": pedido.get("time-stamp", "-"),
                "Cantidad Total": total_cantidad,
                "Total Pedidos": total_pedidos,
                "Estado": pedido.get("Estado", "-")
            })

        # Renderizar la tabla con pedidos resumidos
        return render_template("admin/adminplatform.html", pedidos=pedidos_resumidos)

    except Exception as e:
        logger.error(f"Error en adminplatform: {e}")
        flash("Ocurrió un error al cargar los pedidos.")
        return redirect(url_for("login"))

@app.route("/adminusuarios")
def adminusuarios():
    try:
        # Fetch all user data, including client_id
        usuarios = list(
            usuarios_collection.find({}, {"_id": 0, "email": 1, "client_name": 1, "access": 1, "client_id": 1})
        )
        logger.info("Usuarios cargados correctamente.")
        return render_template("admin/adminusuarios.html", usuarios=usuarios)
    except Exception as e:
        flash("Error al cargar los usuarios.")
        logger.error(f"Error al cargar los usuarios: {e}")
        return redirect(url_for("login"))


@app.route("/adduser", methods=["POST"])
def adduser():
    try:
        # Extract form data
        client_name = request.form.get("client_name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        access = request.form.get("access")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Validate passwords
        if password != confirm_password:
            flash("Las contraseñas no coinciden.")
            logger.warning("Intento fallido de creación de usuario: las contraseñas no coinciden.")
            return redirect(url_for("adminusuarios"))

        # Encrypt password
        encrypted_password = password_manager.encrypt_password(password)

        # Create user data
        user_data = {
            "client_name": client_name,
            "phone": phone,
            "email": email,
            "access": access,
            "contraseña": encrypted_password,
        }

        # Generate client_id as MD5 hash of user data
        user_json_string = f"{client_name}{phone}{email}{access}".encode("utf-8")
        client_id = hashlib.md5(user_json_string).hexdigest()
        user_data["client_id"] = client_id

        # Insert into MongoDB
        usuarios_collection.insert_one(user_data)
        flash("Usuario añadido exitosamente.")
        logger.info(f"Usuario añadido: {email}, client_id: {client_id}")

        return redirect(url_for("adminusuarios"))
    except Exception as e:
        flash("Error al añadir usuario.")
        logger.error(f"Error al añadir usuario: {e}")
        return redirect(url_for("adminusuarios"))


@app.route("/deleteuser", methods=["POST"])
def deleteuser():
    try:
        # Get client_id from form data
        client_id = request.form.get("client_id")
        logger.info(f"Received client_id for deletion: {client_id}")
        if not client_id:
            flash("ID del cliente no proporcionado.")
            logger.warning("Intento de eliminación fallido: client_id no proporcionado.")
            return redirect(url_for("adminusuarios"))

        # Attempt to delete the user
        result = usuarios_collection.delete_one({"client_id": client_id})
        if result.deleted_count > 0:
            flash("Usuario eliminado exitosamente.")
            logger.info(f"Usuario eliminado con client_id: {client_id}")
        else:
            flash("Usuario no encontrado.")
            logger.warning(f"No se encontró el usuario con client_id: {client_id}")

        return redirect(url_for("adminusuarios"))
    except Exception as e:
        flash("Error al eliminar el usuario.")
        logger.error(f"Error al eliminar usuario: {e}")
        return redirect(url_for("adminusuarios"))


@app.route("/admincatalogo")
def admincatalogo():
    try:
        catalogos = list(catalogo_collection.find({}, {"_id": 0, "Tipo de Modelo": 1, "img": 1, "model-uuid": 1}))
        logger.info("Catálogo cargado correctamente.")
        return render_template("admin/admincatalogo.html", catalogos=catalogos)
    except Exception as e:
        flash(f"Error al cargar el catálogo.")
        logger.error(f"Error al cargar el catálogo: {e}")
        return redirect(url_for("login"))

# Generar cadena aleatoria de 20 caracteres
def generate_random_string(length=20):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))

@app.route("/add_catalog_item", methods=["POST"])
def add_catalog_item():
    tipo_modelo = request.form["tipo_modelo"]
    description_models_file = request.files["description_models"]
    modelos_file = request.files["modelos"]

    # Convertir imágenes a Base64
    description_models_base64 = base64.b64encode(description_models_file.read()).decode("utf-8")
    modelos_base64 = base64.b64encode(modelos_file.read()).decode("utf-8")

    model_uuid = generate_random_string()

    # Recopilar atributos únicos de Forms y corte_lazer
    existing_items = list(catalogo_collection.find())
    merged_forms = {}
    merged_corte_lazer = {}

    for item in existing_items:
        # Combinar atributos de Forms
        for key, value in item.get("Forms", {}).items():
            if key not in merged_forms:
                merged_forms[key] = value
            else:
                if isinstance(merged_forms[key], list):
                    if isinstance(value, list):
                        merged_forms[key] = list(set(merged_forms[key] + value))
                    else:
                        merged_forms[key] = list(set(merged_forms[key] + [value]))
                elif isinstance(merged_forms[key], str):
                    if isinstance(value, list):
                        merged_forms[key] = list(set([merged_forms[key]] + value))
                    else:
                        merged_forms[key] = list(set([merged_forms[key], value]))

        # Combinar atributos de corte_lazer
        for key, value in item.get("corte_lazer", {}).items():
            if key not in merged_corte_lazer:
                merged_corte_lazer[key] = value
            else:
                if isinstance(merged_corte_lazer[key], list):
                    if isinstance(value, list):
                        merged_corte_lazer[key] = list(set(merged_corte_lazer[key] + value))
                    else:
                        merged_corte_lazer[key] = list(set(merged_corte_lazer[key] + [value]))
                elif isinstance(merged_corte_lazer[key], str):
                    if isinstance(value, list):
                        merged_corte_lazer[key] = list(set([merged_corte_lazer[key]] + value))
                    else:
                        merged_corte_lazer[key] = list(set([merged_corte_lazer[key], value]))

    # Insertar nuevo elemento en la base de datos
    new_item = {
        "model-uuid": model_uuid,
        "Tipo de Modelo": tipo_modelo,
        "Forms": merged_forms,
        "corte_lazer": merged_corte_lazer,
        "img": {
            "description_models": description_models_base64,
            "modelos": modelos_base64,
        },
        "sort_order": catalogo_collection.count_documents({})  # Asigna el orden al final por defecto
    }
    catalogo_collection.insert_one(new_item)
    return redirect("/admincatalogo")

@app.route("/delete_catalog_item/<model_uuid>", methods=["DELETE"])
def delete_catalog_item(model_uuid):
    result = catalogo_collection.delete_one({"model-uuid": model_uuid})
    if result.deleted_count > 0:
        return "Deleted successfully", 200
    else:
        return "Item not found", 404


@app.route("/adminforms/<model_uuid>")
def adminforms(model_uuid):
    try:
        logger.info(f"Buscando modelo con UUID: {model_uuid}")
        model = catalogo_collection.find_one({"model-uuid": model_uuid}, {"_id": 0})
        if model:
            logger.info(f"Modelo encontrado: {model}")
            return render_template("admin/adminforms.html", model=model)
        else:
            flash("Modelo no encontrado.")
            logger.warning(f"Modelo no encontrado para UUID: {model_uuid}")
            return redirect(url_for("admincatalogo"))
    except Exception as e:
        flash("Error al cargar el formulario.")
        logger.error(f"Error al cargar el formulario: {e}")
        return redirect(url_for("admincatalogo"))
    
@app.route("/get_forms/<model_uuid>", methods=["GET"])
def get_forms(model_uuid):
    try:
        model = catalogo_collection.find_one({"model-uuid": model_uuid})
        if not model:
            return jsonify({"error": "Modelo no encontrado"}), 404

        return jsonify(model.get("Forms", {})), 200
    except Exception as e:
        logger.error(f"Error al obtener el JSON para {model_uuid}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


@app.route("/edit_forms/<model_uuid>", methods=["POST"])
def edit_forms(model_uuid):
    try:
        updated_forms = request.json
        if not updated_forms:
            return jsonify({"error": "No se recibieron datos"}), 400

        result = catalogo_collection.update_one(
            {"model-uuid": model_uuid},
            {"$set": {"Forms": updated_forms}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Modelo no encontrado"}), 404

        return jsonify({"message": "Formulario actualizado con éxito"}), 200
    except Exception as e:
        logger.error(f"Error al guardar el JSON para {model_uuid}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/get_corte_lazer/<model_uuid>", methods=["GET"])
def get_corte_lazer(model_uuid):
    """
    Endpoint para obtener el contenido de `corte_lazer` de un modelo específico.
    """
    try:
        model = catalogo_collection.find_one({"model-uuid": model_uuid}, {"_id": 0, "corte_lazer": 1})
        if not model:
            return jsonify({"error": "Modelo no encontrado"}), 404

        corte_lazer = model.get("corte_lazer", {})
        return jsonify(corte_lazer), 200
    except Exception as e:
        logger.error(f"Error al obtener corte_lazer para {model_uuid}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500
    
@app.route("/edit_corte_lazer/<model_uuid>", methods=["POST"])
def edit_corte_lazer(model_uuid):
    """
    Endpoint para actualizar el contenido de `corte_lazer` de un modelo específico.
    """
    try:
        updated_corte_lazer = request.json  # Obtener el JSON enviado en el cuerpo de la solicitud
        if not updated_corte_lazer:
            return jsonify({"error": "No se recibieron datos"}), 400

        # Actualizar el campo `corte_lazer` en la base de datos
        result = catalogo_collection.update_one(
            {"model-uuid": model_uuid},
            {"$set": {"corte_lazer": updated_corte_lazer}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Modelo no encontrado"}), 404

        return jsonify({"message": "Corte Láser actualizado con éxito"}), 200
    except Exception as e:
        logger.error(f"Error al guardar corte_lazer para {model_uuid}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500


if __name__ == "__main__":
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Iniciando servidor en el puerto {port}, modo debug: {debug_mode}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
