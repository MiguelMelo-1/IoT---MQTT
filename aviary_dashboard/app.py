import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import pandas as pd
import threading # Para gerir a thread MQTT

# --- Configuração da Aplicação Flask ---
app = Flask(__name__)
# A chave secreta é necessária para segurança de sessão do Flask-SocketIO
# Em produção, usa uma chave mais complexa e segura (variável de ambiente)
app.config['SECRET_KEY'] = 'uma_chave_secreta_muito_segura_e_longa_para_o_aviario_2025'
# Configura o SocketIO para permitir conexões de qualquer origem (útil para desenvolvimento)
# Em produção, restringe para o teu domínio.
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
TOPICO_ATUADORES_CONTROLO = "aviario/atuadores/controlo" # Tópico para controlar atuadores
TOPICO_ATUADORES_ESTADO_VENTOINHA = "aviario/atuadores/ventoinha_estado" # O ESP32 deve publicar aqui o estado atual
TOPICO_ATUADORES_ESTADO_JANELA = "aviario/atuadores/janela_estado" # O ESP32 deve publicar aqui o estado atual

# --- Variáveis de Estado Global (Acessíveis pelo Thread MQTT e Flask) ---
# Usamos um Lock para proteger 'current_sensor_data' e 'history_records'
# de acessos simultâneos por diferentes threads.
data_lock = threading.Lock()
current_sensor_data = {
    "temperatura": None,
    "humidade": None,
    "luminosidade": None,
    "gas": None,
    "ventoinha": None, # Estado atual do atuador (recebido do ESP32 ou localmente)
    "janela": None,    # Estado atual do atuador (recebido do ESP32 ou localmente)
    "timestamp": None,
}
history_records = [] # Armazena dados para o CSV e gráficos

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
    global current_sensor_data, history_records
    payload_str = msg.payload.decode('utf-8')
    print(f"📥 MQTT Recebido: Tópico='{msg.topic}', Payload='{payload_str}'")

    with data_lock: # Protege o acesso aos dados globais
        try:
            if msg.topic == "aviario/temperatura":
                current_sensor_data["temperatura"] = float(payload_str)
            elif msg.topic == "aviario/humidade":
                current_sensor_data["humidade"] = float(payload_str)
            elif msg.topic == "aviario/luminosidade":
                current_sensor_data["luminosidade"] = int(payload_str)
            elif msg.topic == "aviario/gas":
                # Assume 0 para "Não" e 1 para "Sim"
                current_sensor_data["gas"] = bool(int(payload_str))
            elif msg.topic == "aviario/ventoinha":
                current_sensor_data["ventoinha"] = bool(int(payload_str))
            elif msg.topic == "aviario/janela":
                current_sensor_data["janela"] = bool(int(payload_str))

            current_sensor_data["timestamp"] = datetime.now().strftime("%H:%M:%S")

            # --- Gerar Histórico ---
            # Para o histórico, queremos um snapshot dos dados dos sensores
            # quando eles estiverem disponíveis.
            # Verificamos se os principais dados de sensor estão presentes antes de registrar
            if all(current_sensor_data[k] is not None for k in ["temperatura", "humidade", "luminosidade", "gas"]):
                record = {
                    "Hora": current_sensor_data["timestamp"],
                    "Temperatura": current_sensor_data["temperatura"],
                    "Humidade": current_sensor_data["humidade"],
                    "Luminosidade": current_sensor_data["luminosidade"],
                    "Gás": "Sim" if current_sensor_data["gas"] else "Não",
                    "Ventoinhas_Estado": "Ligadas" if current_sensor_data["ventoinha"] else "Desligadas",
                    "Janelas_Estado": "Abertas" if current_sensor_data["janela"] else "Fechadas"
                }
                # Evitar duplicados se a mensagem for muito frequente e os dados não mudarem
                if not history_records or history_records[-1] != record:
                    history_records.append(record)
                    # Opcional: Limitar o tamanho do histórico na memória para não consumir muita RAM
                    # Ex: manter apenas os últimos 1000 registos
                    # if len(history_records) > 1000:
                    #     history_records.pop(0)

                    # Salvar em CSV (pode ser feito menos frequentemente para performance, ex: a cada 1min)
                    try:
                        df_history = pd.DataFrame(history_records)
                        # Garante que a pasta 'dados' existe
                        os.makedirs("dados", exist_ok=True)
                        df_history.to_csv("dados/historico_aviario.csv", index=False)
                    except Exception as csv_e:
                        print(f"❌ Erro ao salvar histórico em CSV: {csv_e}")

            # Enviar dados atualizados para todos os clientes WebSocket conectados
            # Usamos uma cópia para evitar que o dicionário seja modificado durante a serialização
            socketio.emit('new_sensor_data', current_sensor_data.copy())
            print("📤 SocketIO Emitido: new_sensor_data")

        except ValueError as e:
            print(f"❌ Erro de conversão de payload: {e} - Payload: '{payload_str}'")
        except Exception as e:
            print(f"❌ Erro ao processar mensagem MQTT na callback: {e}")

