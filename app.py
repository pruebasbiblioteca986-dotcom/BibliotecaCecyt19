
from flask import Flask, send_file, jsonify, request, render_template_string
from flask_cors import CORS
from pymongo import MongoClient
from unidecode import unidecode
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId
import os
import pandas as pd
from io import BytesIO
import calendar
import pytz
# Importar SendGrid
import sendgrid
from sendgrid.helpers.mail import Mail

# Cargar variables de entorno desde .env
try:
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
except FileNotFoundError:
    print("[ADVERTENCIA] Archivo .env no encontrado. Usando variables de entorno del sistema.")

app = Flask(__name__)
CORS(app)

import os
mongo_url = os.environ.get("MONGODB_URI")
client = MongoClient(mongo_url)
db = client["Biblioteca"]  # O el nombre de tu base
inventario = db["Inventario"]
alumnos = db["Alumnos"]
prestamos = db["Prestamos"]
multas = db["Multas"]  # Colección para multas
devoluciones = db["Devoluciones"]  # Colección para devoluciones
sitio = db["Sitio"]  # Colección para registros de entrada al sitio
ajedrez = db["Ajedrez"]  # Colección para contadores de ajedrez


# Configuración de SendGrid
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'bibliotecacecyt19@ipn.com.mx')
CORREO_PRUEBA = os.getenv('CORREO_PRUEBA', '')  # Si está configurado, redirige todos los correos aquí

def enviar_correo(destinatario, asunto, contenido, es_html=False):
    """
    Envía un correo usando SendGrid.
    destinatario: email destino (str)
    asunto: asunto del correo (str)
    contenido: cuerpo del mensaje (str)
    es_html: si el contenido es HTML (bool)
    """
    if CORREO_PRUEBA:
        destinatario = CORREO_PRUEBA
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    mail = Mail(
        from_email=EMAIL_FROM,
        to_emails=destinatario,
        subject=asunto,
        html_content=contenido if es_html else None,
        plain_text_content=contenido if not es_html else None
    )
    try:
        response = sg.send(mail)
        print(f"[SENDGRID] Correo enviado a {destinatario}. Status: {response.status_code}")
        return True
    except Exception as e:
        print(f"[SENDGRID] Error enviando correo: {e}")
        return False

def obtener_disponibles(doc):
    u = doc.get("U")
    if not isinstance(u, dict):
        print("NO ENCONTRADO DISPONIBLES (U no es dict)")
        return ""
    # Busca la clave 'EXIST' de cualquier forma posible
    exist = None
    for k in u.keys():
        if k.strip().upper() == "EXIST":
            exist = u[k]
            break
    print("EXIST:", exist, type(exist))
    if isinstance(exist, dict):
        print("CLAVES EXIST:", list(exist.keys()))
        print("VALORES EXIST:", list(exist.values()))
        # Busca la clave vacía
        if "" in exist and isinstance(exist[""], int):
            print("ENCONTRADO DISPONIBLES:", exist[""])
            return exist[""]
        # Busca cualquier valor numérico
        for v in exist.values():
            if isinstance(v, int):
                print("ENCONTRADO DISPONIBLES (otro):", v)
                return v
            if isinstance(v, str) and v.isdigit():
                print("ENCONTRADO DISPONIBLES (str):", v)
                return int(v)
    if isinstance(exist, int):
        print("ENCONTRADO DISPONIBLES (directo):", exist)
        return exist
    if isinstance(exist, str) and exist.isdigit():
        print("ENCONTRADO DISPONIBLES (directo str):", exist)
        return int(exist)
    print("NO ENCONTRADO DISPONIBLES")
    return ""

@app.route('/api/inventario', methods=['GET'])
def api_inventario():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    titulo = request.args.get('titulo', '').strip()
    autor = request.args.get('autor', '').strip()
    editorial = request.args.get('editorial', '').strip()
    edicion_q = request.args.get('edicion', '').strip()
    estante = request.args.get('estante', '').strip()

    and_clauses = []
    def or_fields(name_variants, value):
        return [{f: {"$regex": value, "$options": "i"}} for f in name_variants]

    if titulo:
        and_clauses.append({"$or": or_fields(["TÍTULO","Titulo","TITULO","titulo"], titulo)})
    if autor:
        and_clauses.append({"$or": or_fields(["AUTOR","Autor","autor"], autor)})
    if editorial:
        and_clauses.append({"$or": or_fields(["EDITORIAL","Editorial","editorial"], editorial)})
    if edicion_q:
        and_clauses.append({"$or": or_fields(["EDICIÓN","Edicion","EDICION","edicion"], edicion_q)})
    if estante:
        and_clauses.append({"$or": or_fields(["ESTANTE","Estante","estante"], estante)})

    query = {"$and": and_clauses} if and_clauses else {}

    # helper: busca campo por varias variantes, normalizando claves (quita acentos/espacios) y buscando en subdocumentos
    def find_field(document, candidates):
        if not isinstance(document, dict):
            return ''
        # búsqueda directa por nombres exactos
        for c in candidates:
            if c in document and document[c] not in (None, ''):
                return document[c]
        # búsqueda por normalización de claves
        for k, v in document.items():
            kn = unidecode(str(k)).upper().replace(" ", "")
            for c in candidates:
                cn = unidecode(str(c)).upper().replace(" ", "")
                if kn == cn or cn in kn or kn in cn:
                    if v not in (None, ''):
                        return v
        # buscar recursivamente en subdocumentos
        for v in document.values():
            if isinstance(v, dict):
                r = find_field(v, candidates)
                if r not in (None, ''):
                    return r
        return ''

    skip = (page - 1) * page_size
    cursor = inventario.find(query, {"_id": 0}).skip(skip).limit(page_size)

    items = []
    for doc in cursor:
        # EDICIÓN: buscar muchas variantes y en subobjetos
        ed = find_field(doc, ["EDICIÓN","EDICION","Edicion","edicion","Edición"])
        if isinstance(ed, dict):
            ed = ed.get("valor") or ed.get("value") or ed.get("") or ''
        ed = str(ed) if ed not in (None, '') else ''

        # DISPONIBLES: buscar variantes y fallback a obtener_disponibles
        disp = find_field(doc, ["DISPONIBLES","Disponibles","disponible","DISPONIBLE"])
        if disp in (None, ''):
            disp = obtener_disponibles(doc)
        try:
            disp = int(disp)
        except Exception:
            disp = 0

        items.append({
            "ISBN": find_field(doc, ["ISBN","Isbn","isbn"]) or '',
            "Titulo": find_field(doc, ["TÍTULO","TITULO","Titulo","titulo"]) or '',
            "Autor": find_field(doc, ["AUTOR","Autor","autor"]) or '',
            "Editorial": find_field(doc, ["EDITORIAL","Editorial","editorial"]) or '',
            "Edicion": ed or '-',
            "Estante": find_field(doc, ["ESTANTE","Estante","estante"]) or '',
            "Disponibles": disp
        })

    total = inventario.count_documents(query)
    return jsonify({"inventario": items, "total": total, "page": page, "page_size": page_size})

