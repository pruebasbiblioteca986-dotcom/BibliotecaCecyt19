#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request, json

def get(url):
    with urllib.request.urlopen(url) as res:
        return json.load(res)

base = 'http://127.0.0.1:5000'

try:
    print('\nGET /api/dashboard')
    data2 = get(base + '/api/dashboard')
    print(json.dumps(data2, indent=2, ensure_ascii=False))
except Exception as e:
    print('Error fetching dashboard:', e)

try:
    print('\nGET /api/sitio')
    data3 = get(base + '/api/sitio')
    print('Registros sitio count:', len(data3.get('registros', data3 if isinstance(data3, list) else [])))
except Exception as e:
    print('Error fetching sitio:', e)
