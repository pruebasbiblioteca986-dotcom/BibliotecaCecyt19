from flask import Flask, send_file, jsonify, request, render_template_string
from flask_cors import CORS
from pymongo import MongoClient
from unidecode import unidecode
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId
import threading
import time
# Importar SendGrid
import sendgrid
from sendgrid.helpers.mail import Mail
import os
import pandas as pd
from io import BytesIO
import calendar
import pytz

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

mongo_url = os.environ.get("MONGODB_URI")
client = MongoClient(mongo_url)
db = client["Biblioteca"]
inventario = db["Inventario"]
alumnos = db["Alumnos"]
prestamos = db["Prestamos"]
multas = db["Multas"]  # Colección para multas
devoluciones = db["Devoluciones"]  # Colección para devoluciones
sitio = db["Sitio"]  # Colección para registros de entrada al sitio
ajedrez = db["Ajedrez"]  # Colección para contadores de ajedrez

# Configuración de correo usando SendGrid
MODO_PRUEBA = os.getenv('MODO_PRUEBA', 'true').lower() == 'true'  # Cambia a 'false' para producción
CORREO_PRUEBA = os.getenv('CORREO_PRUEBA', '')  # Opcional: si está configurado, redirige todos los correos aquí (para pruebas controladas)
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'bibliotecacecyt19@ipn.com.mx')

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

@app.route('/api/buscar')
def buscar():
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
def buscar_html():
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

@app.route('/registrar_observacion', methods=['POST'])
def registrar_observacion():
    """Agrega una observación a un registro existente en la colección Sitio"""
    tipo = request.form.get('tipo', '')
    nombre = request.form.get('nombre', '')
    boleta = request.form.get('boleta', '')
    no_empleado = request.form.get('no_empleado', '')
    observacion_texto = request.form.get('observacion', '').strip()
    
    if not observacion_texto:
        return render_template_string('''
            <html>
            <head>
                <title>Error</title>
                <link rel="stylesheet" href="Interfaz.css">
            </head>
            <body>
                <div style="margin:60px auto;text-align:center;">
                    <h2 style="color:#dc3545;">Error: La observación no puede estar vacía</h2>
                    <a href="/" style="color:#6d1846;font-weight:bold;text-decoration:none;border:1px solid #6d1846;padding:8px 18px;border-radius:6px;">Volver al inicio</a>
                </div>
            </body>
            </html>
        ''')
    
    # Usar zona horaria de México para observaciones
    tz_mexico = pytz.timezone('America/Mexico_City')
    fecha_obs = datetime.now(tz_mexico)
    observacion = {
        "texto": observacion_texto,
        "fecha": fecha_obs.strftime('%Y-%m-%d'),
        "hora": fecha_obs.strftime('%H:%M:%S'),
        "fecha_completa": fecha_obs
    }
    
    # Buscar el registro más reciente del usuario en Sitio
    query = {}
    if tipo == 'alumno':
        query = {"tipo": "alumno", "boleta": boleta}
    else:
        query = {"tipo": "docente", "no_empleado": no_empleado}
    
    # Buscar el registro más reciente (del día de hoy o el más reciente)
    registro = sitio.find_one(query, sort=[("fecha_completa", -1)])
    
    if registro:
        # Agregar la observación al array de observaciones
        sitio.update_one(
            {"_id": registro["_id"]},
            {"$push": {"observaciones": observacion}}
        )
        mensaje = "Observación agregada correctamente al registro de entrada"
    else:
        # Si no hay registro, crear uno nuevo con la observación
        fecha_str = fecha_obs.strftime('%Y-%m-%d')
        nuevo_registro = {
            "tipo": tipo,
            "nombre": nombre,
            "fecha": fecha_str,
            "fecha_completa": fecha_obs,
            "hora_entrada": fecha_obs.strftime('%H:%M:%S'),
            "observaciones": [observacion]
        }
        if tipo == 'alumno':
            nuevo_registro["boleta"] = boleta
        else:
            nuevo_registro["no_empleado"] = no_empleado
        
        sitio.insert_one(nuevo_registro)
        mensaje = "Registro creado y observación agregada correctamente"
    
    return render_template_string('''
        <html>
        <head>
            <title>Observación registrada</title>
            <link rel="stylesheet" href="Interfaz.css">
        </head>
        <body>
            <div style="margin:60px auto;text-align:center;">
                <h2 style="color:#6d1846;">{{ mensaje }}</h2>
                <p style="color:#6d1846;">Fecha: {{ fecha }}</p>
                <div style="margin-top:40px;">
                    <a href="/" style="color:#6d1846;font-weight:bold;text-decoration:none;border:1px solid #6d1846;padding:12px 28px;border-radius:8px;display:inline-block;">Volver al inicio</a>
                </div>
            </div>
        </body>
        </html>
    ''', mensaje=mensaje, fecha=fecha_obs.strftime('%Y-%m-%d'))

@app.route('/')
def home():
    return send_file('Interfaz.html')

@app.route('/Interfaz.css')
def css():
    return send_file('Interfaz.css')

@app.route('/api/registrar_libro', methods=['POST'])
def registrar_libro():
    datos = request.get_json() or {}
    def getv(d, *keys):
        for k in keys:
            if k in d and d[k] not in (None, ''):
                return d[k]
        return ''
    titulo = getv(datos, 'TÍTULO','TITULO','Titulo','titulo') 
    autor = getv(datos, 'AUTOR','Autor','autor','author')
    editorial = getv(datos, 'EDITORIAL','Editorial','editorial','publisher')
    isbn = getv(datos, 'ISBN','Isbn','isbn')
    edicion = getv(datos, 'EDICIÓN','EDICION','Edicion','edicion','EDICION')
    estante = getv(datos, 'ESTANTE','Estante','estante')
    disp_raw = getv(datos, 'DISPONIBLES','Disponibles','disponible','DISPONIBLES')
    try:
        disponibles = int(disp_raw) if disp_raw != '' else None
    except:
        disponibles = None
    libro = {
        "TÍTULO": titulo,
        "AUTOR": autor,
        "EDITORIAL": editorial,
        "ISBN": isbn,
        
        "EDICIÓN": edicion,
        "ESTANTE": estante,
        # almacenar null si no hay valor numérico
        "DISPONIBLES": disponibles
    }
    try:
        inventario.insert_one(libro)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/actualizar_alumno', methods=['POST'])
def actualizar_alumno():
    datos = request.get_json() or {}
    boleta = datos.get('Boleta') or datos.get('boleta')
    if not boleta:
        return jsonify({"success": False, "error": "Boleta requerida"}), 400

    # construir objeto de actualización sólo con campos presentes
    allowed = {'Nombre':'Nombre','Correo':'Correo','Grupo':'Grupo','Carga':'Carga'}
    set_ops = {}
    for key in allowed:
        v = datos.get(key) if key in datos else datos.get(key.lower())
        if v is not None:
            set_ops[allowed[key]] = v

    if not set_ops:
        return jsonify({"success": False, "error": "Nada que actualizar"}), 400

    # intentar actualizar por campo Boleta (ajusta si guardas como número)
    query = {"Boleta": boleta}
    result = alumnos.update_one(query, {"$set": set_ops})

    # si no encontrado, intentar variante numérica
    if result.matched_count == 0:
        try:
            query_num = {"Boleta": int(boleta)}
            result = alumnos.update_one(query_num, {"$set": set_ops})
        except Exception:
            pass

    if result.matched_count == 0:
        return jsonify({"success": False, "error": "Alumno no encontrado"}), 404

    return jsonify({"success": True})

def add_business_days(start_date, days):
    # start_date: datetime or date; devuelve datetime
    if isinstance(start_date, datetime):
        d = start_date
    else:
        d = datetime.combine(start_date, datetime.min.time())
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0..4 => Mon..Fri
            added += 1
    return d

def count_business_days_between(start_date, end_date):
    """Cuenta días hábiles entre dos fechas (excluyendo fines de semana)"""
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    
    current = start_date
    count = 0
    while current < end_date:
        if current.weekday() < 5:  # Lunes a Viernes
            count += 1
        current += timedelta(days=1)
    return count

def calcular_dias_retraso(fecha_devolucion):
    """Calcula días hábiles de retraso desde la fecha de devolución hasta hoy"""
    try:
        if isinstance(fecha_devolucion, str):
            fecha_dev = datetime.strptime(fecha_devolucion, "%Y-%m-%d").date()
        else:
            fecha_dev = fecha_devolucion.date() if isinstance(fecha_devolucion, datetime) else fecha_devolucion
        
        tz_mexico = pytz.timezone('America/Mexico_City')
        hoy = datetime.now(tz_mexico).date()
        if fecha_dev >= hoy:
            return 0
        return count_business_days_between(fecha_dev, hoy)
    except Exception as e:
        print(f"Error calculando días de retraso: {e}")
        return 0

def calcular_multa(dias_retraso):
    """Calcula el monto de la multa: $7.50 por día hábil de retraso"""
    return round(dias_retraso * 7.50, 2)

