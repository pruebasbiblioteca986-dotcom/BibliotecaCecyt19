# mi_biblioteca/settings.py

DATABASES = {
    'default': {
        'ENGINE': 'djongo',
        'NAME': 'Inventario', # Reemplaza con el nombre de tu base de datos en MongoDB
        'CLIENT': {
            'host': 'mongodb://localhost:27017/', # URL de tu servidor MongoDB
        }
    }
} 