@app.route('/api/docentes')
def get_docentes():
    data = []
    for doc in db["Docentes"].find({}, {"_id": 0}):
        data.append({
            "Nombre": doc.get("Nombre Completo", ""),
            "NoEmpleado": doc.get("No Empleado", ""),
            "Correo": doc.get("Correo", ""),
            "Turno": doc.get("Turno", ""),
            "Ocupacion": doc.get("Ocupación \n(Docente u otro)", "")
        })
    return jsonify(data)

@app.route('/api/buscar_alumno')
def buscar_alumno():
    """Busca un alumno específico por boleta"""
    boleta = request.args.get('boleta', '').strip()
    if not boleta:
        return jsonify({"encontrado": False, "error": "Boleta requerida"}), 400
    
    # Buscar en múltiples formatos de boleta (string y número)
    or_clauses = [
        {"Boleta": boleta},
        {"boleta": boleta}
    ]
    
    # Si la boleta es numérica, también buscar como número
    if boleta.isdigit():
        try:
            boleta_int = int(boleta)
            or_clauses.append({"Boleta": boleta_int})
            or_clauses.append({"boleta": boleta_int})
        except Exception:
            pass
    
    query = {"$or": or_clauses}
    
    doc = alumnos.find_one(query, {"_id": 0})
    if not doc:
        return jsonify({"encontrado": False})
    
    def pick(doc, keys):
        for k in keys:
            if k in doc and doc[k] not in (None, ''):
                return doc[k]
        return ''
    
    return jsonify({
        "encontrado": True,
        "Nombre": pick(doc, ["Nombre","nombre","Nombre Del Alumno:\n(Completo)"]),
        "Boleta": pick(doc, ["Boleta","boleta"]),
        "Correo": pick(doc, ["Correo","correo","Email","email"]),
        "Grupo": pick(doc, ["Grupo","grupo"]),
        "Carga": pick(doc, ["Carga","carga","Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)"])
    })

@app.route('/api/buscar_docente')
def buscar_docente():
    """Busca un docente específico por número de empleado"""
    no_empleado = request.args.get('no_empleado', '').strip()
    if not no_empleado:
        return jsonify({"encontrado": False, "error": "Número de empleado requerido"}), 400
    
    # Buscar en múltiples formatos de número de empleado
    or_clauses = [
        {"No Empleado": no_empleado},
        {"NoEmpleado": no_empleado},
        {"no_empleado": no_empleado},
        {"noEmpleado": no_empleado}
    ]
    
    # Si el número de empleado es numérico, también buscar como número
    if no_empleado.isdigit():
        try:
            no_empleado_int = int(no_empleado)
            or_clauses.append({"No Empleado": no_empleado_int})
            or_clauses.append({"NoEmpleado": no_empleado_int})
        except Exception:
            pass
    
    query = {"$or": or_clauses}
    
    doc = db["Docentes"].find_one(query, {"_id": 0})
    if not doc:
        return jsonify({"encontrado": False})
    
    return jsonify({
        "encontrado": True,
        "Nombre": doc.get("Nombre Completo", "") or doc.get("Nombre", "") or doc.get("nombre", ""),
        "NoEmpleado": doc.get("No Empleado", "") or doc.get("NoEmpleado", "") or doc.get("no_empleado", "") or doc.get("noEmpleado", ""),
        "Correo": doc.get("Correo", "") or doc.get("correo", ""),
        "Turno": doc.get("Turno", "") or doc.get("turno", ""),
        "Ocupacion": doc.get("Ocupación \n(Docente u otro)", "") or doc.get("Ocupacion", "") or doc.get("ocupacion", "") or doc.get("Cargo", "") or doc.get("cargo", "")
    })

@app.route('/api/alumnos')
def get_alumnos():
    # Recibe el parámetro de página (por defecto 1)
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    page_size = 50
    skip = (page - 1) * page_size

    def pick(doc, keys):
        for k in keys:
            if k in doc and doc[k] not in (None, ''):
                return doc[k]
        return ''

    alumnos_cursor = alumnos.find({}, {"_id": 0}).skip(skip).limit(page_size)
    data = []
    for doc in alumnos_cursor:
        data.append({
            "Nombre": pick(doc, ["Nombre","nombre","Nombre Del Alumno:\n(Completo)"]),
            "Boleta": pick(doc, ["Boleta","boleta"]),
            "Correo": pick(doc, ["Correo","correo","Email","email"]),
            "Grupo": pick(doc, ["Grupo","grupo"]),
            "Carga": pick(doc, ["Carga","carga","Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)"])
        })
    total = alumnos.count_documents({})
    return jsonify({"alumnos": data, "total": total, "page": page, "page_size": page_size})

@app.route('/api/registrar_alumno', methods=['POST'])
def registrar_alumno():
    datos = request.get_json() or {}
    # normalizar a campos canónicos antes de insertar
    doc = {
        "Nombre": datos.get("Nombre") or datos.get("nombre") or datos.get("Nombre Del Alumno:\n(Completo)") or '',
        "Boleta": datos.get("Boleta") or datos.get("boleta") or '',
        "Correo": datos.get("Correo") or datos.get("correo") or '',
        "Grupo": datos.get("Grupo") or datos.get("grupo") or '',
        "Carga": datos.get("Carga") or datos.get("carga") or datos.get("Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)") or ''
    }
    try:
        alumnos.insert_one(doc)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/registrar_docente', methods=['POST'])
def registrar_docente():
    datos = request.get_json() or {}
    # normalizar a campos canónicos antes de insertar
    ocupacion = datos.get("Ocupacion") or datos.get("ocupacion") or datos.get("Cargo") or datos.get("cargo") or 'Docente'
    if not ocupacion or not ocupacion.strip():
        ocupacion = 'Docente'
    
    doc = {
        "Nombre Completo": datos.get("Nombre") or datos.get("nombre") or '',
        "No Empleado": datos.get("No. Empleado") or datos.get("no_empleado") or datos.get("No Empleado") or '',
        "Correo": datos.get("Correo") or datos.get("correo") or '',
        "Turno": datos.get("Turno") or datos.get("turno") or '',
        "Ocupación \n(Docente u otro)": ocupacion
    }
    try:
        db["Docentes"].insert_one(doc)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})




