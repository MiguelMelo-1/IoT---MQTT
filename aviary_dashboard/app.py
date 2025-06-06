import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import threading
from firebase_admin import db

from firebase import guardar_dados_em_firebase

# --- Configuração da Aplicação Flask ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma_chave_secreta_muito_segura_e_longa_para_o_aviario_2025'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Configuração MQTT ---
BROKER = "test.mosquitto.org"
PORT = 1883
TOPICOS_SUB = [
    "aviario/temperatura",
    "aviario/humidade",
    "aviario/luminosidade",
    "aviario/gas",
    "aviario/ventoinha",
    "aviario/janela",
]
TOPICO_VENTOINHA_SET = "aviario/atuadores/ventoinha/set"
TOPICO_JANELA_SET = "aviario/atuadores/janela/set"

current_state = {
    "temperatura": None,
    "humidade": None,
    "luminosidade": None,
    "gas": None,
    "ventoinha": False,
    "janela": False,
    "timestamp": None,
}

# --- Callbacks MQTT ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado ao broker MQTT.")
        for topico in TOPICOS_SUB:
            client.subscribe(topico)
            print(f"📡 Subscrito: {topico}")
    else:
        print(f"❌ Falha na conexão MQTT com código: {rc}")

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode('utf-8')
    print(f"📥 MQTT Recebido: Tópico='{msg.topic}', Payload='{payload_str}'")

    try:
        if msg.topic == "aviario/temperatura":
            current_state["temperatura"] = float(payload_str)
        elif msg.topic == "aviario/humidade":
            current_state["humidade"] = float(payload_str)
        elif msg.topic == "aviario/luminosidade":
            current_state["luminosidade"] = int(payload_str)
        elif msg.topic == "aviario/gas":
            current_state["gas"] = bool(int(payload_str))
        elif msg.topic == "aviario/ventoinha":
            current_state["ventoinha"] = bool(int(payload_str))
        elif msg.topic == "aviario/janela":
            current_state["janela"] = bool(int(payload_str.strip()))

        current_state["timestamp"] = datetime.now().strftime("%H:%M:%S")

        guardar_dados_em_firebase(current_state)

        socketio.emit('new_sensor_data', current_state)
        print(f"📦 Conteúdo emitido: {current_state}")

    except ValueError as e:
        print(f"❌ Erro de conversão de payload: {e} - Payload: '{payload_str}' (Tópico: {msg.topic})")
    except Exception as e:
        print(f"❌ Erro ao processar mensagem MQTT na callback: {e}")

# --- Inicialização do Cliente MQTT ---
mqtt_client = mqtt.Client(client_id=f"flask-app-{os.getenv('GAE_INSTANCE', 'dev')}-{os.getpid()}")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt_client():
    try:
        mqtt_client.connect(BROKER, PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"❌ Erro fatal ao iniciar loop MQTT: {e}")

mqtt_thread = threading.Thread(target=start_mqtt_client)
mqtt_thread.daemon = True
mqtt_thread.start()
print("🚀 Thread MQTT iniciada.")

# --- Rotas Flask ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/historico')
def get_historico():
    try:
        ref = db.reference('aviario/historico')
        all_data = ref.order_by_key().limit_to_last(15).get()
        # Inverter para ordem cronológica (mais antigo primeiro)
        if isinstance(all_data, dict):
            lista_ordenada = sorted(all_data.items(), key=lambda x: x[0])
            return jsonify([item[1] for item in lista_ordenada])
        return jsonify([])
    except Exception as e:
        print(f"❌ Erro ao ler histórico do Firebase: {e}")
        return jsonify([]), 500

# --- Eventos SocketIO ---
@socketio.on('connect')
def handle_connect():
    print(f"🔗 Cliente WebSocket conectado: {request.sid}")
    emit('new_sensor_data', current_state)
    print("📤 SocketIO Emitido (on_connect): new_sensor_data")
    print(f"📦 Conteúdo emitido: {current_state}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Cliente WebSocket desconectado: {request.sid}")

@socketio.on('toggle_actuator')
def handle_toggle_actuator(data):
    actuator_type = data.get('type')
    new_state = int(data.get('state'))

    print(f"⚡ Pedido de toggle para {actuator_type}: {new_state}")

    if actuator_type == "ventoinha":
        mqtt_client.publish(TOPICO_VENTOINHA_SET, str(new_state))
    elif actuator_type == "janela":
        mqtt_client.publish(TOPICO_JANELA_SET, str(new_state))
    else:
        print(f"⚠️ Atuador desconhecido: {actuator_type}")

# if __name__ == '__main__':
#     print("⚠️ Executando localmente com socketio.run().")
#     socketio.run(app, debug=True, host='127.0.0.1', port=5000, allow_unsafe_werkzeug=True)
