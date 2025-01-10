from pymongo import MongoClient
from dotenv import load_dotenv
import os
import random

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Obtener la URI de MongoDB desde las variables de entorno
MONGO_URI = os.getenv('MONGO_URI')

# Conectar al cliente de MongoDB
client = MongoClient(MONGO_URI)

# Seleccionar la base de datos y la colección
db = client['lepuppy']  # Nombre de la base de datos
collection = db['catalogo']  # Nombre de la colección

# Contar cuántos documentos hay en la colección
document_count = collection.count_documents({})

if document_count > 0:
    # Elegir un índice aleatorio
    random_index = random.randint(0, document_count - 1)

    # Obtener un documento aleatorio utilizando skip
    random_document = collection.find().skip(random_index).limit(1)[0]

    # Imprimir los primeros atributos del documento
    print("Primeros atributos del documento aleatorio:")
    for i, (key, value) in enumerate(random_document.items()):
        print(f"{key}: {value}")
        if i == 6:  # Limitar a los primeros 5 atributos
            break
else:
    print("La colección 'catalogo' está vacía.")

# Cerrar la conexión
client.close()