@app.route('/')
def index():
    """Ruta raíz que sirve la interfaz principal"""
    return send_file('Interfaz.html')

@app.route('/api/buscar')
def buscar_json():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"libros": [], "alumnos": []})

    # Normaliza la búsqueda (sin acentos, minúsculas)
    q_norm = unidecode(q).lower()

    # Libros: busca por título, ISBN, autor o editorial (múltiples variantes)
    libros = []
    for doc in inventario.find({}, {"_id": 0}):
        # Buscar en múltiples campos y variantes
        titulo_variantes = [
            doc.get("TÍTULO", ""),
            doc.get("TITULO", ""),
            doc.get("Titulo", ""),
            doc.get("titulo", ""),
            doc.get("Título", ""),
            doc.get("title", "")
        ]
        titulo = ""
        for t in titulo_variantes:
            if t and str(t).strip():
                titulo = str(t)
                break
        
        isbn_variantes = [
            doc.get("ISBN", ""),
            doc.get("Isbn", ""),
            doc.get("isbn", "")
        ]
        isbn = ""
        for i in isbn_variantes:
            if i and str(i).strip():
                isbn = str(i)
                break
        
        autor_variantes = [
            doc.get("AUTOR", ""),
            doc.get("Autor", ""),
            doc.get("autor", "")
        ]
        autor = ""
        for a in autor_variantes:
            if a and str(a).strip():
                autor = str(a)
                break
        
        editorial_variantes = [
            doc.get("EDITORIAL", ""),
            doc.get("Editorial", ""),
            doc.get("editorial", "")
        ]
        editorial = ""
        for e in editorial_variantes:
            if e and str(e).strip():
                editorial = str(e)
                break
        
        titulo_norm = unidecode(titulo).lower()
        isbn_norm = unidecode(isbn).lower()
        autor_norm = unidecode(autor).lower()
        editorial_norm = unidecode(editorial).lower()
        
        if (q_norm in titulo_norm or q_norm in isbn_norm or 
            q_norm in autor_norm or q_norm in editorial_norm):
            libros.append(doc)

    # Alumnos: busca por nombre o boleta (soporta ambos formatos de campo nombre)
    alumnos = []
    for doc in db["Alumnos"].find({}, {"_id": 0}):
        # Buscar nombre en múltiples campos posibles
        nombre_variantes = [
            doc.get("Nombre", ""),
            doc.get("nombre", ""),
            doc.get("Nombre Del Alumno:\n(Completo)", ""),
            doc.get("Nombre Completo", "")
        ]
        nombre = ""
        for n in nombre_variantes:
            if n and str(n).strip():
                nombre = str(n)
                break
        
        nombre_norm = unidecode(nombre).lower()
        boleta = str(doc.get("Boleta", "")).lower()
        if q_norm in nombre_norm or q_norm in boleta:
            alumnos.append(doc)

    return jsonify({"libros": libros, "alumnos": alumnos})

