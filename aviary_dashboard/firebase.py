import firebase_admin 
from firebase_admin import credentials, db
from datetime import datetime
import uuid

cred = credentials.Certificate("aviario-cloud-firebase-adminsdk-fbsvc-8c884a6463.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://aviario-cloud-default-rtdb.europe-west1.firebasedatabase.app/'
})

def ler_dados_aviario():
    ref = db.reference('aviario/sensores')
    return ref.get()

def guardar_dados_em_firebase(dados):
    ref = db.reference('aviario/sensores')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = f"{timestamp}_{uuid.uuid4().hex[:6]}"

    ref = db.reference("aviario/historico")
    ref.child(unique_id).set(dados)
    ref.push(dados)