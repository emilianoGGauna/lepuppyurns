from flask import Flask, request, render_template, redirect, url_for, flash
from functools import wraps
from flask import session, redirect, url_for, flash
import os
import logging
from pymongo import MongoClient
from dotenv import load_dotenv
from PasswordManager import PasswordManager
import hashlib

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
        logger.info(f"Catálogo cargado correctamente: {catalogos}")
        return render_template("cliente/clientecatalogo.html", catalogos=catalogos)
    except Exception as e:
        flash(f"Error al cargar el catálogo.")
        logger.error(f"Error al cargar el catálogo: {e}")
        return redirect(url_for("login"))


@app.route("/clienteforms/<model_uuid>")
def clienteforms(model_uuid):
    try:
        logger.info(f"Buscando modelo con UUID: {model_uuid}")
        model = catalogo_collection.find_one({"model-uuid": model_uuid}, {"_id": 0})
        if model:
            logger.info(f"Modelo encontrado: {model['Tipo de Modelo']}")
            return render_template("cliente/clienteforms.html", model=model)
        else:
            flash("Modelo no encontrado.")
            logger.warning(f"Modelo no encontrado para UUID: {model_uuid}")
            return redirect(url_for("clientecatalogo"))
    except Exception as e:
        flash(f"Error al cargar el formulario.")
        logger.error(f"Error al cargar el formulario: {e}")
        return redirect(url_for("clientecatalogo"))

##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
## ADMIN PLATFORM
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
##------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route("/adminplatform")
def adminplatform():
    logger.info("Acceso a la plataforma de administración.")
    return render_template("admin/adminplatform.html")

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
            logger.info(f"Modelo encontrado: {model['Tipo de Modelo']}")
            return render_template("admin/adminforms.html", model=model)
        else:
            flash("Modelo no encontrado.")
            logger.warning(f"Modelo no encontrado para UUID: {model_uuid}")
            return redirect(url_for("admincatalogo"))
    except Exception as e:
        flash(f"Error al cargar el formulario.")
        logger.error(f"Error al cargar el formulario: {e}")
        return redirect(url_for("admincatalogo"))

if __name__ == "__main__":
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Iniciando servidor en el puerto {port}, modo debug: {debug_mode}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
