import urllib.request, json
url='http://localhost:5000/api/registrar_prestamo'
payload={
  'tipo':'alumno',
  'id':'0001',
  'nombre':'Test Usuario',
  'correo':'destinatario@local',
  'libro':{'titulo':'Libro prueba','isbn':'000'}
}
data=json.dumps(payload).encode('utf-8')
req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
print(urllib.request.urlopen(req).read().decode())