# --- Inicialização do Cliente MQTT ---
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt_client():
    try:
        mqtt_client.connect(BROKER, PORT, 60)
        mqtt_client.loop_forever() # Bloqueia, então deve estar numa thread
    except Exception as e:
        print(f"❌ Erro fatal ao iniciar loop MQTT: {e}")

# Iniciar o cliente MQTT em um thread separado
mqtt_thread = threading.Thread(target=start_mqtt_client)
mqtt_thread.daemon = True # Permite que o programa saia mesmo que este thread esteja a correr
mqtt_thread.start()
print("🚀 Thread MQTT iniciada.")

# --- Rotas Flask ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Eventos SocketIO ---
@socketio.on('connect')
def handle_connect():
    print(f"🔗 Cliente WebSocket conectado: {request.sid}")
    with data_lock: # Envia o estado atual dos sensores ao novo cliente conectado
        emit('new_sensor_data', current_sensor_data.copy())
    
    # Enviar os últimos N registos do histórico ao conectar
    with data_lock:
        if history_records:
            # Envia os últimos 20 registos para evitar sobrecarga inicial
            emit('initial_history', history_records[-20:]) 
        print("📤 SocketIO Emitido: initial_history para novo cliente.")


@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Cliente WebSocket desconectado: {request.sid}")

@socketio.on('toggle_actuator')
def handle_toggle_actuator(data):
    # data deve ser um dicionário como {'type': 'ventoinha', 'state': 1}
    actuator_type = data.get('type')
    new_state = int(data.get('state')) # Convert to int (0 or 1)
    
    print(f"⚡ Recebido pedido de toggle para {actuator_type}: {new_state}")

    if actuator_type in ["ventoinha", "janela"]:
        # Publica no tópico de controlo para o ESP32
        # É uma boa prática ter um tópico para cada atuador se for para controlar individualmente
        # ou um tópico geral e um payload JSON mais complexo
        
        # Exemplo com tópico específico para cada atuador:
        mqtt_client.publish(f"aviario/atuadores/{actuator_type}/set", str(new_state))
        print(f"📤 MQTT Publicado: aviario/atuadores/{actuator_type}/set = {new_state}")

        # Opcional: Atualiza o estado localmente imediatamente para dar feedback rápido na UI
        # (Idealmente, esperaríamos a confirmação do ESP32 via MQTT, mas para feedback rápido é útil)
        with data_lock:
            current_sensor_data[actuator_type] = bool(new_state)
            current_sensor_data["timestamp"] = datetime.now().strftime("%H:%M:%S")
            socketio.emit('new_sensor_data', current_sensor_data.copy()) # Atualiza UI de todos

    else:
        print(f"⚠️ Atuador desconhecido: {actuator_type}")

# --- Ponto de Entrada para a Aplicação ---
if __name__ == '__main__':
    # Quando em ambiente de produção, não usar debug=True
    # Isso ativa o reloader, que pode causar a inicialização dupla da thread MQTT.
    # Para desenvolvimento, pode-se usar, mas estar ciente do warning sobre threads.
    print("Iniciando servidor Flask-SocketIO...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)