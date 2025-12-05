#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspección rápida de la BD: cuenta y muestra ejemplos de documentos relevantes"""
from pymongo import MongoClient
from pprint import pprint

client = MongoClient('mongodb://localhost:27017/')
db = client['Biblioteca']

collections = ['Alumnos','alumnos','Docentes','docentes','Prestamos','prestamos','Sitio','sitio']

print('Conexión a MongoDB OK')
for col in collections:
    if col in db.list_collection_names():
        c = db[col]
        count = c.count_documents({})
        print(f"\nColección: {col} - {count} documentos")
        sample = c.find_one({})
        print('Ejemplo (primer documento):')
        pprint(sample)
    else:
        print(f"\nColección: {col} - NO existe")

# Mostrar últimos 5 prestamos del mes actual
print('\nÚltimos 5 préstamos (por created_at desc):')
prestamo_col = None
for name in ('Prestamos','prestamos'):
    if name in db.list_collection_names():
        prestamo_col = db[name]
        break

if prestamo_col:
    docs = list(prestamo_col.find({}, sort=[('created_at', -1)]).limit(5))
    for d in docs:
        pprint(d)
else:
    print('No se encontró colección de prestamos')

# Mostrar últimos 5 registros en Sitio
print('\nÚltimos 5 registros en Sitio:')
sitio_col = None
for name in ('Sitio','sitio'):
    if name in db.list_collection_names():
        sitio_col = db[name]
        break

if sitio_col:
    docs = list(sitio_col.find({}, sort=[('fecha_completa', -1)]).limit(5))
    for d in docs:
        pprint(d)
else:
    print('No se encontró colección Sitio')

client.close()
print('\nInspección finalizada')