def enviar_correo(destinatario, asunto, cuerpo):
    """Envía un correo electrónico al destinatario usando SendGrid"""
    # Validar que el destinatario tenga correo
    if not destinatario or not destinatario.strip():
        return False
    
    # Opcional: Si CORREO_PRUEBA está configurado, redirigir todos los correos ahí (para pruebas controladas)
    # Si CORREO_PRUEBA está vacío, se envían a los correos reales de los usuarios
    if MODO_PRUEBA and CORREO_PRUEBA and CORREO_PRUEBA.strip():
        destinatario_original = destinatario
        destinatario = CORREO_PRUEBA.strip()
        # Agregar información del destinatario original en el cuerpo
        cuerpo = f"[MODO PRUEBA - Correo original: {destinatario_original}]\n\n" + cuerpo
        asunto = f"[PRUEBA] {asunto}"
        print(f"[EMAIL] 🧪 MODO PRUEBA: Redirigiendo correo de {destinatario_original} a {destinatario}")
    elif MODO_PRUEBA:
        # Modo prueba pero sin redirección: enviar a correo real del usuario
        print(f"[EMAIL] 🧪 MODO PRUEBA: Enviando correo real a {destinatario}")
    
    # Validar configuración SendGrid
    if not SENDGRID_API_KEY or not SENDGRID_API_KEY.strip():
        print(f"[EMAIL] ⚠️ SendGrid no configurado. Crea un archivo .env con:")
        print(f"[EMAIL]    SENDGRID_API_KEY=tu_api_key_de_sendgrid")
        print(f"[EMAIL]    EMAIL_FROM=tu_correo@dominio.com")
        print(f"[EMAIL]    CORREO_PRUEBA=tu_correo@gmail.com (opcional)")
        print(f"[EMAIL]    Ver CONFIGURAR_CORREOS.md para más detalles")
        return False
    
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        mail = Mail(
            from_email=EMAIL_FROM,
            to_emails=destinatario.strip(),
            subject=asunto,
            plain_text_content=cuerpo
        )
        response = sg.send(mail)
        print(f"[EMAIL] ✅ Correo enviado exitosamente a {destinatario}: {asunto} (Status: {response.status_code})")
        return True
    except Exception as e:
        print(f"[EMAIL] ❌ Error enviando correo a {destinatario}: {e}")
        print(f"[EMAIL] Verifica tu API key de SendGrid en el archivo .env")
        return False

def verificar_y_actualizar_prestamos_vencidos():
    """Verifica préstamos activos y los marca como vencidos, creando multas si es necesario"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    prestamos_activos = prestamos.find({"estado": "Activo"})
    
    for prestamo in prestamos_activos:
        fecha_dev_str = prestamo.get("fecha_devolucion", "")
        if not fecha_dev_str:
            continue
        
        try:
            fecha_dev = datetime.strptime(fecha_dev_str, "%Y-%m-%d").date()
            dias_retraso = calcular_dias_retraso(fecha_dev)
            
            if dias_retraso > 0:
                # Marcar como vencido
                prestamos.update_one(
                    {"_id": prestamo["_id"]},
                    {"$set": {"estado": "Vencido"}}
                )
                
                # Actualizar estado en devoluciones
                devoluciones.update_many(
                    {"prestamo_id": str(prestamo["_id"])},
                    {"$set": {"estado": "Vencido"}}
                )
                
                # Verificar si ya existe multa para este préstamo
                multa_existente = multas.find_one({
                    "prestamo_id": str(prestamo["_id"]),
                    "estado": "Pendiente"
                })
                
                if not multa_existente:
                    # Crear nueva multa
                    monto = calcular_multa(dias_retraso)
                    multa_doc = {
                        "prestamo_id": str(prestamo["_id"]),
                        "tipo": prestamo.get("tipo", "alumno"),
                        "id": prestamo.get("id", ""),
                        "nombre": prestamo.get("nombre", ""),
                        "correo": prestamo.get("correo", ""),
                        "libro": prestamo.get("libro", {}),
                        "fecha_devolucion": fecha_dev_str,
                        "dias_retraso": dias_retraso,
                        "monto": monto,
                        "estado": "Pendiente",
                        "created_at": datetime.now(tz_mexico)
                    }
                    multas.insert_one(multa_doc)
                else:
                    # Actualizar multa existente con nuevos días de retraso
                    monto = calcular_multa(dias_retraso)
                    multas.update_one(
                        {"_id": multa_existente["_id"]},
                        {"$set": {
                            "dias_retraso": dias_retraso,
                            "monto": monto,
                            "updated_at": datetime.now(tz_mexico)
                        }}
                    )
        except Exception as e:
            print(f"Error verificando préstamo {prestamo.get('_id')}: {e}")

def enviar_recordatorios_diarios():
    """Envía recordatorios diarios por correo a usuarios con préstamos activos"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy = datetime.now(tz_mexico).date()
    prestamos_activos = prestamos.find({"estado": "Activo"})
    
    for prestamo in prestamos_activos:
        correo = prestamo.get("correo", "")
        if not correo:
            continue
        
        fecha_dev_str = prestamo.get("fecha_devolucion", "")
        if not fecha_dev_str:
            continue
        
        try:
            fecha_dev = datetime.strptime(fecha_dev_str, "%Y-%m-%d").date()
            dias_restantes = count_business_days_between(hoy, fecha_dev)
            nombre = prestamo.get("nombre", "")
            libro_titulo = prestamo.get("libro", {}).get("titulo", "el libro")
            
            asunto = ""
            cuerpo = ""
            
            if dias_restantes == 0:
                # Hoy es el día de devolución
                asunto = "⚠️ Tu préstamo vence HOY"
                cuerpo = f"""Estimado/a {nombre},

Tu préstamo vence HOY.

Libro: "{libro_titulo}"
Fecha de vencimiento: {fecha_dev_str}

Por favor, acude a la biblioteca HOY para realizar la devolución a tiempo y evitar multas.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
            elif dias_restantes == 1:
                # Queda 1 día
                asunto = "⏰ Tu préstamo vence en 1 día"
                cuerpo = f"""Estimado/a {nombre},

Tu préstamo vence en 1 día.

Libro: "{libro_titulo}"
Fecha de vencimiento: {fecha_dev_str}

Por favor, acude a la biblioteca mañana para realizar la devolución a tiempo.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
            elif dias_restantes == 2:
                # Quedan 2 días
                asunto = "📚 Tu préstamo vence en 2 días"
                cuerpo = f"""Estimado/a {nombre},

Tu préstamo vence en 2 días.

Libro: "{libro_titulo}"
Fecha de vencimiento: {fecha_dev_str}

Por favor, acude a la biblioteca para realizar la devolución a tiempo.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
            elif dias_restantes == 3:
                # Quedan 3 días
                asunto = "📖 Tu préstamo vence en 3 días"
                cuerpo = f"""Estimado/a {nombre},

Tu préstamo vence en 3 días.

Libro: "{libro_titulo}"
Fecha de vencimiento: {fecha_dev_str}

Por favor, acude a la biblioteca para realizar la devolución a tiempo.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
            
            if asunto and cuerpo:
                enviar_correo(correo, asunto, cuerpo)
        except Exception as e:
            print(f"Error enviando recordatorio a {correo}: {e}")

def enviar_recordatorios_multas():
    """Envía recordatorios de multas pendientes con mensajes según días de retraso"""
    multas_pendientes = multas.find({"estado": "Pendiente"})
    
    for multa in multas_pendientes:
        correo = multa.get("correo", "")
        if not correo:
            continue
        
        # Recalcular días de retraso y monto actualizados
        fecha_dev_str = multa.get("fecha_devolucion", "")
        if fecha_dev_str:
            try:
                dias_retraso = calcular_dias_retraso(fecha_dev_str)
                monto = calcular_multa(dias_retraso)
                # Actualizar en la base de datos
                multas.update_one(
                    {"_id": multa["_id"]},
                    {"$set": {
                        "dias_retraso": dias_retraso,
                        "monto": monto,
                        "updated_at": datetime.now(timezone.utc)
                    }}
                )
            except Exception:
                dias_retraso = multa.get("dias_retraso", 0)
                monto = multa.get("monto", 0)
        else:
            dias_retraso = multa.get("dias_retraso", 0)
            monto = multa.get("monto", 0)
        
        nombre = multa.get("nombre", "")
        libro_titulo = multa.get("libro", {}).get("titulo", "el libro")
        
        # Mensaje según días de retraso
        if dias_retraso == 1:
            asunto = "💰 Préstamo vencido: Debes 1 día de multa"
            cuerpo = f"""Estimado/a {nombre},

Tu préstamo está vencido. Debes 1 día de multa.

Libro: "{libro_titulo}"
Días de retraso: 1 día hábil
Monto a pagar: ${monto:.2f} (${7.50:.2f} por día hábil de retraso)

Por favor, acude a la biblioteca para pagar tu multa y devolver el libro.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
        elif dias_retraso == 2:
            asunto = "💰 Préstamo vencido: Debes 2 días de multa"
            cuerpo = f"""Estimado/a {nombre},

Tu préstamo está vencido. Debes 2 días de multa.

Libro: "{libro_titulo}"
Días de retraso: 2 días hábiles
Monto a pagar: ${monto:.2f} (${7.50:.2f} por día hábil de retraso)

Por favor, acude a la biblioteca para pagar tu multa y devolver el libro.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
        elif dias_retraso == 3:
            asunto = "💰 Préstamo vencido: Debes 3 días de multa"
            cuerpo = f"""Estimado/a {nombre},

Tu préstamo está vencido. Debes 3 días de multa.

Libro: "{libro_titulo}"
Días de retraso: 3 días hábiles
Monto a pagar: ${monto:.2f} (${7.50:.2f} por día hábil de retraso)

Por favor, acude a la biblioteca para pagar tu multa y devolver el libro.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
        else:
            # Más de 3 días
            asunto = f"💰 Préstamo vencido: Debes {dias_retraso} días de multa"
            cuerpo = f"""Estimado/a {nombre},

Tu préstamo está vencido. Debes {dias_retraso} días de multa.

Libro: "{libro_titulo}"
Días de retraso: {dias_retraso} días hábiles
Monto a pagar: ${monto:.2f} (${7.50:.2f} por día hábil de retraso)

Por favor, acude a la biblioteca para pagar tu multa y devolver el libro.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
        
        enviar_correo(correo, asunto, cuerpo)

