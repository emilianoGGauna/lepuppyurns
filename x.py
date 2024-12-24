import os
from pymongo import MongoClient

# Cargar las variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv("C:\\Users\\PC\\OneDrive\\Escritorio\\URNAS\\mongodb\\.env")

# Conexión a MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["lepuppy"]  # Cambia por el nombre de tu base de datos
collection = db["catalogo"]  # Cambia por el nombre de tu colección

# Renombrar el campo "Colores Disponibles" a "Colores"
# Agregar el atributo Figura al mismo nivel que Tipo Urna
def agregar_figura():
    documentos = collection.find({"Tipo de Modelo": "CORAZÓN PORTARRETRATO"})

    for doc in documentos:
        # Verificar si Forms existe y si Figura no está presente
        if "Forms" in doc and "Figura" not in doc["Forms"]:
            # Actualizar el documento agregando Figura al mismo nivel que Tipo Urna
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"Forms.Figura": "Corazón"}}
            )
            print(f"Atributo 'Figura' agregado al documento con _id: {doc['_id']}")
        else:
            print(f"El documento con _id: {doc['_id']} ya tiene el atributo 'Figura' o no tiene 'Forms'.")

# Ejecutar la función
if __name__ == "__main__":
    agregar_figura()
    print("Actualización completada.")