@app.route('/buscar')
def buscar_html_vista():
    q = request.args.get('q', '').strip()
    if not q:
        return send_file('Interfaz.html')

    campo_nombre = "Nombre Del Alumno:\n(Completo)"
    campo_carga = "Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)"
    campo_ocupacion = "Ocupación \n(Docente u otro)"
    q_norm = unidecode(q).lower()

    libros_similares = []
    libros_encontrados = []
    for doc in inventario.find({}, {"_id": 0}):
        # Buscar en múltiples campos y variantes
        titulo_variantes = [
            doc.get("TÍTULO", ""),
            doc.get("TITULO", ""),
            doc.get("Titulo", ""),
            doc.get("titulo", ""),
            doc.get("Título", ""),
            doc.get("title", "")
        ]
        titulo = ""
        for t in titulo_variantes:
            if t and str(t).strip():
                titulo = str(t)
                break
        
        isbn_variantes = [
            doc.get("ISBN", ""),
            doc.get("Isbn", ""),
            doc.get("isbn", "")
        ]
        isbn = ""
        for i in isbn_variantes:
            if i and str(i).strip():
                isbn = str(i)
                break
        
        autor_variantes = [
            doc.get("AUTOR", ""),
            doc.get("Autor", ""),
            doc.get("autor", "")
        ]
        autor = ""
        for a in autor_variantes:
            if a and str(a).strip():
                autor = str(a)
                break
        
        editorial_variantes = [
            doc.get("EDITORIAL", ""),
            doc.get("Editorial", ""),
            doc.get("editorial", "")
        ]
        editorial = ""
        for e in editorial_variantes:
            if e and str(e).strip():
                editorial = str(e)
                break
        
        titulo_norm = unidecode(titulo).lower()
        isbn_norm = unidecode(isbn).lower()
        autor_norm = unidecode(autor).lower()
        editorial_norm = unidecode(editorial).lower()
        
        if (q_norm in titulo_norm or q_norm in isbn_norm or 
            q_norm in autor_norm or q_norm in editorial_norm):
            libros_encontrados.append(doc)
        elif q_norm in titulo_norm:
            libros_similares.append(doc)

    alumnos = []
    for doc in db["Alumnos"].find({}, {"_id": 0}):
        # Buscar nombre en múltiples campos posibles
        nombre_variantes = [
            doc.get("Nombre", ""),
            doc.get("nombre", ""),
            doc.get("Nombre Del Alumno:\n(Completo)", ""),
            doc.get("Nombre Completo", "")
        ]
        nombre = ""
        for n in nombre_variantes:
            if n and str(n).strip():
                nombre = str(n)
                break
        
        nombre_norm = unidecode(nombre).lower()
        boleta = str(doc.get("Boleta", "")).lower()
        if q_norm in nombre_norm or q_norm in boleta:
            alumnos.append(doc)

    docentes = []
    for doc in db["Docentes"].find({}, {"_id": 0}):
        # Buscar nombre en múltiples campos posibles
        nombre_variantes = [
            doc.get("Nombre Completo", ""),
            doc.get("Nombre", ""),
            doc.get("nombre", ""),
            doc.get("Nombre Completo", "")
        ]
        nombre = ""
        for n in nombre_variantes:
            if n and str(n).strip():
                nombre = str(n)
                break
        
        no_empleado_variantes = [
            doc.get("No Empleado", ""),
            doc.get("NoEmpleado", ""),
            doc.get("no_empleado", ""),
            doc.get("noEmpleado", "")
        ]
        no_empleado = ""
        for ne in no_empleado_variantes:
            if ne and str(ne).strip():
                no_empleado = str(ne)
                break
        
        nombre_norm = unidecode(nombre).lower()
        no_empleado_norm = str(no_empleado).lower()
        if q_norm in nombre_norm or q_norm in no_empleado_norm:
            docentes.append(doc)

    html = '''
    <html>
    <head>
        <title>Resultados de búsqueda</title>
        <link rel="stylesheet" href="Interfaz.css">
        <style>
            body { margin:0; padding:0; background:#fff; }
            .institucional-header { width:100%;background:#fff;display:flex;align-items:center;justify-content:space-between;padding:1.2rem 2rem 1.2rem 2rem; }
            .institucional-info { flex:1 1 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#6d1846;text-align:center;font-size:1rem;font-family:'Montserrat',Arial,sans-serif;font-weight:bold; }
            .institucional-divider { width:100%;height:3px;background:#6d1846;margin:0 0 20px 0; }
            .tabla-centro { display: flex; justify-content: center; align-items: center; margin: 40px 0; }
            .tabla-busqueda {
                border-collapse: collapse;
                width: 900px;
                max-width: 900px;
                margin: 0 auto;
                background: #fff;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .tabla-busqueda th, .tabla-busqueda td {
                border: 1px solid #6d1846;
                padding: 10px 16px;
                white-space: nowrap;
                text-align: center;
            }
            .tabla-busqueda th {
                background: #6d1846;
                color: #fff;
                font-weight: bold;
            }
            .tabla-busqueda tr:nth-child(even) { background: #f7f2f7; }
            .tabla-busqueda tr:nth-child(odd) { background: #fff; }
            h4 { color: #6d1846; margin-top: 40px; margin-bottom: 10px; text-align:center;}
            .sin-resultados { color: #6d1846; font-weight: bold; margin: 40px auto; text-align: center; }
            .volver { display:block; margin:30px auto; text-align:center;}
            .volver a { color:#6d1846; font-weight:bold; text-decoration:none; border:1px solid #6d1846; padding:8px 18px; border-radius:6px;}
            .volver a:hover { background:#6d1846; color:#fff;}
        </style>
    </head>
    <body>
        <div class="institucional-header">
            <img src="https://cecyt19.ipn.mx/assets/files/main/img/template/header/pleca-educacion.svg" alt="SEP" style="height:85px;vertical-align:middle;flex:0 0 auto;" />
            <div class="institucional-info">
                <div>Educación</div>
                <div style="font-weight:bold;">Instituto Politécnico Nacional</div>
                <div style="font-style:italic;color:#a67c52;font-weight:normal;">"La Técnica al Servicio de la Patria"</div>
                <div style="color:#222;font-weight:500;">Centro de Estudios Científicos y Tecnológicos 19 "Leona Vicario"</div>
            </div>
            <img src="https://cecyt19.ipn.mx/assets/files/main/img/template/header/logo-ipn-horizontal.svg" alt="IPN" style="height:85px;vertical-align:middle;flex:0 0 auto;" />
        </div>
        <div class="institucional-divider"></div>
        <div style="max-width:1000px;margin:30px auto;">
    '''

    if libros_encontrados:
        html += '''
        <h4>Libros encontrados</h4>
        <div class="tabla-centro">
            <table class="tabla-busqueda">
                <thead>
                    <tr>
                        <th>Título</th>
                        <th>Autor</th>
                        <th>Editorial</th>
                        <th>Estante</th>
                        <th>Disponibles</th>
                    </tr>
                </thead>
                <tbody>
        '''
        for libro in libros_encontrados:
            # Obtener valores desde múltiples variantes de campos
            titulo_libro = (
                libro.get('TÍTULO', '') or 
                libro.get('TITULO', '') or 
                libro.get('Titulo', '') or 
                libro.get('titulo', '') or 
                libro.get('Título', '') or
                libro.get('title', '') or
                ''
            )
            autor_libro = (
                libro.get('AUTOR', '') or 
                libro.get('Autor', '') or 
                libro.get('autor', '') or
                ''
            )
            editorial_libro = (
                libro.get('EDITORIAL', '') or 
                libro.get('Editorial', '') or 
                libro.get('editorial', '') or
                ''
            )
            estante_libro = (
                libro.get('ESTANTE', '') or 
                libro.get('Estante', '') or 
                libro.get('estante', '') or
                ''
            )
            disponibles = obtener_disponibles(libro)
            html += f"<tr><td>{titulo_libro}</td><td>{autor_libro}</td><td>{editorial_libro}</td><td>{estante_libro}</td><td>{disponibles}</td></tr>"
        html += '''
                </tbody>
            </table>
        </div>
        '''

    if alumnos:
        html += '''
        <h4>Alumnos encontrados</h4>
        <div class="tabla-centro">
            <table class="tabla-busqueda">
                <thead>
                    <tr>
                        <th>Nombre</th>
                        <th>Boleta</th>
                        <th>Grupo</th>
                        <th>Carga</th>
                        <th>Acción</th>
                        <th>Observaciones</th>
                    </tr>
                </thead>
                <tbody>
        '''
        for alumno in alumnos:
            # Obtener nombre desde múltiples campos posibles
            nombre_alumno = (
                alumno.get("Nombre", "") or 
                alumno.get("nombre", "") or 
                alumno.get("Nombre Del Alumno:\n(Completo)", "") or
                alumno.get("Nombre Completo", "") or
                ""
            )
            # Obtener carga desde múltiples campos posibles
            carga_alumno = (
                alumno.get("Carga", "") or 
                alumno.get("carga", "") or 
                alumno.get("Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)", "") or
                ""
            )
            
            html += f'''
            <tr>
                <td>{nombre_alumno.upper() if nombre_alumno else ''}</td>
                <td>{alumno.get('Boleta', '')}</td>
                <td>{alumno.get('Grupo', '')}</td>
                <td>{carga_alumno.upper() if carga_alumno else ''}</td>
                <td>
                    <form action="/registrar_entrada" method="post" style="margin:0;">
                        <input type="hidden" name="nombre" value="{nombre_alumno}">
                        <input type="hidden" name="boleta" value="{alumno.get('Boleta', '')}">
                        <input type="hidden" name="grupo" value="{alumno.get('Grupo', '')}">
                        <input type="hidden" name="carga" value="{carga_alumno}">
                        <button type="submit" style="background:#6d1846;color:#fff;border:none;padding:6px 14px;border-radius:5px;font-weight:bold;cursor:pointer;">Registrar entrada</button>
                    </form>
                </td>
                <td>
                    <form action="/registrar_observacion" method="post" style="margin:0;">
                        <input type="hidden" name="tipo" value="alumno">
                        <input type="hidden" name="nombre" value="{nombre_alumno}">
                        <input type="hidden" name="boleta" value="{alumno.get('Boleta', '')}">
                        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;margin-top:12px;">
                            <input type="text" name="observacion" placeholder="Observaciones" style="width:120px;margin-bottom:8px;">
                            <button type="submit" style="background:#6d1846;color:#fff;border:none;padding:6px 18px;border-radius:5px;font-weight:bold;cursor:pointer;">Guardar</button>
                        </div>
                    </form>
                </td>
            </tr>
            '''
        html += '''
                </tbody>
            </table>
        </div>
        '''

    if docentes:
        html += '''
        <h4>Docentes encontrados</h4>
        <div class="tabla-centro">
            <table class="tabla-busqueda">
                <thead>
                    <tr>
                        <th>Nombre</th>
                        <th>No. Empleado</th>
                        <th>Turno</th>
                        <th>Ocupación</th>
                        <th>Acción</th>
                        <th>Observaciones</th>
                    </tr>
                </thead>
                <tbody>
        '''
        for docente in docentes:
            # Obtener valores desde múltiples variantes de campos
            nombre_docente = (
                docente.get('Nombre Completo', '') or 
                docente.get('Nombre', '') or 
                docente.get('nombre', '') or
                ''
            )
            no_empleado_docente = (
                docente.get('No Empleado', '') or 
                docente.get('NoEmpleado', '') or 
                docente.get('no_empleado', '') or
                docente.get('noEmpleado', '') or
                ''
            )
            turno_docente = (
                docente.get('Turno', '') or 
                docente.get('turno', '') or
                ''
            )
            ocupacion_docente = (
                docente.get(campo_ocupacion, '') or 
                docente.get('Ocupacion', '') or 
                docente.get('ocupacion', '') or
                docente.get('Cargo', '') or
                docente.get('cargo', '') or
                ''
            )
            html += (
                f"<tr>"
                f"<td>{nombre_docente.upper() if nombre_docente else ''}</td>"
                f"<td>{no_empleado_docente}</td>"
                f"<td>{turno_docente}</td>"
                f"<td>{ocupacion_docente}</td>"
            )
            html += f'''<td>
                <form action="/registrar_entrada_docente" method="post" style="margin:0;">
                    <input type="hidden" name="nombre" value="{nombre_docente}">
                    <input type="hidden" name="no_empleado" value="{no_empleado_docente}">
                    <input type="hidden" name="turno" value="{turno_docente}">
                    <input type="hidden" name="ocupacion" value="{ocupacion_docente}">
                    <button type="submit" style="background:#6d1846;color:#fff;border:none;padding:6px 14px;border-radius:5px;font-weight:bold;cursor:pointer;">Registrar entrada</button>
                </form>
            </td>
            <td>
                <form action="/registrar_observacion" method="post" style="margin:0;">
                    <input type="hidden" name="tipo" value="docente">
                    <input type="hidden" name="nombre" value="{nombre_docente}">
                    <input type="hidden" name="no_empleado" value="{no_empleado_docente}">
                    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;margin-top:12px;">
                        <input type="text" name="observacion" placeholder="Observaciones" style="width:120px;margin-bottom:8px;">
                        <button type="submit" style="background:#6d1846;color:#fff;border:none;padding:6px 18px;border-radius:5px;font-weight:bold;cursor:pointer;">Guardar</button>
                    </div>
                </form>
            </td></tr>'''
        html += '''
                </tbody>
            </table>
        </div>
        '''

    if not (libros_encontrados or alumnos or docentes):
        html += '<div class="sin-resultados">Sin resultados.</div>'
    html += '</div><div class="volver"><a href="/">Volver al inicio</a></div></body></html>'
    return render_template_string(html)