@app.route('/api/registrar_prestamo', methods=['POST'])
def registrar_prestamo():
    datos = request.get_json() or {}
    tipo = datos.get('tipo', 'alumno')
    identificador = datos.get('id') or datos.get('boleta') or datos.get('no_empleado') or ''
    nombre = datos.get('nombre') or ''
    grupo = datos.get('grupo') or datos.get('cargo') or ''
    correo = datos.get('correo') or ''
    libro = datos.get('libro') or {}
    titulo = libro.get('titulo') or datos.get('titulo') or ''
    isbn = libro.get('isbn') or datos.get('ISBN') or ''

    # fecha inicio = hoy (hora local México), fecha devolucion = +3 dias hábiles
    tz_mexico = pytz.timezone('America/Mexico_City')
    hoy_dt = datetime.now(tz_mexico)
    fecha_inicio = datos.get('fecha_inicio') or hoy_dt.strftime('%Y-%m-%d')
    fecha_devolucion = datos.get('fecha_devolucion') or add_business_days(hoy_dt, 3).strftime('%Y-%m-%d')

    doc = {
        "tipo": tipo,
        "id": identificador,
        "nombre": nombre,
        "grupo": grupo,
        "correo": correo,
        "libro": {"titulo": titulo, "isbn": isbn},
        "fecha_inicio": fecha_inicio,
        "fecha_devolucion": fecha_devolucion,
        "estado": "Activo",
        "created_at": datetime.now(tz_mexico)
    }

    try:
        result = prestamos.insert_one(doc)
        prestamo_inserted_id = result.inserted_id
        
        # Crear registro en devoluciones
        devolucion_doc = {
            "prestamo_id": str(prestamo_inserted_id),
            "tipo": tipo,
            "id": identificador,
            "nombre": nombre,
            "grupo": grupo,
            "correo": correo,
            "libro": {"titulo": titulo, "isbn": isbn},
            "fecha_inicio": fecha_inicio,
            "fecha_devolucion": fecha_devolucion,
            "estado": "Activo",
            "created_at": datetime.now(tz_mexico)
        }
        # Intentar insertar en devoluciones (puede fallar si la colección no existe, pero no es crítico)
        try:
            devoluciones.insert_one(devolucion_doc)
        except Exception as e:
            print(f"[DEVOLUCIONES] No se pudo crear registro en devoluciones: {e}")
        
        # Enviar correo de confirmación de préstamo
        if correo:
            asunto = "✅ Has adquirido un préstamo - Biblioteca CECyT 19"
            cuerpo = f"""Estimado/a {nombre},

Has adquirido un préstamo:

Libro: "{titulo}"
ISBN: {isbn}
Fecha de préstamo: {fecha_inicio}
Fecha límite de devolución: {fecha_devolucion}

Tu préstamo vence el {fecha_devolucion}. Recibirás recordatorios cuando falten 3, 2 y 1 día para la fecha de vencimiento.

Saludos,
Biblioteca CECyT 19 "Leona Vicario"
IPN"""
            enviar_correo(correo, asunto, cuerpo)

        # --- actualizar inventario: buscar por ISBN primero, luego por título ---
        nuevo_valor_disponibles = None
        if isbn or titulo:
            or_clauses = []
            if isbn:
                or_clauses += [{"ISBN": isbn}, {"Isbn": isbn}, {"isbn": isbn}, {"ISBN": {"$regex": f"^{isbn}$"}}]
            if titulo:
                or_clauses += [
                    {"TÍTULO": titulo}, {"TITULO": titulo}, {"Titulo": titulo}, {"titulo": titulo},
                    {"title": titulo}
                ]
            if or_clauses:
                found = inventario.find_one({"$or": or_clauses})
                if found:
                    # obtener valor actual de disponibles intentando varias claves
                    cur = None
                    for k in ("DISPONIBLES","Disponibles","disponible","DISPONIBLE"):
                        if k in found and found.get(k) not in (None, ''):
                            cur = extract_number(found.get(k))
                            source_key = k
                            break
                    # fallback a estructura U
                    if cur in (None, ''):
                        cur = obtener_disponibles(found)
                        source_key = None
                    # intentar parsear a entero
                    cur_n = None
                    try:
                        if isinstance(cur, (int, float)):
                            cur_n = int(cur)
                        elif isinstance(cur, str) and cur.strip().isdigit():
                            cur_n = int(cur.strip())
                    except Exception:
                        cur_n = None

                    if cur_n is not None:
                        nuevo = max(0, cur_n - 1)
                        nuevo_valor_disponibles = nuevo
                        # actualizar campo canonical DISPONIBLES para que front y dashboard lo lean
                        inventario.update_one({"_id": found["_id"]}, {"$set": {"DISPONIBLES": nuevo}})
                    else:
                        # si no se pudo leer número, aún escribe DISPONIBLES = 0 (seguro)
                        inventario.update_one({"_id": found["_id"]}, {"$set": {"DISPONIBLES": 0}})
                        nuevo_valor_disponibles = 0


        tz_mexico = pytz.timezone('America/Mexico_City')
        start = datetime.now(tz_mexico).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        try:
            prestamos_hoy = prestamos.count_documents({"created_at": {"$gte": start, "$lt": end}})
        except Exception:
            prestamos_hoy = 0

        # libros en estantería (suma DISPONIBLES)
        libros_en_estanteria = 0
        for doc in inventario.find({}):
            v = None
            if "DISPONIBLES" in doc and doc.get("DISPONIBLES") not in (None, ""):
                try:
                    v = int(doc.get("DISPONIBLES"))
                except Exception:
                    v = None
            if v is None:
                for k in ("Disponibles","disponibles","DISPONIBLE","Disponible"):
                    if k in doc and doc.get(k) not in (None, ""):
                        try:
                            v = int(doc.get(k)); break
                        except Exception:
                            v = None
            if v is None:
                try:
                    tmp = obtener_disponibles(doc)
                    if isinstance(tmp, int):
                        v = tmp
                    elif isinstance(tmp, str) and tmp.isdigit():
                        v = int(tmp)
                except Exception:
                    v = None
            if isinstance(v, int) and v > 0:
                libros_en_estanteria += v

        return jsonify({
            "success": True,
            "prestamos_hoy": prestamos_hoy,
            "libros_estanteria": libros_en_estanteria,
            "nuevo_disponibles": nuevo_valor_disponibles
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/prestamos', methods=['GET'])
def api_prestamos():
    # Verificar y actualizar préstamos vencidos antes de listar
    verificar_y_actualizar_prestamos_vencidos()
    
    items = []
    # Incluir préstamos activos y vencidos (no devueltos)
    for doc in prestamos.find({"estado": {"$ne": "Devuelto"}}, {"_id": 0}).sort("created_at", -1):
        fi = doc.get("fecha_inicio", "")
        fd = doc.get("fecha_devolucion", "")
        estado = doc.get("estado", "")
        
        # Verificar estado si no está definido
        try:
            if not estado or estado == "Activo":
                if fd:
                    fd_dt = datetime.strptime(fd, "%Y-%m-%d")
                    dias_retraso = calcular_dias_retraso(fd)
                    if dias_retraso > 0:
                        estado = "Vencido"
                    else:
                        estado = "Activo"
                else:
                    estado = "Activo"
        except Exception:
            estado = doc.get("estado", "Activo")
        
        items.append({
            "tipo": doc.get("tipo", ""),
            "nombre": doc.get("nombre", ""),
            "id": doc.get("id", ""),
            "grupo": doc.get("grupo", ""),
            "correo": doc.get("correo", ""),
            "libro": doc.get("libro", {}),
            "fecha_inicio": fi,
            "fecha_devolucion": fd,
            "estado": estado
        })
    return jsonify({"prestamos": items})

@app.route('/api/multas', methods=['GET'])
def api_multas():
    # Actualizar multas pendientes con días de retraso actuales
    multas_pendientes = multas.find({"estado": "Pendiente"})
    for multa in multas_pendientes:
        prestamo_id = multa.get("prestamo_id", "")
        fecha_dev = multa.get("fecha_devolucion", "")
        if fecha_dev:
            dias_retraso = calcular_dias_retraso(fecha_dev)
            monto = calcular_multa(dias_retraso)
            multas.update_one(
                {"_id": multa["_id"]},
                {"$set": {
                    "dias_retraso": dias_retraso,
                    "monto": monto,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
    
    items = []
    for doc in multas.find({"estado": "Pendiente"}, {"_id": 0}).sort("created_at", -1):
        items.append({
            "prestamo_id": doc.get("prestamo_id", ""),
            "tipo": doc.get("tipo", ""),
            "nombre": doc.get("nombre", ""),
            "id": doc.get("id", ""),
            "correo": doc.get("correo", ""),
            "libro": doc.get("libro", {}),
            "fecha_devolucion": doc.get("fecha_devolucion", ""),
            "dias_retraso": doc.get("dias_retraso", 0),
            "monto": doc.get("monto", 0),
            "estado": doc.get("estado", "Pendiente")
        })
    return jsonify({"multas": items})

@app.route('/api/liberar_prestamo_vencido', methods=['POST'])
def liberar_prestamo_vencido():
    """Libera un préstamo vencido (similar a eliminar pero para vencidos)"""
    datos = request.get_json() or {}
    isbn = datos.get('isbn') or (datos.get('libro') or {}).get('isbn') or ''
    identificador = datos.get('id') or datos.get('boleta') or ''
    fecha_inicio = datos.get('fecha_inicio')

    query = {"estado": "Vencido"}
    if isbn:
        query["libro.isbn"] = isbn
    if identificador:
        query["id"] = str(identificador)
    if fecha_inicio:
        query["fecha_inicio"] = fecha_inicio
    
    prestamo = prestamos.find_one(query)
    if not prestamo:
        return jsonify({"success": False, "error": "Préstamo vencido no encontrado"}), 404
    
    try:
        # Eliminar préstamo
        prestamos.delete_one({"_id": prestamo["_id"]})
        
        # Eliminar multa asociada si existe
        tz_mexico = pytz.timezone('America/Mexico_City')
        multas.update_one(
            {"prestamo_id": str(prestamo["_id"]), "estado": "Pendiente"},
            {"$set": {"estado": "Pagada", "fecha_pago": datetime.now(tz_mexico)}}
        )
        
        # Eliminar de devoluciones si existe
        devoluciones.delete_many({
            "$or": [
                {"prestamo_id": str(prestamo["_id"])},
                {"libro.isbn": prestamo.get('libro', {}).get('isbn', '')},
                {"id": prestamo.get('id', '')},
                {"libro.isbn": isbn, "id": str(identificador)}
            ]
        })
        
        # Incrementar disponibles en inventario
        isbn_buscar = isbn or prestamo.get('libro', {}).get('isbn', '')
        titulo_buscar = prestamo.get('libro', {}).get('titulo', '')
        
        encontrado = None
        if isbn_buscar:
            isbn_clean = isbn_buscar.replace('-', '').replace(' ', '').strip()
            encontrado = inventario.find_one({
                "$or": [
                    {"ISBN": isbn_buscar}, {"Isbn": isbn_buscar}, {"isbn": isbn_buscar},
                    {"ISBN": isbn_clean}, {"Isbn": isbn_clean}, {"isbn": isbn_clean}
                ]
            })
        if not encontrado and titulo_buscar:
            encontrado = inventario.find_one({
                "$or": [
                    {"TÍTULO": titulo_buscar}, {"TITULO": titulo_buscar},
                    {"Titulo": titulo_buscar}, {"titulo": titulo_buscar}
                ]
            })
        if encontrado:
            cur_val = None
            for k in ("DISPONIBLES","Disponibles","disponible","DISPONIBLE","Disponible"):
                if k in encontrado and encontrado.get(k) not in (None, ""):
                    try:
                        cur_val = int(encontrado.get(k))
                        break
                    except Exception:
                        cur_val = None
            if cur_val is None:
                try:
                    tmp = obtener_disponibles(encontrado)
                    if isinstance(tmp, int):
                        cur_val = tmp
                    elif isinstance(tmp, str) and tmp.isdigit():
                        cur_val = int(tmp)
                except Exception:
                    cur_val = None
            if cur_val is None:
                cur_val = 0
            nuevo = cur_val + 1
            inventario.update_one({"_id": encontrado["_id"]}, {"$set": {"DISPONIBLES": nuevo}})
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/liberar_multa', methods=['POST'])
def liberar_multa():
    """Marca una multa como pagada y elimina el préstamo asociado"""
    datos = request.get_json() or {}
    multa_id = datos.get('multa_id') or datos.get('id')
    prestamo_id = datos.get('prestamo_id')
    
    if not multa_id and not prestamo_id:
        return jsonify({"success": False, "error": "ID de multa o préstamo requerido"}), 400
    
    query = {}
    if multa_id:
        try:
            query = {"_id": ObjectId(multa_id)}
        except Exception:
            query = {"_id": multa_id}
    elif prestamo_id:
        query = {"prestamo_id": str(prestamo_id), "estado": "Pendiente"}
    
    multa = multas.find_one(query)
    if not multa:
        return jsonify({"success": False, "error": "Multa no encontrada"}), 404
    
    try:
        # Marcar multa como pagada
        tz_mexico = pytz.timezone('America/Mexico_City')
        multas.update_one(
            {"_id": multa["_id"]},
            {"$set": {"estado": "Pagada", "fecha_pago": datetime.now(tz_mexico)}}
        )
        
        # Eliminar préstamo asociado si existe
        prestamo_id_obj = multa.get("prestamo_id", "")
        prestamo_eliminado = False
        if prestamo_id_obj:
            try:
                prestamo_obj_id = ObjectId(prestamo_id_obj)
                result = prestamos.delete_one({"_id": prestamo_obj_id})
                prestamo_eliminado = result.deleted_count > 0
            except Exception:
                # Intentar buscar por otros campos
                result = prestamos.delete_one({
                    "libro.isbn": multa.get("libro", {}).get("isbn", ""),
                    "id": multa.get("id", ""),
                    "estado": "Vencido"
                })
                prestamo_eliminado = result.deleted_count > 0
        
        # Eliminar de devoluciones si existe
        if prestamo_eliminado or prestamo_id_obj:
            devoluciones.delete_many({
                "$or": [
                    {"prestamo_id": str(prestamo_id_obj)},
                    {"libro.isbn": multa.get("libro", {}).get("isbn", "")},
                    {"id": multa.get("id", "")}
                ]
            })
        
        # Incrementar disponibles en inventario
        isbn_buscar = multa.get('libro', {}).get('isbn', '')
        titulo_buscar = multa.get('libro', {}).get('titulo', '')
        
        encontrado = None
        if isbn_buscar:
            isbn_clean = isbn_buscar.replace('-', '').replace(' ', '').strip()
            encontrado = inventario.find_one({
                "$or": [
                    {"ISBN": isbn_buscar}, {"Isbn": isbn_buscar}, {"isbn": isbn_buscar},
                    {"ISBN": isbn_clean}, {"Isbn": isbn_clean}, {"isbn": isbn_clean}
                ]
            })
        if not encontrado and titulo_buscar:
            encontrado = inventario.find_one({
                "$or": [
                    {"TÍTULO": titulo_buscar}, {"TITULO": titulo_buscar},
                    {"Titulo": titulo_buscar}, {"titulo": titulo_buscar}
                ]
            })
        if encontrado:
            cur_val = None
            for k in ("DISPONIBLES","Disponibles","disponible","DISPONIBLE","Disponible"):
                if k in encontrado and encontrado.get(k) not in (None, ""):
                    try:
                        cur_val = int(encontrado.get(k))
                        break
                    except Exception:
                        cur_val = None
            if cur_val is None:
                try:
                    tmp = obtener_disponibles(encontrado)
                    if isinstance(tmp, int):
                        cur_val = tmp
                    elif isinstance(tmp, str) and tmp.isdigit():
                        cur_val = int(tmp)
                except Exception:
                    cur_val = None
            if cur_val is None:
                cur_val = 0
            nuevo = cur_val + 1
            inventario.update_one({"_id": encontrado["_id"]}, {"$set": {"DISPONIBLES": nuevo}})
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sitio', methods=['GET'])
def api_sitio():
    """Lista todos los registros de entrada al sitio"""
    # Verificar y limpiar registros antiguos (más de 1 mes) antes de listar
    limpiar_registros_antiguos()
    
    # Obtener fecha actual en zona horaria de México
    tz_mexico = pytz.timezone('America/Mexico_City')
    ahora = datetime.now(tz_mexico)
    fecha_hoy = ahora.strftime('%Y-%m-%d')
    
    # Actualizar registros antiguos que no tengan los campos "eliminado" o "reiniciado"
    sitio.update_many(
        {"eliminado": {"$exists": False}},
        {"$set": {"eliminado": False}}
    )
    sitio.update_many(
        {"reiniciado": {"$exists": False}},
        {"$set": {"reiniciado": False}}
    )
    
    # Contar alumnos que ingresaron hoy (7am - 10pm) - incluye eliminados en el conteo
    # Usar un enfoque simple: contar todos los alumnos del día y filtrar por hora
    contador_dia = 0
    
    # Obtener todos los registros de alumnos del día
    # El contador cuenta TODOS los registros (incluyendo eliminados individualmente)
    # Solo se excluyen los que fueron reiniciados (tienen reiniciado: True)
    registros_hoy = list(sitio.find({
        "tipo": "alumno",
        "fecha": fecha_hoy,
        "reiniciado": {"$ne": True}  # No contar los que fueron reiniciados
    }))
    
    for doc in registros_hoy:
        fecha_completa = doc.get("fecha_completa")
        hora_entrada_str = doc.get("hora_entrada", "")
        
        # Verificar si está en el rango 7am-10pm
        en_rango = False
        
        # Intentar usar fecha_completa primero
        if fecha_completa and isinstance(fecha_completa, datetime):
            try:
                # Normalizar timezone
                if fecha_completa.tzinfo is None:
                    fecha_completa = tz_mexico.localize(fecha_completa)
                else:
                    fecha_completa = fecha_completa.astimezone(tz_mexico)
                
                # Verificar rango 7am-10pm
                hora_registro = fecha_completa.hour
                if 7 <= hora_registro <= 22:
                    en_rango = True
            except Exception as e:
                # Si falla, intentar con hora_entrada
                pass
        
        # Si no se pudo con fecha_completa, usar hora_entrada string
        if not en_rango and hora_entrada_str:
            try:
                partes_hora = hora_entrada_str.split(':')
                if partes_hora:
                    hora_int = int(partes_hora[0])
                    if 7 <= hora_int <= 22:
                        en_rango = True
            except:
                pass
        
        # Si no hay información de hora, contar igual (por seguridad, mejor contar de más)
        if not en_rango:
            # Si no tenemos información de hora, contar igual
            en_rango = True
        
        if en_rango:
            contador_dia += 1
    
    items = []
    # Obtener registros NO eliminados y NO reiniciados, ordenados por fecha más reciente
    # No usar proyección para obtener todos los campos
    for doc in sitio.find({
        "eliminado": {"$ne": True},
        "reiniciado": {"$ne": True},
        "tipo": {"$ne": "resumen_reinicio"}  # No mostrar los resúmenes de reinicio
    }).sort("fecha_completa", -1).limit(500):
        tipo = doc.get("tipo", "")
        nombre = doc.get("nombre", "")
        fecha = doc.get("fecha", "")
        hora_entrada = doc.get("hora_entrada", "")
        turno = doc.get("turno", "")
        observaciones = doc.get("observaciones", [])
        registro_id = str(doc.get("_id", ""))
        
        # Obtener identificador según tipo
        identificador = ""
        grupo = ""
        if tipo == "alumno":
            identificador = doc.get("boleta", "")
            grupo = doc.get("grupo", "")
        else:
            identificador = doc.get("no_empleado", "")
            grupo = doc.get("ocupacion", "")
        
        items.append({
            "_id": registro_id,
            "tipo": tipo,
            "nombre": nombre,
            "identificador": identificador,
            "grupo": grupo,
            "turno": turno,
            "fecha": fecha,
            "hora_entrada": hora_entrada,
            "observaciones": observaciones
        })
    
    return jsonify({
        "registros": items,
        "contador_dia": contador_dia
    })

def limpiar_registros_antiguos():
    """Elimina registros de la colección Sitio que tengan más de 1 mes.
    El día 30 de cada mes, guarda un resumen diario y limpia los registros."""
    try:
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora = datetime.now(tz_mexico)
        
        # Si es día 30, guardar resumen mensual y limpiar
        if ahora.day == 30:
            print(f"[SITIO] Día 30 detectado. Guardando resumen mensual y limpiando registros...")
            
            # Calcular rango del mes actual
            inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            fin_mes = ahora.replace(day=30, hour=23, minute=59, second=59, microsecond=999999)
            
            # Obtener todos los registros del mes (incluyendo eliminados para el conteo)
            registros_mes = list(sitio.find({
                "fecha_completa": {"$gte": inicio_mes, "$lte": fin_mes}
            }))
            
            # Agrupar por día y contar alumnos (7am-10pm)
            resumen_por_dia = {}
            for reg in registros_mes:
                fecha_reg = reg.get("fecha", "")
                tipo_reg = reg.get("tipo", "")
                hora_entrada = reg.get("hora_entrada", "")
                fecha_completa = reg.get("fecha_completa")
                
                if not fecha_reg or tipo_reg != "alumno":
                    continue
                
                # Verificar si está en el rango 7am-10pm
                if fecha_completa:
                    hora = fecha_completa.hour
                    if 7 <= hora <= 22:  # 7am a 10pm
                        if fecha_reg not in resumen_por_dia:
                            resumen_por_dia[fecha_reg] = 0
                        resumen_por_dia[fecha_reg] += 1
            
            # Guardar resumen en la colección (crear documento de resumen)
            if resumen_por_dia:
                resumen_doc = {
                    "tipo": "resumen_mensual",
                    "mes": ahora.month,
                    "año": ahora.year,
                    "fecha_creacion": ahora,
                    "resumen_por_dia": resumen_por_dia,
                    "total_dias": len(resumen_por_dia),
                    "total_alumnos": sum(resumen_por_dia.values())
                }
                sitio.insert_one(resumen_doc)
                print(f"[SITIO] Resumen mensual guardado: {len(resumen_por_dia)} días, {sum(resumen_por_dia.values())} alumnos totales")
            
            # Eliminar todos los registros del mes (ya tenemos el resumen)
            resultado = sitio.delete_many({
                "fecha_completa": {"$gte": inicio_mes, "$lte": fin_mes},
                "tipo": {"$ne": "resumen_mensual"}  # No eliminar los resúmenes
            })
            if resultado.deleted_count > 0:
                print(f"[SITIO] Eliminados {resultado.deleted_count} registros del mes (resumen guardado)")
        else:
            # Limpieza normal: eliminar registros de más de 1 mes
            fecha_limite = ahora - timedelta(days=30)
            resultado = sitio.delete_many({
                "fecha_completa": {"$lt": fecha_limite},
                "tipo": {"$ne": "resumen_mensual"}  # No eliminar los resúmenes
            })
            if resultado.deleted_count > 0:
                print(f"[SITIO] Eliminados {resultado.deleted_count} registros antiguos (más de 1 mes)")
    except Exception as e:
        print(f"[SITIO] Error limpiando registros antiguos: {e}")

@app.route('/api/sitio/eliminar', methods=['POST'])
def eliminar_registro_sitio():
    """Marca un registro como eliminado (se mantiene en el conteo del día)"""
    try:
        data = request.get_json()
        registro_id = data.get('id', '')
        
        if not registro_id:
            return jsonify({"success": False, "error": "ID requerido"}), 400
        
        # Buscar y marcar como eliminado
        from bson.objectid import ObjectId
        try:
            obj_id = ObjectId(registro_id)
        except:
            return jsonify({"success": False, "error": "ID inválido"}), 400
        
        resultado = sitio.update_one(
            {"_id": obj_id},
            {"$set": {"eliminado": True}}
        )
        
        if resultado.modified_count > 0:
            return jsonify({"success": True, "message": "Registro eliminado de la tabla"})
        else:
            return jsonify({"success": False, "error": "Registro no encontrado"}), 404
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sitio/reiniciar-contador', methods=['POST'])
def reiniciar_contador_sitio():
    """Guarda el total actual del contador y luego lo reinicia a 0"""
    try:
        # Obtener fecha actual en zona horaria de México
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora = datetime.now(tz_mexico)
        fecha_hoy = ahora.strftime('%Y-%m-%d')
        
        # PRIMERO: Contar el total actual de alumnos del día (antes de reiniciar)
        # Contar todos los alumnos del día que NO fueron reiniciados previamente
        total_antes_reinicio = 0
        registros_antes = list(sitio.find({
            "tipo": "alumno",
            "fecha": fecha_hoy,
            "reiniciado": {"$ne": True}
        }))
        
        for doc in registros_antes:
            fecha_completa = doc.get("fecha_completa")
            hora_entrada_str = doc.get("hora_entrada", "")
            
            # Verificar si está en el rango 7am-10pm
            en_rango = False
            
            if fecha_completa and isinstance(fecha_completa, datetime):
                try:
                    if fecha_completa.tzinfo is None:
                        fecha_completa = tz_mexico.localize(fecha_completa)
                    else:
                        fecha_completa = fecha_completa.astimezone(tz_mexico)
                    
                    hora_registro = fecha_completa.hour
                    if 7 <= hora_registro <= 22:
                        en_rango = True
                except:
                    pass
            
            if not en_rango and hora_entrada_str:
                try:
                    partes_hora = hora_entrada_str.split(':')
                    if partes_hora:
                        hora_int = int(partes_hora[0])
                        if 7 <= hora_int <= 22:
                            en_rango = True
                except:
                    pass
            
            if not en_rango:
                en_rango = True  # Por seguridad
            
            if en_rango:
                total_antes_reinicio += 1
        
        # SEGUNDO: Guardar el total en la base de datos
        registro_reinicio = {
            "tipo": "resumen_reinicio",
            "fecha": fecha_hoy,
            "fecha_completa": ahora,
            "total_alumnos": total_antes_reinicio,
            "hora_reinicio": ahora.strftime('%H:%M:%S'),
            "created_at": ahora
        }
        sitio.insert_one(registro_reinicio)
        
        # TERCERO: Marcar todos los registros del día como reiniciados (para que el contador muestre 0)
        resultado = sitio.update_many(
            {
                "fecha": fecha_hoy,
                "tipo": {"$in": ["alumno", "docente"]},
                "reiniciado": {"$ne": True}  # Solo los que no fueron reiniciados
            },
            {"$set": {"reiniciado": True}}
        )
        
        return jsonify({
            "success": True,
            "message": f"Contador reiniciado. Total guardado: {total_antes_reinicio} alumnos.",
            "total_guardado": total_antes_reinicio,
            "registros_afectados": resultado.modified_count
        })
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ajedrez/buscar_usuario')
def ajedrez_buscar_usuario():
    """Busca un usuario (alumno o docente) para ajedrez"""
    id_buscar = request.args.get('id', '').strip()
    tipo = request.args.get('tipo', 'alumno').strip()
    
    if not id_buscar:
        return jsonify({"encontrado": False, "error": "ID requerido"}), 400
    
    if tipo == 'alumno':
        # Buscar alumno
        query = {
            "$or": [
                {"Boleta": id_buscar},
                {"boleta": id_buscar}
            ]
        }
        if id_buscar.isdigit():
            try:
                query["$or"].append({"Boleta": int(id_buscar)})
                query["$or"].append({"boleta": int(id_buscar)})
            except Exception:
                pass
        
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
            "tipo": "alumno",
            "nombre": pick(doc, ["Nombre","nombre","Nombre Del Alumno:\n(Completo)"]),
            "id": pick(doc, ["Boleta","boleta"]),
            "grupo": pick(doc, ["Grupo","grupo"]),
            "carga": pick(doc, ["Carga","carga","Tipo de Carga(Horario)\n(MEDIA, MINIMA o COMPLETA)"]),
            "correo": pick(doc, ["Correo","correo","Email","email"])
        })
    else:
        # Buscar docente
        query = {
            "$or": [
                {"No Empleado": id_buscar},
                {"NoEmpleado": id_buscar},
                {"no_empleado": id_buscar},
                {"noEmpleado": id_buscar}
            ]
        }
        if id_buscar.isdigit():
            try:
                query["$or"].append({"No Empleado": int(id_buscar)})
                query["$or"].append({"NoEmpleado": int(id_buscar)})
            except Exception:
                pass
        
        doc = db["Docentes"].find_one(query, {"_id": 0})
        if not doc:
            return jsonify({"encontrado": False})
        
        return jsonify({
            "encontrado": True,
            "tipo": "docente",
            "nombre": doc.get("Nombre Completo", "") or doc.get("Nombre", "") or doc.get("nombre", ""),
            "id": doc.get("No Empleado", "") or doc.get("NoEmpleado", "") or doc.get("no_empleado", "") or doc.get("noEmpleado", ""),
            "grupo": doc.get("Ocupación \n(Docente u otro)", "") or doc.get("Ocupacion", "") or doc.get("ocupacion", "") or doc.get("Cargo", "") or doc.get("cargo", ""),
            "carga": doc.get("Turno", "") or doc.get("turno", ""),
            "correo": doc.get("Correo", "") or doc.get("correo", "")
        })

@app.route('/api/ajedrez/iniciar', methods=['POST'])
def ajedrez_iniciar():
    """Inicia un contador de 40 minutos para un usuario"""
    datos = request.get_json() or {}
    tipo = datos.get('tipo', 'alumno')
    nombre = datos.get('nombre', '')
    id_usuario = datos.get('id', '')
    grupo = datos.get('grupo', '')
    carga = datos.get('carga', '')
    correo = datos.get('correo', '')
    
    if not nombre or not id_usuario:
        return jsonify({"success": False, "error": "Nombre e ID requeridos"}), 400
    
    # Verificar si ya tiene un contador activo
    contador_activo = ajedrez.find_one({
        "id": str(id_usuario),
        "estado": "activo"
    })
    
    if contador_activo:
        return jsonify({"success": False, "error": "El usuario ya tiene un contador activo"}), 400
    
    # Crear registro con contador de 40 minutos (2400 segundos)
    tz_mexico = pytz.timezone('America/Mexico_City')
    ahora = datetime.now(tz_mexico)
    tiempo_inicio = ahora
    tiempo_fin = ahora + timedelta(minutes=40)
    
    registro = {
        "tipo": tipo,
        "nombre": nombre,
        "id": str(id_usuario),
        "grupo": grupo,
        "carga": carga,
        "correo": correo,
        "tiempo_inicio": tiempo_inicio,
        "tiempo_fin": tiempo_fin,
        "tiempo_restante_segundos": 2400,  # 40 minutos en segundos
        "estado": "activo",
        "created_at": ahora
    }
    
    try:
        ajedrez.insert_one(registro)
        return jsonify({
            "success": True,
            "tiempo_restante_segundos": 2400,
            "tiempo_fin": tiempo_fin.isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ajedrez', methods=['GET'])
def api_ajedrez():
    """Lista todos los contadores activos de ajedrez"""
    items = []
    ahora = datetime.now(timezone.utc)
    
    for doc in ajedrez.find({"estado": "activo"}, {"_id": 0}).sort("tiempo_inicio", -1):
        tiempo_fin = doc.get("tiempo_fin")
        
        # Convertir tiempo_fin a datetime con timezone si es necesario
        if tiempo_fin:
            if isinstance(tiempo_fin, str):
                try:
                    tiempo_fin = datetime.fromisoformat(tiempo_fin.replace('Z', '+00:00'))
                except Exception:
                    tiempo_fin = None
            elif isinstance(tiempo_fin, datetime):
                # Si es datetime pero sin timezone, agregar UTC
                if tiempo_fin.tzinfo is None:
                    tiempo_fin = tiempo_fin.replace(tzinfo=timezone.utc)
        
        if tiempo_fin:
            # Calcular tiempo restante
            diferencia = tiempo_fin - ahora
            segundos_restantes = max(0, int(diferencia.total_seconds()))
            
            # Actualizar en la base de datos
            ajedrez.update_one(
                {"id": doc.get("id"), "estado": "activo"},
                {"$set": {"tiempo_restante_segundos": segundos_restantes}}
            )
            
            # Si llegó a 0, marcar como finalizado
            if segundos_restantes == 0:
                ajedrez.update_one(
                    {"id": doc.get("id"), "estado": "activo"},
                    {"$set": {"estado": "finalizado", "fecha_finalizacion": ahora}}
                )
                estado = "finalizado"
            else:
                estado = "activo"
        else:
            segundos_restantes = doc.get("tiempo_restante_segundos", 0)
            estado = doc.get("estado", "activo")
        
        # Formatear tiempo
        minutos = segundos_restantes // 60
        segundos = segundos_restantes % 60
        tiempo_formato = f"{minutos:02d}:{segundos:02d}"
        
        items.append({
            "tipo": doc.get("tipo", ""),
            "nombre": doc.get("nombre", ""),
            "id": doc.get("id", ""),
            "grupo": doc.get("grupo", ""),
            "carga": doc.get("carga", ""),
            "correo": doc.get("correo", ""),
            "tiempo_restante_segundos": segundos_restantes,
            "tiempo_formato": tiempo_formato,
            "estado": estado,
            "tiempo_inicio": doc.get("tiempo_inicio", "").isoformat() if isinstance(doc.get("tiempo_inicio"), datetime) else str(doc.get("tiempo_inicio", ""))
        })
    
    return jsonify({"contadores": items})

@app.route('/api/ajedrez/terminar', methods=['POST'])
def ajedrez_terminar():
    """Termina un contador de ajedrez"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id', '')
    
    if not id_usuario:
        return jsonify({"success": False, "error": "ID requerido"}), 400
    
    resultado = ajedrez.update_one(
        {"id": str(id_usuario), "estado": "activo"},
        {"$set": {"estado": "terminado", "fecha_finalizacion": datetime.now(timezone.utc)}}
    )
    
    if resultado.modified_count > 0:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Contador no encontrado o ya terminado"}), 404

@app.route('/api/ajedrez/reiniciar', methods=['POST'])
def ajedrez_reiniciar():
    """Reinicia un contador de ajedrez (nuevos 40 minutos)"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id', '')
    
    if not id_usuario:
        return jsonify({"success": False, "error": "ID requerido"}), 400
    
    ahora = datetime.now(timezone.utc)
    tiempo_fin = ahora + timedelta(minutes=40)
    
    resultado = ajedrez.update_one(
        {"id": str(id_usuario), "estado": {"$in": ["activo", "finalizado"]}},
        {"$set": {
            "tiempo_inicio": ahora,
            "tiempo_fin": tiempo_fin,
            "tiempo_restante_segundos": 2400,
            "estado": "activo",
            "fecha_finalizacion": None
        }}
    )
    
    if resultado.modified_count > 0:
        return jsonify({
            "success": True,
            "tiempo_restante_segundos": 2400,
            "tiempo_fin": tiempo_fin.isoformat()
        })
    else:
        return jsonify({"success": False, "error": "Contador no encontrado"}), 404

@app.route('/api/ajedrez/eliminar', methods=['POST'])
def ajedrez_eliminar():
    """Elimina un registro de ajedrez"""
    datos = request.get_json() or {}
    id_usuario = datos.get('id', '')
    
    if not id_usuario:
        return jsonify({"success": False, "error": "ID requerido"}), 400
    
    resultado = ajedrez.delete_one({"id": str(id_usuario)})
    
    if resultado.deleted_count > 0:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Registro no encontrado"}), 404

def generar_datos_reporte_mensual(mes=None, año=None):
    """Genera los datos del reporte mensual desde MongoDB"""
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    # Calcular rango de fechas del mes
    inicio_mes = datetime(año, mes, 1, tzinfo=timezone.utc)
    if mes == 12:
        fin_mes = datetime(año + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fin_mes = datetime(año, mes + 1, 1, tzinfo=timezone.utc)
    
    datos = {}
    
    # 1. ACERVO BIBLIOGRÁFICO - LIBROS
    # EXISTENCIA TOTAL (títulos y volúmenes)
    total_titulos = inventario.count_documents({})
    total_volumenes = 0
    for doc in inventario.find({}):
        disponibles = obtener_disponibles(doc)
        if disponibles:
            try:
                num = int(str(disponibles).replace(',', '').split()[0])
                total_volumenes += num
            except:
                pass
    
    datos['acervo_existencia_titulos'] = total_titulos
    datos['acervo_existencia_volumenes'] = total_volumenes
    
    # ADQUISICIONES del mes (libros registrados en el mes)
    # Nota: Si no tienes campo created_at, esto contará 0. Puedes ajustar según tu estructura
    adquisiciones_titulos = 0
    adquisiciones_volumenes = 0
    try:
        adquisiciones_titulos = inventario.count_documents({
            "created_at": {"$gte": inicio_mes, "$lt": fin_mes}
        })
        for doc in inventario.find({"created_at": {"$gte": inicio_mes, "$lt": fin_mes}}):
            disponibles = obtener_disponibles(doc)
            if disponibles:
                try:
                    num = int(str(disponibles).replace(',', '').split()[0])
                    adquisiciones_volumenes += num
                except:
                    pass
    except Exception:
        # Si no existe el campo created_at, asumimos 0 adquisiciones
        adquisiciones_titulos = 0
        adquisiciones_volumenes = 0
    
    datos['acervo_adquisiciones_titulos'] = adquisiciones_titulos
    datos['acervo_adquisiciones_volumenes'] = adquisiciones_volumenes
    
    # 2. MATERIALES CONSULTADOS
    # MATERIALES CONSULTADOS EN SALA (préstamos que se consultaron en sala)
    # Por ahora, asumimos que todos los préstamos son a domicilio
    # Si tienes un campo para distinguir, úsalo aquí
    materiales_sala_titulos = 0
    materiales_sala_volumenes = 0
    
    # PRÉSTAMOS A DOMICILIO del mes
    prestamos_mes = prestamos.find({
        "fecha_inicio": {"$gte": inicio_mes.strftime("%Y-%m-%d"), "$lt": fin_mes.strftime("%Y-%m-%d")}
    })
    prestamos_domicilio_titulos = 0
    prestamos_domicilio_volumenes = 0
    for p in prestamos_mes:
        prestamos_domicilio_titulos += 1
        prestamos_domicilio_volumenes += 1
    
    datos['materiales_sala_titulos'] = materiales_sala_titulos
    datos['materiales_sala_volumenes'] = materiales_sala_volumenes
    datos['prestamos_domicilio_titulos'] = prestamos_domicilio_titulos
    datos['prestamos_domicilio_volumenes'] = prestamos_domicilio_volumenes
    datos['total_materiales_consultados_titulos'] = materiales_sala_titulos + prestamos_domicilio_titulos
    datos['total_materiales_consultados_volumenes'] = materiales_sala_volumenes + prestamos_domicilio_volumenes
    
    # 3. SERVICIOS BIBLIOTECARIOS
    # USUARIOS ATENDIDOS (usuarios que usaron la biblioteca en el mes)
    usuarios_atendidos_hombres = 0
    usuarios_atendidos_mujeres = 0
    
    # Contar usuarios únicos que tuvieron préstamos en el mes
    usuarios_unicos = set()
    for p in prestamos.find({
        "fecha_inicio": {"$gte": inicio_mes.strftime("%Y-%m-%d"), "$lt": fin_mes.strftime("%Y-%m-%d")}
    }):
        usuario_id = p.get("id") or p.get("identificador") or ""
        if usuario_id:
            usuarios_unicos.add(usuario_id)
    
    # Contar por género (necesitarías tener un campo de género en alumnos/docentes)
    # Por ahora, asumimos distribución 50/50 o puedes ajustar según tus datos
    usuarios_atendidos_hombres = len(usuarios_unicos) // 2
    usuarios_atendidos_mujeres = len(usuarios_unicos) - usuarios_atendidos_hombres
    
    datos['usuarios_atendidos_hombres'] = usuarios_atendidos_hombres
    datos['usuarios_atendidos_mujeres'] = usuarios_atendidos_mujeres
    datos['usuarios_atendidos_total'] = len(usuarios_unicos)
    
    # USUARIOS INSCRITOS A LA BIBLIOTECA (total de alumnos y docentes)
    total_alumnos = alumnos.count_documents({})
    total_docentes = db["Docentes"].count_documents({})
    total_inscritos = total_alumnos + total_docentes
    
    # Distribución por género (asumiendo 50/50 si no tienes el campo)
    usuarios_inscritos_hombres = total_inscritos // 2
    usuarios_inscritos_mujeres = total_inscritos - usuarios_inscritos_hombres
    
    datos['usuarios_inscritos_hombres'] = usuarios_inscritos_hombres
    datos['usuarios_inscritos_mujeres'] = usuarios_inscritos_mujeres
    datos['usuarios_inscritos_total'] = total_inscritos
    
    # 4. PERSONAL ADSCRITO A LA BIBLIOTECA
    # Esto normalmente se llena manualmente, pero puedes tener una colección para esto
    datos['personal_directivo_hombres'] = 0
    datos['personal_directivo_mujeres'] = 0
    datos['personal_procesos_tecnicos_hombres'] = 0
    datos['personal_procesos_tecnicos_mujeres'] = 0
    datos['personal_servicios_publico_hombres'] = 0
    datos['personal_servicios_publico_mujeres'] = 0
    datos['personal_apoyo_bibliotecarios_hombres'] = 0
    datos['personal_apoyo_bibliotecarios_mujeres'] = 0
    datos['personal_administrativo_hombres'] = 0
    datos['personal_administrativo_mujeres'] = 0
    datos['personal_apoyo_administrativos_hombres'] = 0
    datos['personal_apoyo_administrativos_mujeres'] = 0
    datos['personal_otros_hombres'] = 0
    datos['personal_otros_mujeres'] = 0
    datos['personal_total'] = 0
    
    return datos

def generar_reporte_excel(mes=None, año=None):
    """Genera el archivo Excel del reporte mensual"""
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    # Leer el template
    template_path = "Reporte AGOSTO ( 18-29 ) (1).xls"
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template no encontrado: {template_path}")
    
    try:
        # Leer todas las hojas (pandas puede leer .xls con xlrd)
        excel_file = pd.ExcelFile(template_path, engine='xlrd')
    except Exception as e:
        # Si falla con xlrd, intentar con openpyxl (para .xlsx) o sin engine
        try:
            excel_file = pd.ExcelFile(template_path)
        except Exception as e2:
            raise FileNotFoundError(f"Error al leer el archivo Excel: {e2}")
    
    # Obtener datos del mes
    datos = generar_datos_reporte_mensual(mes, año)
    
    # Nombres de meses en español
    meses_espanol = ['', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
                     'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
    mes_nombre = meses_espanol[mes]
    
    # Crear un nuevo archivo en memoria
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Procesar cada hoja
            for sheet_name in excel_file.sheet_names:
                try:
                    # Leer la hoja (intentar con xlrd primero para .xls)
                    try:
                        df = pd.read_excel(template_path, sheet_name=sheet_name, header=None, engine='xlrd')
                    except:
                        df = pd.read_excel(template_path, sheet_name=sheet_name, header=None)
                    
                    # Verificar que el DataFrame tenga suficientes filas y columnas
                    num_filas = len(df)
                    num_cols = len(df.columns) if num_filas > 0 else 0
                    
                    # Actualizar datos en la hoja "RMIBI MENSUAL"
                    if sheet_name == "RMIBI MENSUAL" and num_filas > 48 and num_cols > 18:
                        # Actualizar mes y año (línea 14)
                        if num_filas > 14 and num_cols > 6:
                            if pd.notna(df.iloc[14, 1]) and "MES:" in str(df.iloc[14, 1]):
                                df.iloc[14, 2] = mes_nombre
                            if pd.notna(df.iloc[14, 5]) and "Año:" in str(df.iloc[14, 5]):
                                df.iloc[14, 6] = año
                        
                        # ACERVO BIBLIOGRÁFICO - EXISTENCIA TOTAL (línea 19)
                        if num_filas > 19 and num_cols > 3:
                            df.iloc[19, 2] = datos['acervo_existencia_titulos']  # Títulos
                            df.iloc[19, 3] = datos['acervo_existencia_volumenes']  # Volúmenes
                        
                        # ACERVO BIBLIOGRÁFICO - ADQUISICIONES (línea 20)
                        if num_filas > 20 and num_cols > 3:
                            df.iloc[20, 2] = datos['acervo_adquisiciones_titulos']  # Títulos
                            df.iloc[20, 3] = datos['acervo_adquisiciones_volumenes']  # Volúmenes
                        
                        # MATERIALES CONSULTADOS EN SALA (línea 25)
                        if num_filas > 25 and num_cols > 3:
                            df.iloc[25, 2] = datos['materiales_sala_titulos']
                            df.iloc[25, 3] = datos['materiales_sala_volumenes']
                        
                        # PRÉSTAMOS A DOMICILIO (línea 26)
                        if num_filas > 26 and num_cols > 3:
                            df.iloc[26, 2] = datos['prestamos_domicilio_titulos']
                            df.iloc[26, 3] = datos['prestamos_domicilio_volumenes']
                        
                        # TOTAL DE MATERIALES CONSULTADOS (línea 27)
                        if num_filas > 27 and num_cols > 3:
                            df.iloc[27, 2] = datos['total_materiales_consultados_titulos']
                            df.iloc[27, 3] = datos['total_materiales_consultados_volumenes']
                        
                        # USUARIOS ATENDIDOS (línea 36)
                        if num_filas > 36 and num_cols > 5:
                            df.iloc[36, 2] = datos['usuarios_atendidos_hombres']
                            df.iloc[36, 3] = datos['usuarios_atendidos_mujeres']
                            # USUARIOS INSCRITOS (línea 36, columnas 4-5)
                            df.iloc[36, 4] = datos['usuarios_inscritos_hombres']
                            df.iloc[36, 5] = datos['usuarios_inscritos_mujeres']
                        
                        # PERSONAL ADSCRITO (línea 48)
                        if num_filas > 48 and num_cols > 18:
                            # Directivo
                            df.iloc[48, 2] = datos['personal_directivo_hombres']
                            df.iloc[48, 3] = datos['personal_directivo_mujeres']
                            # Procesos Técnicos
                            df.iloc[48, 4] = datos['personal_procesos_tecnicos_hombres']
                            df.iloc[48, 5] = datos['personal_procesos_tecnicos_mujeres']
                            # Servicios al Público
                            df.iloc[48, 6] = datos['personal_servicios_publico_hombres']
                            df.iloc[48, 7] = datos['personal_servicios_publico_mujeres']
                            # Apoyo Bibliotecarios
                            if num_cols > 11:
                                df.iloc[48, 10] = datos['personal_apoyo_bibliotecarios_hombres']
                                df.iloc[48, 11] = datos['personal_apoyo_bibliotecarios_mujeres']
                            # Administrativo
                            if num_cols > 13:
                                df.iloc[48, 12] = datos['personal_administrativo_hombres']
                                df.iloc[48, 13] = datos['personal_administrativo_mujeres']
                            # Apoyo Administrativos
                            if num_cols > 15:
                                df.iloc[48, 14] = datos['personal_apoyo_administrativos_hombres']
                                df.iloc[48, 15] = datos['personal_apoyo_administrativos_mujeres']
                            # Otros
                            if num_cols > 17:
                                df.iloc[48, 16] = datos['personal_otros_hombres']
                                df.iloc[48, 17] = datos['personal_otros_mujeres']
                            # Total
                            if num_cols > 18:
                                df.iloc[48, 18] = datos['personal_total']
                    
                    # Escribir la hoja
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
                except Exception as e:
                    print(f"[REPORTE] Error al procesar hoja '{sheet_name}': {e}")
                    # Continuar con la siguiente hoja
                    continue
    except Exception as e:
        raise Exception(f"Error al generar el reporte Excel: {e}")
    
    output.seek(0)
    return output

@app.route('/api/informes/datos', methods=['GET'])
def api_informes_datos():
    """Obtiene los datos del reporte para mostrar en la tabla"""
    mes = request.args.get('mes', type=int)
    año = request.args.get('año', type=int)
    
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    datos = generar_datos_reporte_mensual(mes, año)
    
    # Formatear datos para la tabla
    meses_espanol = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    return jsonify({
        "mes": meses_espanol[mes],
        "año": año,
        "acervo": {
            "existencia_titulos": datos['acervo_existencia_titulos'],
            "existencia_volumenes": datos['acervo_existencia_volumenes'],
            "adquisiciones_titulos": datos['acervo_adquisiciones_titulos'],
            "adquisiciones_volumenes": datos['acervo_adquisiciones_volumenes']
        },
        "materiales_consultados": {
            "sala_titulos": datos['materiales_sala_titulos'],
            "sala_volumenes": datos['materiales_sala_volumenes'],
            "domicilio_titulos": datos['prestamos_domicilio_titulos'],
            "domicilio_volumenes": datos['prestamos_domicilio_volumenes'],
            "total_titulos": datos['total_materiales_consultados_titulos'],
            "total_volumenes": datos['total_materiales_consultados_volumenes']
        },
        "usuarios": {
            "atendidos_hombres": datos['usuarios_atendidos_hombres'],
            "atendidos_mujeres": datos['usuarios_atendidos_mujeres'],
            "atendidos_total": datos['usuarios_atendidos_total'],
            "inscritos_hombres": datos['usuarios_inscritos_hombres'],
            "inscritos_mujeres": datos['usuarios_inscritos_mujeres'],
            "inscritos_total": datos['usuarios_inscritos_total']
        },
        "personal": {
            "total": datos['personal_total']
        }
    })

@app.route('/api/informes/descargar', methods=['GET'])
def api_informes_descargar():
    """Genera y descarga el reporte Excel"""
    mes = request.args.get('mes', type=int)
    año = request.args.get('año', type=int)
    
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    try:
        output = generar_reporte_excel(mes, año)
        meses_espanol = ['', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
                         'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
        # Usar .xlsx porque openpyxl genera archivos Excel modernos
        filename = f"Reporte_RMIBI_{meses_espanol[mes]}_{año}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def generar_reporte_mensual_automatico():
    """Genera el reporte mensual automáticamente el día 28 de cada mes"""
    hoy = datetime.now()
    if hoy.day == 28:
        mes = hoy.month
        año = hoy.year
        try:
            # Generar el reporte
            output = generar_reporte_excel(mes, año)
            
            # Guardar el reporte en una carpeta de reportes
            reportes_dir = "reportes_mensuales"
            if not os.path.exists(reportes_dir):
                os.makedirs(reportes_dir)
            
            meses_espanol = ['', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
                             'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
            # Usar .xlsx porque openpyxl genera archivos Excel modernos
            filename = f"{reportes_dir}/Reporte_RMIBI_{meses_espanol[mes]}_{año}.xlsx"
            
            with open(filename, 'wb') as f:
                f.write(output.getvalue())
            
            print(f"[REPORTE] Reporte mensual generado automáticamente: {filename}")
        except Exception as e:
            print(f"[REPORTE] Error al generar reporte automático: {e}")

@app.route('/api/verificar_vencimientos', methods=['POST'])
def verificar_vencimientos():
    """Endpoint manual para verificar vencimientos y enviar correos"""
    try:
        verificar_y_actualizar_prestamos_vencidos()
        enviar_recordatorios_diarios()
        enviar_recordatorios_multas()
        limpiar_registros_antiguos()  # También limpiar registros antiguos
        return jsonify({"success": True, "message": "Verificación completada"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/eliminar_prestamo', methods=['POST'])
def eliminar_prestamo():
    datos = request.get_json() or {}
    prestamo_id = datos.get('prestamo_id')
    isbn = datos.get('isbn') or (datos.get('libro') or {}).get('isbn') or ''
    identificador = datos.get('id') or datos.get('boleta') or ''
    fecha_inicio = datos.get('fecha_inicio')

    # construir query para localizar préstamo activo
    query = {}
    if prestamo_id:
        try:
            query = {"_id": ObjectId(prestamo_id)}
        except Exception:
            query = {"_id": prestamo_id}
    else:
        # Buscar por ISBN y ID principalmente
        query = {"estado": {"$ne": "Devuelto"}}  # No devueltos
        if isbn:
            query["libro.isbn"] = isbn
        if identificador:
            query["id"] = str(identificador)
        if fecha_inicio:
            query["fecha_inicio"] = fecha_inicio

    prestamo = prestamos.find_one(query)
    if not prestamo:
        # intentar sin estado estricto pero manteniendo ISBN e ID
        alt = {}
        if isbn:
            alt["libro.isbn"] = isbn
        if identificador:
            alt["id"] = str(identificador)
        if fecha_inicio:
            alt["fecha_inicio"] = fecha_inicio
        if alt:
            prestamo = prestamos.find_one(alt)
        if not prestamo:
            return jsonify({"success": False, "error": "Préstamo no encontrado"}), 404

    try:
        # Eliminar el préstamo físicamente de la colección
        prestamos.delete_one({"_id": prestamo["_id"]})
        
        # Eliminar de devoluciones si existe
        devoluciones.delete_many({
            "$or": [
                {"prestamo_id": str(prestamo["_id"])},
                {"libro.isbn": prestamo.get('libro', {}).get('isbn', '')},
                {"id": prestamo.get('id', '')},
                {"libro.isbn": isbn, "id": str(identificador)}
            ]
        })

        # incrementar disponibles en inventario (buscar por ISBN, fallback por título)
        encontrado = None
        isbn_buscar = isbn or prestamo.get('libro', {}).get('isbn','')
        titulo_buscar = prestamo.get('libro', {}).get('titulo','')
        
        # Buscar por ISBN con múltiples variantes (con y sin guiones)
        if isbn_buscar:
            # Normalizar ISBN removiendo guiones y espacios
            isbn_clean = isbn_buscar.replace('-', '').replace(' ', '').strip()
            # Buscar con diferentes formatos de campo y variaciones del ISBN
            encontrado = inventario.find_one({
                "$or": [
                    {"ISBN": isbn_buscar},
                    {"Isbn": isbn_buscar},
                    {"isbn": isbn_buscar},
                    {"ISBN": isbn_clean},
                    {"Isbn": isbn_clean},
                    {"isbn": isbn_clean},
                    {"ISBN": {"$regex": f"^{isbn_buscar.replace('-', '[- ]?')}$", "$options": "i"}}
                ]
            })
        
        # Si no se encontró por ISBN, buscar por título
        if not encontrado and titulo_buscar:
            encontrado = inventario.find_one({
                "$or": [
                    {"TÍTULO": titulo_buscar},
                    {"TITULO": titulo_buscar},
                    {"Titulo": titulo_buscar},
                    {"titulo": titulo_buscar},
                    {"TÍTULO": {"$regex": titulo_buscar, "$options": "i"}}
                ]
            })

        incremented = None
        if encontrado:
            cur_val = None
            for k in ("DISPONIBLES","Disponibles","disponible","DISPONIBLE","Disponible"):
                if k in encontrado and encontrado.get(k) not in (None, ""):
                    try:
                        cur_val = int(encontrado.get(k))
                        break
                    except Exception:
                        cur_val = None
            if cur_val is None:
                try:
                    tmp = obtener_disponibles(encontrado)
                    if isinstance(tmp, int):
                        cur_val = tmp
                    elif isinstance(tmp, str) and tmp.isdigit():
                        cur_val = int(tmp)
                except Exception:
                    cur_val = None
            if cur_val is None:
                cur_val = 0
            nuevo = cur_val + 1
            inventario.update_one({"_id": encontrado["_id"]}, {"$set": {"DISPONIBLES": nuevo}})
            incremented = nuevo

        # recalcular contadores (mismo método que /api/dashboard)
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        try:
            prestamos_hoy = prestamos.count_documents({"created_at": {"$gte": start, "$lt": end}})
        except Exception:
            prestamos_hoy = 0

        libros_en_estanteria = 0
        for doc in inventario.find({}):
            v = None
            if "DISPONIBLES" in doc and doc.get("DISPONIBLES") not in (None, ""):
                try:
                    v = int(doc.get("DISPONIBLES"))
                except Exception:
                    v = None
            if v is None:
                for k in ("Disponibles","disponibles","DISPONIBLE","Disponible"):
                    if k in doc and doc.get(k) not in (None, ""):
                        try:
                            v = int(doc.get(k)); break
                        except Exception:
                            v = None
            if v is None:
                try:
                    tmp = obtener_disponibles(doc)
                    if isinstance(tmp, int):
                        v = tmp
                    elif isinstance(tmp, str) and tmp.isdigit():
                        v = int(tmp)
                except Exception:
                    v = None
            if isinstance(v, int) and v > 0:
                libros_en_estanteria += v

        return jsonify({
            "success": True,
            "prestamos_hoy": prestamos_hoy,
            "libros_estanteria": libros_en_estanteria,
            "incremented_disponibles": incremented
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
def tarea_periodica():
    """Tarea que se ejecuta periódicamente para verificar vencimientos, enviar correos y limpiar registros antiguos"""
    # Esperar 1 hora antes de la primera ejecución para evitar envíos al iniciar
    print("[TAREA PERIÓDICA] Esperando 1 hora antes de la primera verificación...")
    time.sleep(3600)  # Esperar 1 hora (3600 segundos)
    
    while True:
        try:
            print("[TAREA PERIÓDICA] Ejecutando verificación periódica...")
            # Verificar préstamos vencidos y crear/actualizar multas
            verificar_y_actualizar_prestamos_vencidos()
            # Enviar recordatorios diarios
            enviar_recordatorios_diarios()
            # Enviar recordatorios de multas
            enviar_recordatorios_multas()
            # Limpiar registros de sitio con más de 1 mes
            limpiar_registros_antiguos()
            # Generar reporte mensual automáticamente el día 28
            generar_reporte_mensual_automatico()
            print("[TAREA PERIÓDICA] Verificación completada. Próxima ejecución en 24 horas.")
        except Exception as e:
            print(f"[TAREA PERIÓDICA] Error: {e}")
        # Esperar 24 horas (86400 segundos) antes de ejecutar nuevamente
        time.sleep(86400)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
