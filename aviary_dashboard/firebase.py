import firebase_admin 
from firebase_admin import credentials, db

cred = credentials.Certificate("aviary_dashboard/aviario-cloud-firebase-adminsdk-fbsvc-8c884a6463.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://aviario-cloud.firebaseio.com'
})

def ler_dados_aviario():
    ref = db.reference('aviario/sensores')
    return ref.get()

def guardar_dados_em_firebase(dados):
    ref = db.reference('aviario/sensores')
    ref.set(dados)