@app.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    """Registra la entrada de un alumno al sitio"""
    nombre = request.form.get('nombre', '')
    boleta = request.form.get('boleta', '')
    grupo = request.form.get('grupo', '')
    carga = request.form.get('carga', '')
    
    # Determinar turno basado en la carga o grupo
    turno = ''
    if 'MATUTINO' in carga.upper() or 'MAÑANA' in carga.upper():
        turno = 'Matutino'
    elif 'VESPERTINO' in carga.upper() or 'TARDE' in carga.upper():
        turno = 'Vespertino'
    elif 'NOCTURNO' in carga.upper() or 'NOCHE' in carga.upper():
        turno = 'Nocturno'
    else:
        # Intentar determinar por grupo (ej: 5IM03 podría ser matutino)
        turno = 'Matutino'  # Por defecto
    
    # Usar zona horaria de México (América/México_City) en lugar de UTC
    tz_mexico = pytz.timezone('America/Mexico_City')
    fecha = datetime.now(tz_mexico)
    fecha_str = fecha.strftime('%Y-%m-%d')
    hora_entrada = fecha.strftime('%H:%M:%S')
    
    registro = {
        "tipo": "alumno",
        "nombre": nombre,
        "boleta": boleta,
        "turno": turno,
        "grupo": grupo,
        "carga": carga,
        "fecha": fecha_str,
        "fecha_completa": fecha,
        "hora_entrada": hora_entrada,
        "observaciones": [],
        "created_at": fecha,
        "eliminado": False,  # Campo para marcar si está eliminado de la tabla (botón eliminar)
        "reiniciado": False  # Campo para marcar si fue reiniciado (botón reiniciar contador)
    }
    
    sitio.insert_one(registro)
    return render_template_string('''
        <html>
        <head>
            <title>Registro exitoso</title>
            <link rel="stylesheet" href="Interfaz.css">
        </head>
        <body>
            <div style="margin:60px auto;text-align:center;">
                <h2 style="color:#6d1846;">Entrada de alumno registrada correctamente</h2>
                <p style="color:#6d1846;">Fecha: {{ fecha }}<br>Hora de entrada: {{ hora_entrada }}</p>
                <a href="/" style="color:#6d1846;font-weight:bold;text-decoration:none;border:1px solid #6d1846;padding:8px 18px;border-radius:6px;">Volver al inicio</a>
            </div>
        </body>
        </html>
    ''', fecha=fecha_str, hora_entrada=hora_entrada)

