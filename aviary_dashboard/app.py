import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import pandas as pd
import threading

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
    "aviario/ventoinha", # Manter para receber o estado atual do atuador
    "aviario/janela",    # Manter para receber o estado atual do atuador
]
TOPICO_ATUADORES_CONTROLO = "aviario/atuadores/controlo" # Tópico para controlar atuadores (geral, se usares)
# Tópicos específicos para controlo que o ESP32 deve subscrever
TOPICO_VENTOINHA_SET = "aviario/atuadores/ventoinha/set"
TOPICO_JANELA_SET = "aviario/atuadores/janela/set"

# Definir quais tópicos são de 'sensor' para o histórico.
# Os tópicos de atuador que publicam o estado (aviario/ventoinha, aviario/janela)
# não devem estar aqui, pois queremos que só os dados dos sensores
# (temperatura, humidade, luminosidade, gás) gerem entradas de histórico.
SENSOR_TOPICS_FOR_HISTORY = [
    "aviario/temperatura",
    "aviario/humidade",
    "aviario/luminosidade",
    "aviario/gas",
]


# --- Variáveis de Estado Global (Acessíveis pelo Thread MQTT e Flask) ---
data_lock = threading.Lock()
current_sensor_data = {
    "temperatura": None,
    "humidade": None,
    "luminosidade": None,
    "gas": None,
    "ventoinha": None, # Estado atual do atuador (recebido do ESP32)
    "janela": None,    # Estado atual do atuador (recebido do ESP32)
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
            # Atualiza os dados de todos os tipos (sensores e atuadores)
            if msg.topic == "aviario/temperatura":
                current_sensor_data["temperatura"] = float(payload_str)
            elif msg.topic == "aviario/humidade":
                current_sensor_data["humidade"] = float(payload_str)
            elif msg.topic == "aviario/luminosidade":
                current_sensor_data["luminosidade"] = int(payload_str)
            elif msg.topic == "aviario/gas":
                current_sensor_data["gas"] = bool(int(payload_str))
            # Estes tópicos devem ser publicados pelo ESP32 com o estado real do atuador
            elif msg.topic == "aviario/ventoinha":
                current_sensor_data["ventoinha"] = bool(int(payload_str))
            elif msg.topic == "aviario/janela":
                current_sensor_data["janela"] = bool(int(payload_str))

            current_sensor_data["timestamp"] = datetime.now().strftime("%H:%M:%S")

            # --- Gerar Histórico SOMENTE para dados de sensores ---
            # Verifica se a mensagem veio de um dos tópicos de sensor definidos
            # E se todos os dados de sensor (temperatura, humidade, luminosidade, gás) estão disponíveis
            if msg.topic in SENSOR_TOPICS_FOR_HISTORY and \
               all(current_sensor_data[k] is not None for k in ["temperatura", "humidade", "luminosidade", "gas"]):
                
                record = {
                    "Hora": current_sensor_data["timestamp"],
                    "Temperatura": current_sensor_data["temperatura"],
                    "Humidade": current_sensor_data["humidade"],
                    "Luminosidade": current_sensor_data["luminosidade"],
                    "Gás": "Sim" if current_sensor_data["gas"] else "Não",
                    "Ventoinhas_Estado": "Ligadas" if current_sensor_data["ventoinha"] else "Desligadas",
                    "Janelas_Estado": "Abertas" if current_sensor_data["janela"] else "Fechadas"
                }
                
                # Evitar duplicados no histórico (ex: só adiciona se a hora ou temperatura mudou)
                # Esta lógica é um pouco mais robusta para evitar entradas idênticas consecutivas.
                if not history_records or \
                   history_records[-1]["Hora"] != record["Hora"] or \
                   history_records[-1]["Temperatura"] != record["Temperatura"] or \
                   history_records[-1]["Humidade"] != record["Humidade"] or \
                   history_records[-1]["Luminosidade"] != record["Luminosidade"] or \
                   history_records[-1]["Gás"] != record["Gás"]:
                    
                    history_records.append(record)

                    # Opcional: Limitar o tamanho do histórico na memória do backend para não consumir muita RAM
                    # Se tiveres muitos dados e estiveres a guardar no CSV, podes querer limitar isto também.
                    # if len(history_records) > 5000: # Ex: manter os últimos 5000 registos em memória
                    #     history_records.pop(0)

                    # Salvar em CSV (pode ser feito menos frequentemente para performance, ex: a cada 1min)
                    try:
                        df_history = pd.DataFrame(history_records)
                        os.makedirs("dados", exist_ok=True)
                        df_history.to_csv("dados/historico_aviario.csv", index=False)
                    except Exception as csv_e:
                        print(f"❌ Erro ao salvar histórico em CSV: {csv_e}")

            # Enviar DADOS ATUALIZADOS para todos os clientes WebSocket conectados
            # Isso é para TODOS os dados (sensores e atuadores) para a UI principal,
            # independentemente de virem de um sensor ou de um estado de atuador.
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
    actuator_type = data.get('type')
    new_state = int(data.get('state')) # Convert to int (0 or 1)
    
    print(f"⚡ Recebido pedido de toggle para {actuator_type}: {new_state}")

    if actuator_type == "ventoinha":
        # Publica o comando para o ESP32
        mqtt_client.publish(TOPICO_VENTOINHA_SET, str(new_state))
        print(f"📤 MQTT Publicado: {TOPICO_VENTOINHA_SET} = {new_state}")
    elif actuator_type == "janela":
        # Publica o comando para o ESP32
        mqtt_client.publish(TOPICO_JANELA_SET, str(new_state))
        print(f"📤 MQTT Publicado: {TOPICO_JANELA_SET} = {new_state}")
    else:
        print(f"⚠️ Atuador desconhecido: {actuator_type}")

    # Removido: A atualização da UI do atuador vai acontecer quando o ESP32
    # publicar o estado REAL do atuador nos tópicos "aviario/ventoinha" ou "aviario/janela".
    # Isso garante que a UI reflete sempre o estado físico do hardware.

# --- Ponto de Entrada para a Aplicação ---
if __name__ == '__main__':
    print("Iniciando servidor Flask-SocketIO...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)