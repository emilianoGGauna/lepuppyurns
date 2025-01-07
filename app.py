from flask import Flask, request, render_template, redirect, url_for, flash, request, jsonify, send_file
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

        # Crear/Actualizar el carrito en MongoDB
        carrito_collection = db["carrito"]
        carrito_collection.update_one(
            {"client_id": client_id, "model_uuid": model_uuid},
            {"$set": {
                "model": model,
                "client_id": client_id,
                "model_uuid": model_uuid,
                "cantidad": cantidad,
                "forms_data": forms_data
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
        new_quantity = int(request.form.get("cantidad"))

        carrito_collection = db["carrito"]
        carrito_collection.update_one(
            {"client_id": client_id, "model_uuid": model_uuid},
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
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from tempfile import NamedTemporaryFile

@app.route("/export_pedidos", methods=["POST"])
def export_pedidos():
    try:
        pedidos_collection = db["pedidos"]
        pedidos = list(pedidos_collection.find({}))
        pedidos_data = []
        for pedido in pedidos:
            for item in pedido["pedidos"]:
                pedidos_data.append({
                    "Orden ID": pedido.get("orden-id", "N/A"),
                    "Cliente Nombre": pedido.get("cliente-nombre", "N/A"),
                    "Fecha": pedido.get("time-stamp", "N/A"),
                    "Modelo": item.get("modelo", "N/A"),
                    "Cantidad": item.get("cantidad", "N/A"),
                    **item.get("atributos", {})
                })

        df_pedidos = pd.DataFrame(pedidos_data)

        # Usar un archivo temporal para guardar el Excel
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            df_pedidos.to_excel(temp_file.name, index=False)
            temp_file_path = temp_file.name

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name="pedidos_filtrados.xlsx"
        )
    except Exception as e:
        logger.error(f"Error al exportar pedidos: {e}")
        flash("Ocurrió un error al exportar los pedidos.")
        return redirect(url_for("adminplatform"))

@app.route("/test_pedidos", methods=["GET"])
def test_pedidos():
    pedidos_collection = db["pedidos"]
    pedidos = list(pedidos_collection.find({}))
    return jsonify(pedidos)  # Devuelve los datos en formato JSON para verificar


@app.route("/adminplatform", methods=["GET", "POST"])
def adminplatform():
    try:
        # Access the "pedidos" collection in the database
        pedidos_collection = db["pedidos"]
        pedidos = list(pedidos_collection.find({}))  # Retrieve all orders

        # Transform orders into a DataFrame for easier processing
        pedidos_data = []
        for pedido in pedidos:
            for item in pedido["pedidos"]:
                pedidos_data.append({
                    "Orden ID": pedido.get("orden-id", "N/A"),
                    "Cliente Nombre": pedido.get("cliente-nombre", "N/A"),
                    "Fecha": pedido.get("time-stamp", "N/A"),
                    "Modelo": item.get("modelo", "N/A"),
                    "Cantidad": item.get("cantidad", "N/A"),
                    **item.get("atributos", {})  # Include dynamic attributes as columns
                })

        # Create a pandas DataFrame
        df_pedidos = pd.DataFrame(pedidos_data)

        if request.method == "POST":
            # Save DataFrame to Excel
            excel_path = os.path.join(os.getcwd(), "pedidos_filtrados.xlsx")
            df_pedidos.to_excel(excel_path, index=False)

            # Send the file to the client as an attachment
            return send_file(excel_path, as_attachment=True, download_name="pedidos_filtrados.xlsx")

        # Render the orders in the HTML template
        return render_template("admin/adminplatform.html", pedidos=df_pedidos.to_dict(orient="records"))
    
    except Exception as e:
        logger.error(f"Error in adminplatform: {e}")
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


if __name__ == "__main__":
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Iniciando servidor en el puerto {port}, modo debug: {debug_mode}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