@app.route('/registrar_entrada_docente', methods=['POST'])
def registrar_entrada_docente():
    """Registra la entrada de un docente al sitio"""
    nombre = request.form.get('nombre', '')
    no_empleado = request.form.get('no_empleado', '')
    correo = request.form.get('correo', '')
    turno = request.form.get('turno', '')
    ocupacion = request.form.get('ocupacion', '')
    
    # Usar zona horaria de México (América/México_City) en lugar de UTC
    tz_mexico = pytz.timezone('America/Mexico_City')
    fecha = datetime.now(tz_mexico)
    fecha_str = fecha.strftime('%Y-%m-%d')
    hora_entrada = fecha.strftime('%H:%M:%S')
    
    registro = {
        "tipo": "docente",
        "nombre": nombre,
        "no_empleado": no_empleado,
        "correo": correo or '',
        "turno": turno,
        "ocupacion": ocupacion,
        "fecha": fecha_str,
        "fecha_completa": fecha,
        "hora_entrada": hora_entrada,
        "observaciones": [],
        "created_at": fecha,
        "eliminado": False,  # Campo para marcar si está eliminado de la tabla (botón eliminar)
        "reiniciado": False  # Campo para marcar si fue reiniciado (botón reiniciar contador)
    }
    
    sitio.insert_one(registro)
    return render_template_string('''
        <html>
        <head>
            <title>Registro exitoso</title>
            <link rel="stylesheet" href="Interfaz.css">
        </head>
        <body>
            <div style="margin:60px auto;text-align:center;">
                <h2 style="color:#6d1846;">Entrada de docente registrada correctamente</h2>
                <p style="color:#6d1846;">Fecha: {{ fecha }}<br>Hora de entrada: {{ hora_entrada }}</p>
                <a href="/" style="color:#6d1846;font-weight:bold;text-decoration:none;border:1px solid #6d1846;padding:8px 18px;border-radius:6px;">Volver al inicio</a>
            </div>
        </body>
        </html>
    ''', fecha=fecha_str, hora_entrada=hora_entrada)

# Funciones helper para préstamos y devoluciones
def count_business_days_between(start_date, end_date):
    """Calcula días hábiles entre dos fechas (excluyendo sábados y domingos)"""
    if start_date > end_date:
        return 0
    count = 0
    current = start_date
    while current <= end_date:
        # 0 = lunes, 6 = domingo
        if current.weekday() < 5:  # Lunes a viernes
            count += 1
        current += timedelta(days=1)
    return count

def calcular_dias_retraso(fecha_devolucion):
    """Calcula los días de retraso desde la fecha de devolución hasta hoy (solo días hábiles)"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    if fecha_devolucion >= hoy:
        return 0
    return count_business_days_between(fecha_devolucion, hoy)

def calcular_multa(dias_retraso):
    """Calcula el monto de la multa basado en días de retraso"""
    # $5 pesos por día hábil de retraso
    return dias_retraso * 5

def verificar_y_actualizar_prestamos_vencidos():
    """Verifica y actualiza el estado de préstamos vencidos"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    
    # Buscar préstamos activos que hayan vencido
    for prestamo in prestamos.find({"estado": {"$in": ["Activo", None]}}):
        fecha_dev_str = prestamo.get("fecha_devolucion", "")
        if not fecha_dev_str:
            continue
        
        try:
            fecha_dev = datetime.strptime(fecha_dev_str, "%Y-%m-%d").date()
            if fecha_dev < hoy:
                # Actualizar estado a "Vencido"
                prestamos.update_one(
                    {"_id": prestamo["_id"]},
                    {"$set": {"estado": "Vencido"}}
                )
        except Exception:
            continue

@app.route('/api/prestamos', methods=['GET'])
def api_prestamos():
    """Lista todos los préstamos"""
    items = []
    for doc in prestamos.find({}, {"_id": 0}).sort("created_at", -1):
        libro = doc.get("libro", {})
        items.append({
            "tipo": doc.get("tipo", ""),
            "nombre": doc.get("nombre", ""),
            "id": doc.get("id", ""),
            "grupo": doc.get("grupo", ""),
            "correo": doc.get("correo", ""),
            "libro": {
                "titulo": libro.get("titulo", "") or doc.get("titulo", ""),
                "isbn": libro.get("isbn", "") or doc.get("ISBN", "")
            },
            "fecha_inicio": doc.get("fecha_inicio", ""),
            "fecha_devolucion": doc.get("fecha_devolucion", ""),
            "estado": doc.get("estado", "Activo"),
            "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else ""
        })
    return jsonify({"prestamos": items})

