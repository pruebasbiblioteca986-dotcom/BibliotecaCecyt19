from flask import request, jsonify
from app import app, sitio
from bson.objectid import ObjectId

@app.route('/api/eliminar_sitio', methods=['POST'])
def eliminar_sitio():
    datos = request.get_json() or {}
    id_registro = datos.get('id', '')
    if not id_registro:
        return jsonify({'success': False, 'error': 'ID requerido'}), 400
    try:
        result = sitio.delete_one({'_id': ObjectId(id_registro)})
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Registro no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500