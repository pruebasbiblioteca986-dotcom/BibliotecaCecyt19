import pymongo

# Configuración de la conexión a MongoDB
# Asegúrate de reemplazar la URL de conexión con la tuya
# Si te conectas localmente, generalmente es mongodb://localhost:27017/
mongo_url = "mongodb://localhost:27017/" 
db_name = "Inventario"
collection_name = "Inventario"

def agregar_registro():
    """
    Función para agregar un nuevo registro a la colección de MongoDB.
    """
    try:
        # Establecer la conexión con el servidor de MongoDB
        cliente = pymongo.MongoClient(mongo_url)
        print("✅ Conexión a MongoDB exitosa.")

        # Seleccionar la base de datos y la colección
        db = cliente[db_name]
        coleccion = db[collection_name]

        # Solicitar datos al usuario
        # Usa un bucle para asegurarte de que el usuario introduzca un número
        while True:
            try:
                numero_inventario = int(input("Introduce el número de inventario: "))
                break  # Sale del bucle si la entrada es un número válido
            except ValueError:
                print("⚠️ ¡Error! Por favor, introduce un número válido para el inventario.")

        nombre_completo = input("Introduce el nombre completo del artículo: ")

        # Crear el documento (diccionario) con los datos a insertar
        # Los campos que indicaste en la solicitud son "No" y "Nombre completo"
        documento = {
            "No": numero_inventario,
            "Nombre completo": nombre_completo
        }

        # Insertar el documento en la colección
        resultado = coleccion.insert_one(documento)
        print(f"✔️ Registro agregado con éxito. ID del nuevo documento: {resultado.inserted_id}")

    except pymongo.errors.ConnectionFailure as e:
        # Manejo de errores si la conexión falla
        print(f"❌ Error de conexión a MongoDB: {e}")

    finally:
        # Asegurarse de cerrar la conexión
        if 'cliente' in locals() and cliente:
            cliente.close()
            print("👋 Conexión a MongoDB cerrada.")

if __name__ == "__main__":
    agregar_registro()