@app.route('/api/dashboard')
def get_dashboard():
    import re
    # rango del día de hoy en UTC
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    try:
        prestamos_hoy = prestamos.count_documents({"created_at": {"$gte": start, "$lt": end}})
    except Exception:
        prestamos_hoy = 0

    # helper para extraer primer número entero válido de un valor (string, doc, list, etc.)
    def extract_number(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            try:
                return int(v)
            except:
                return None
        if isinstance(v, str):
            s = re.sub(r'[^0-9]', '', v)
            return int(s) if s else None
        if isinstance(v, dict):
            # intenta claves comunes primero
            for k in ("DISPONIBLES","Disponibles","disponible","DISPONIBLE","Disponible","EXIST"):
                if k in v:
                    n = extract_number(v[k])
                    if n is not None:
                        return n
            # luego recorre valores
            for val in v.values():
                n = extract_number(val)
                if n is not None:
                    return n
        if isinstance(v, (list, tuple)):
            for item in v:
                n = extract_number(item)
                if n is not None:
                    return n
        return None

    # libros en estantería: sumar DISPONIBLES en inventario (con varios fallbacks)
    libros_en_estanteria = 0
    for doc in inventario.find({}):
        val = None
        # 1) claves directas preferidas
        for k in ("DISPONIBLES","Disponibles","disponibles","DISPONIBLE","Disponible"):
            if k in doc and doc.get(k) not in (None, ''):
                val = extract_number(doc.get(k))
                if val is not None:
                    break
        # 2) intentar normalizar otras claves (por si hay variaciones)
        if val is None:
            for k in doc.keys():
                kn = unidecode(str(k)).upper().replace(" ", "")
                if "DISPON" in kn or "EXIST" in kn:
                    val = extract_number(doc.get(k))
                    if val is not None:
                        break
        # 3) fallback a obtener_disponibles que maneja estructura U
        if val is None:
            try:
                od = obtener_disponibles(doc)
                val = extract_number(od)
            except Exception:
                val = None
        if isinstance(val, int) and val > 0:
            libros_en_estanteria += val

    # devoluciones atrasadas
    devoluciones_atrasadas = 0
    try:
        today_date = datetime.now(timezone.utc).date()
        for p in prestamos.find({"estado": {"$in": ["Activo", None]}}):
            fd = p.get("fecha_devolucion") or p.get("fechaDevolucion") or ""
            try:
                fd_dt = datetime.strptime(fd, "%Y-%m-%d").date()
                if fd_dt < today_date:
                    devoluciones_atrasadas += 1
            except Exception:
                continue
    except Exception:
        devoluciones_atrasadas = 0

    nuevos_usuarios = db["Alumnos"].count_documents({})

    return jsonify({
        "prestamos_hoy": prestamos_hoy,
        "libros_estanteria": libros_en_estanteria,
        "devoluciones_atrasadas": devoluciones_atrasadas,
        "nuevos_usuarios": nuevos_usuarios
    })

@app.route('/api/proximas_devoluciones')
def proximas_devoluciones():
    """Devuelve las próximas devoluciones (préstamos activos próximos a vencer)"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    items = []
    
    # Obtener préstamos activos ordenados por fecha de devolución
    for doc in prestamos.find({"estado": "Activo"}, {"_id": 0}).sort("fecha_devolucion", 1).limit(10):
        fecha_dev_str = doc.get("fecha_devolucion", "")
        if not fecha_dev_str:
            continue
        
        try:
            fecha_dev = datetime.strptime(fecha_dev_str, "%Y-%m-%d").date()
            dias_restantes = count_business_days_between(hoy, fecha_dev)
            
            # Solo mostrar los próximos 5 días
            if dias_restantes <= 5:
                libro_titulo = doc.get("libro", {}).get("titulo", "") or doc.get("titulo", "")
                nombre_usuario = doc.get("nombre", "")
                
                # Color según días restantes
                if dias_restantes == 0:
                    color = "#dc3545"  # Rojo - hoy
                elif dias_restantes == 1:
                    color = "#ffc107"  # Amarillo - mañana
                else:
                    color = "#6d1846"  # Vino - normal
                
                items.append({
                    "libro": libro_titulo,
                    "usuario": nombre_usuario,
                    "vencimiento": fecha_dev_str,
                    "dias_restantes": dias_restantes,
                    "color": color
                })
        except Exception:
            continue
    
    return jsonify(items)

@app.route('/api/devoluciones', methods=['GET'])
def api_devoluciones():
    """Lista todas las devoluciones pendientes (préstamos activos y vencidos)"""
    # Verificar y actualizar préstamos vencidos antes de listar
    verificar_y_actualizar_prestamos_vencidos()
    
    items = []
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    
    # Obtener todos los préstamos activos y vencidos (no devueltos)
    for doc in prestamos.find({"estado": {"$ne": "Devuelto"}}, {"_id": 0}).sort("fecha_devolucion", 1):
        fecha_dev_str = doc.get("fecha_devolucion", "")
        estado = doc.get("estado", "")
        
        # Calcular días de retraso si está vencido
        dias_retraso = 0
        if fecha_dev_str:
            try:
                fecha_dev = datetime.strptime(fecha_dev_str, "%Y-%m-%d").date()
                if fecha_dev < hoy:
                    dias_retraso = calcular_dias_retraso(fecha_dev)
                    if estado != "Vencido":
                        estado = "Vencido"
                elif estado != "Vencido":
                    estado = "Activo"
            except Exception:
                estado = estado or "Activo"
        
        libro = doc.get("libro", {})
        items.append({
            "tipo": doc.get("tipo", ""),
            "nombre": doc.get("nombre", ""),
            "id": doc.get("id", ""),
            "grupo": doc.get("grupo", ""),
            "correo": doc.get("correo", ""),
            "libro": {
                "titulo": libro.get("titulo", "") or doc.get("titulo", ""),
                "isbn": libro.get("isbn", "") or doc.get("ISBN", "")
            },
            "fecha_inicio": doc.get("fecha_inicio", ""),
            "fecha_devolucion": fecha_dev_str,
            "estado": estado,
            "dias_retraso": dias_retraso,
            "monto_multa": calcular_multa(dias_retraso) if dias_retraso > 0 else 0
        })
    
    return jsonify({"devoluciones": items})

# ========== RUTAS PARA SITIO (Registro de entrada) ==========
@app.route('/api/sitio', methods=['GET'])
def api_sitio():
    """Lista todos los registros de entrada al sitio"""
    items = []
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    
    for doc in sitio.find({"eliminado": False}, {"_id": 1}).sort("created_at", -1):
        # Convertir _id a string para JSON
        doc_id = str(doc["_id"])
        registro = sitio.find_one({"_id": doc["_id"]}, {"_id": 0})
        if registro:
            registro["id"] = doc_id
            items.append(registro)
    
    return jsonify({"registros": items})

@app.route('/api/sitio/eliminar', methods=['POST'])
def api_sitio_eliminar():
    """Elimina un registro del sitio (marca como eliminado)"""
    datos = request.get_json() or {}
    id_registro = datos.get('id', '')
    if not id_registro:
        return jsonify({'success': False, 'error': 'ID requerido'}), 400
    try:
        result = sitio.update_one(
            {'_id': ObjectId(id_registro)},
            {'$set': {'eliminado': True}}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sitio/reiniciar-contador', methods=['POST'])
def api_sitio_reiniciar_contador():
    """Reinicia el contador de un registro del sitio"""
    datos = request.get_json() or {}
    id_registro = datos.get('id', '')
    if not id_registro:
        return jsonify({'success': False, 'error': 'ID requerido'}), 400
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        fecha_str = fecha.strftime('%Y-%m-%d')
        hora_entrada = fecha.strftime('%H:%M:%S')
        
        result = sitio.update_one(
            {'_id': ObjectId(id_registro)},
            {'$set': {
                'reiniciado': True,
                'fecha': fecha_str,
                'fecha_completa': fecha,
                'hora_entrada': hora_entrada,
                'created_at': fecha
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/registrar_observacion', methods=['POST'])
def registrar_observacion():
    """Agrega una observación a un registro de entrada"""
    tipo = request.form.get('tipo', '')
    nombre = request.form.get('nombre', '')
    boleta = request.form.get('boleta', '')
    no_empleado = request.form.get('no_empleado', '')
    observacion = request.form.get('observacion', '').strip()
    
    if not observacion:
        return jsonify({'success': False, 'error': 'Observación requerida'}), 400
    
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        
        query = {}
        if tipo == 'alumno' and boleta:
            query = {"tipo": "alumno", "boleta": boleta, "eliminado": False}
        elif tipo == 'docente' and no_empleado:
            query = {"tipo": "docente", "no_empleado": no_empleado, "eliminado": False}
        else:
            return jsonify({'success': False, 'error': 'Datos insuficientes'}), 400
        
        # Buscar el registro más reciente
        registro = sitio.find_one(query, sort=[("created_at", -1)])
        if registro:
            sitio.update_one(
                {'_id': registro['_id']},
                {'$push': {'observaciones': {
                    'texto': observacion,
                    'fecha': fecha.strftime('%Y-%m-%d %H:%M:%S')
                }}}
            )
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== RUTAS PARA AJEDREZ ==========
@app.route('/api/ajedrez', methods=['GET'])
def api_ajedrez():
    """Lista todos los registros de ajedrez"""
    items = []
    for doc in ajedrez.find({}, {"_id": 0}).sort("created_at", -1):
        items.append(doc)
    return jsonify({"registros": items})

@app.route('/api/ajedrez/buscar_usuario', methods=['GET'])
def api_ajedrez_buscar_usuario():
    """Busca un usuario en los registros de ajedrez"""
    usuario_id = request.args.get('id', '').strip()
    tipo = request.args.get('tipo', '').strip()
    
    if not usuario_id or not tipo:
        return jsonify({"encontrado": False})
    
    query = {"id_usuario": usuario_id, "tipo": tipo, "estado": "activo"}
    registro = ajedrez.find_one(query, {"_id": 0})
    
    if registro:
        return jsonify({"encontrado": True, "registro": registro})
    else:
        return jsonify({"encontrado": False})

@app.route('/api/ajedrez/iniciar', methods=['POST'])
def api_ajedrez_iniciar():
    """Inicia un juego de ajedrez"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id_usuario', '')
    nombre = datos.get('nombre', '')
    tipo = datos.get('tipo', '')
    
    if not id_usuario or not nombre or not tipo:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        
        registro = {
            "id_usuario": id_usuario,
            "nombre": nombre,
            "tipo": tipo,
            "estado": "activo",
            "inicio": fecha,
            "created_at": fecha
        }
        ajedrez.insert_one(registro)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ajedrez/terminar', methods=['POST'])
def api_ajedrez_terminar():
    """Termina un juego de ajedrez"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id_usuario', '')
    tipo = datos.get('tipo', '')
    
    if not id_usuario or not tipo:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        
        result = ajedrez.update_one(
            {"id_usuario": id_usuario, "tipo": tipo, "estado": "activo"},
            {"$set": {
                "estado": "terminado",
                "fin": fecha,
                "updated_at": fecha
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ajedrez/reiniciar', methods=['POST'])
def api_ajedrez_reiniciar():
    """Reinicia un juego de ajedrez"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id_usuario', '')
    tipo = datos.get('tipo', '')
    
    if not id_usuario or not tipo:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        
        result = ajedrez.update_one(
            {"id_usuario": id_usuario, "tipo": tipo},
            {"$set": {
                "estado": "activo",
                "inicio": fecha,
                "updated_at": fecha
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ajedrez/eliminar', methods=['POST'])
def api_ajedrez_eliminar():
    """Elimina un registro de ajedrez"""
    datos = request.get_json() or {}
    id_registro = datos.get('id', '')
    if not id_registro:
        return jsonify({'success': False, 'error': 'ID requerido'}), 400
    try:
        result = ajedrez.delete_one({'_id': ObjectId(id_registro)})
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== RUTAS PARA MULTAS ==========
@app.route('/api/multas', methods=['GET'])
def api_multas():
    """Lista todas las multas pendientes"""
    items = []
    for doc in multas.find({"pagada": False}, {"_id": 0}).sort("fecha_creacion", -1):
        items.append(doc)
    return jsonify({"multas": items})

@app.route('/api/liberar_multa', methods=['POST'])
def api_liberar_multa():
    """Marca una multa como pagada"""
    datos = request.get_json() or {}
    id_multa = datos.get('id', '')
    if not id_multa:
        return jsonify({'success': False, 'error': 'ID requerido'}), 400
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha = datetime.now(tz_mexico)
        
        result = multas.update_one(
            {'_id': ObjectId(id_multa)},
            {'$set': {
                'pagada': True,
                'fecha_pago': fecha.strftime('%Y-%m-%d')
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Multa no encontrada'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== RUTAS PARA PRÉSTAMOS ==========
@app.route('/api/registrar_prestamo', methods=['POST'])
def api_registrar_prestamo():
    """Registra un nuevo préstamo"""
    datos = request.get_json() or {}
    
    tipo = datos.get('tipo', '')
    nombre = datos.get('nombre', '')
    id_usuario = datos.get('id', '')
    grupo = datos.get('grupo', '')
    correo = datos.get('correo', '')
    libro_titulo = datos.get('libro_titulo', '')
    libro_isbn = datos.get('libro_isbn', '')
    dias_prestamo = int(datos.get('dias_prestamo', 7))
    
    if not tipo or not nombre or not libro_titulo:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha_inicio = datetime.now(tz_mexico).date()
        fecha_devolucion = fecha_inicio + timedelta(days=dias_prestamo)
        
        # Ajustar fecha de devolución para que sea día hábil
        while fecha_devolucion.weekday() >= 5:  # Si es sábado o domingo
            fecha_devolucion += timedelta(days=1)
        
        prestamo = {
            "tipo": tipo,
            "nombre": nombre,
            "id": id_usuario,
            "grupo": grupo,
            "correo": correo,
            "libro": {
                "titulo": libro_titulo,
                "isbn": libro_isbn
            },
            "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
            "fecha_devolucion": fecha_devolucion.strftime('%Y-%m-%d'),
            "estado": "Activo",
            "created_at": datetime.now(tz_mexico)
        }
        
        prestamos.insert_one(prestamo)
        
        # Reducir disponibles en inventario
        if libro_isbn:
            inventario.update_one(
                {"ISBN": libro_isbn},
                {"$inc": {"DISPONIBLES": -1}}
            )
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
