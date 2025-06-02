import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import pandas as pd # Manter pandas por agora, mas vamos remover a escrita em CSV
import threading
import uuid

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
TOPICO_VENTOINHA_SET = "aviario/atuadores/ventoinha/set"
TOPICO_JANELA_SET = "aviario/atuadores/janela/set"

# Definir quais tópicos são de 'sensor' para o histórico (ainda usaremos isso para decidir o que registar, por enquanto).
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
    "ventoinha": False, # <--- Inicializa com um valor padrão (ex: False ou 0)
    "janela": False,    # <--- Inicializa com um valor padrão (ex: False ou 0)
    "timestamp": None,
}
# history_records foi removido daqui, pois 'current_sensor_data' é o que nos importa para o estado atual.
# Para o histórico a longo prazo, isso será gerido pela base de dados.

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
    global current_sensor_data # Não precisamos mais de 'history_records' aqui
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
                # --- NOVAS LINHAS PARA DEBUG DA VENTOINHA ---
                print(f"DEBUG - Ventoinha: Payload STR recebido: '{payload_str}' (Tipo: {type(payload_str)})")
                normalized_payload = payload_str.strip() # Remove espaços em branco
                print(f"DEBUG - Ventoinha: Payload STR normalizado: '{normalized_payload}'")
                
                # Tenta converter para int, depois para bool.
                # Se for "1", int("1") é 1, bool(1) é True.
                # Se for "0", int("0") é 0, bool(0) é False.
                # Se for "true" ou "false" (strings), precisas de uma lógica diferente.
                # Assumindo que o ESP32 envia "0" ou "1".
                current_sensor_data["ventoinha"] = bool(int(normalized_payload))
                print(f"DEBUG - Ventoinha: Valor convertido: {current_sensor_data['ventoinha']}")
                # --- FIM NOVAS LINHAS PARA DEBUG DA VENTOINHA ---

            elif msg.topic == "aviario/janela":
                # --- NOVAS LINHAS PARA DEBUG DA JANELA ---
                print(f"DEBUG - Janela: Payload STR recebido: '{payload_str}' (Tipo: {type(payload_str)})")
                normalized_payload = payload_str.strip() # Remove espaços em branco
                print(f"DEBUG - Janela: Payload STR normalizado: '{normalized_payload}'")
                current_sensor_data["janela"] = bool(int(normalized_payload))
                print(f"DEBUG - Janela: Valor convertido: {current_sensor_data['janela']}")
                # --- FIM NOVAS LINHAS PARA DEBUG DA JANELA ---

            current_sensor_data["timestamp"] = datetime.now().strftime("%H:%M:%S")

            # --- PARTE DO HISTÓRICO EM CSV - REMOVER OU COMENTAR ---
            # Como vamos passar para base de dados, estas linhas devem ser removidas ou
            # reescritas para interagir com a base de dados.
            # Por agora, para focar no problema da ventoinha/janela, vamos comentar.
            """
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
                
                # if not history_records or ... (lógica para evitar duplicados, não mais necessária para o histórico em memória)
                # history_records.append(record) # <-- Esta variável não existe mais globalmente

                try:
                    df_history = pd.DataFrame([record]) # Criar um DataFrame a partir do último record para fins de teste local, se necessário
                    # os.makedirs("dados", exist_ok=True) # <-- ESTA LINHA VAI SEMPRE FALHAR NO APP ENGINE
                    # df_history.to_csv("dados/historico_aviario.csv", mode='a', header=not os.path.exists("dados/historico_aviario.csv"), index=False)
                except Exception as csv_e:
                    print(f"❌ Erro ao salvar histórico em CSV: {csv_e}")
            """
            # --- FIM DA PARTE DO HISTÓRICO EM CSV ---

            # Enviar DADOS ATUALIZADOS para todos os clientes WebSocket conectados
            socketio.emit('new_sensor_data', current_sensor_data.copy())
            print("📤 SocketIO Emitido: new_sensor_data")
            print(f"📦 Conteúdo de current_sensor_data após atualização e emissão: {current_sensor_data}")

        except ValueError as e:
            print(f"❌ Erro de conversão de payload: {e} - Payload: '{payload_str}'")
        except Exception as e:
            print(f"❌ Erro ao processar mensagem MQTT na callback: {e}")

# --- Inicialização do Cliente MQTT ---
client_id = f"flask-app-{uuid.uuid4()}" 
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
    
    # A emissão de 'initial_history' também dependerá da base de dados no futuro.
    # Por agora, para teste, podes remover ou comentar esta parte.
    # print("📤 SocketIO Emitido: initial_history para novo cliente.")


@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Cliente WebSocket desconectado: {request.sid}")

@socketio.on('toggle_actuator')
def handle_toggle_actuator(data):
    actuator_type = data.get('type')
    new_state = int(data.get('state')) # Convert to int (0 or 1)
    
    print(f"⚡ Recebido pedido de toggle para {actuator_type}: {new_state}")

    with data_lock: # Atualiza o estado no backend imediatamente após receber o pedido
        if actuator_type == "ventoinha":
            mqtt_client.publish(TOPICO_VENTOINHA_SET, str(new_state))
            current_sensor_data["ventoinha"] = bool(new_state) # <--- Atualiza o estado localmente
            print(f"📤 MQTT Publicado: {TOPICO_VENTOINHA_SET} = {new_state}")
        elif actuator_type == "janela":
            mqtt_client.publish(TOPICO_JANELA_SET, str(new_state))
            current_sensor_data["janela"] = bool(new_state) # <--- Atualiza o estado localmente
            print(f"📤 MQTT Publicado: {TOPICO_JANELA_SET} = {new_state}")
        else:
            print(f"⚠️ Atuador desconhecido: {actuator_type}")
        
        # Emite os dados atualizados para o frontend, refletindo a mudança local
        socketio.emit('new_sensor_data', current_sensor_data.copy())
        print(f"📦 Conteúdo de current_sensor_data após toggle e emissão: {current_sensor_data}")

    # Removido: A atualização da UI do atuador vai acontecer quando o ESP32
    # publicar o estado REAL do atuador nos tópicos "aviario/ventoinha" ou "aviario/janela".
    # Isso garante que a UI reflete sempre o estado físico do hardware.

# --- Ponto de Entrada para a Aplicação ---
# if __name__ == '__main__':
#     print("Iniciando servidor Flask-SocketIO...")
#     socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)




# # app.py (tentativa 2: Flask-SocketIO + MQTT + Threading)
# import os # Necessário para os.makedirs()
# from flask import Flask, render_template, request, jsonify
# from flask_socketio import SocketIO, emit
# import paho.mqtt.client as mqtt # Reintroduz MQTT
# import json # Reintroduz JSON (para payloads MQTT)
# from datetime import datetime # Reintroduz datetime
# # import pandas as pd # AINDA NÃO! Comentar ou remover
# import threading # Reintroduz threading

# # --- Configuração da Aplicação Flask ---
# app = Flask(__name__)
# app.config['SECRET_KEY'] = 'uma_chave_secreta_muito_segura_e_longa_para_o_aviario_2025'
# socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# # --- Configuração MQTT ---
# # Usar variáveis de ambiente para o broker e porta é uma boa prática em cloud
# BROKER = os.environ.get("MQTT_BROKER_HOST", "test.mosquitto.org")
# PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))
# TOPICOS_SUB = [
#     "aviario/temperatura",
#     "aviario/humidade",
#     "aviario/luminosidade",
#     "aviario/gas",
#     "aviario/ventoinha",
#     "aviario/janela",
# ]
# TOPICO_VENTOINHA_SET = "aviario/atuadores/ventoinha/set"
# TOPICO_JANELA_SET = "aviario/atuadores/janela/set"
# SENSOR_TOPICS_FOR_HISTORY = [
#     "aviario/temperatura", "aviario/humidade",
#     "aviario/luminosidade", "aviario/gas",
# ]


# # --- Variáveis de Estado Global (Acessíveis pelo Thread MQTT e Flask) ---
# data_lock = threading.Lock()
# current_sensor_data = {
#     "temperatura": None, "humidade": None, "luminosidade": None, "gas": None,
#     "ventoinha": None, "janela": None, "timestamp": None,
# }
# history_records = []

# # --- Callbacks MQTT ---
# def on_connect(client, userdata, flags, rc):
#     if rc == 0:
#         print("✅ Conectado ao broker MQTT.")
#         for topico in TOPICOS_SUB:
#             client.subscribe(topico)
#             print(f"📡 Subscrito: {topico}")
#     else:
#         print(f"❌ Falha na conexão MQTT com código: {rc}")

# def on_message(client, userdata, msg):
#     global current_sensor_data, history_records
#     payload_str = msg.payload.decode('utf-8')
#     print(f"📥 MQTT Recebido: Tópico='{msg.topic}', Payload='{payload_str}'")

#     with data_lock:
#         try:
#             if msg.topic == "aviario/temperatura": current_sensor_data["temperatura"] = float(payload_str)
#             elif msg.topic == "aviario/humidade": current_sensor_data["humidade"] = float(payload_str)
#             elif msg.topic == "aviario/luminosidade": current_sensor_data["luminosidade"] = int(payload_str)
#             elif msg.topic == "aviario/gas": current_sensor_data["gas"] = bool(int(payload_str))
#             elif msg.topic == "aviario/ventoinha": current_sensor_data["ventoinha"] = bool(int(payload_str))
#             elif msg.topic == "aviario/janela": current_sensor_data["janela"] = bool(int(payload_str))

#             current_sensor_data["timestamp"] = datetime.now().strftime("%H:%M:%S")

#             # Sem Pandas aqui, então a parte de salvar CSV estará comentada
#             # if msg.topic in SENSOR_TOPICS_FOR_HISTORY and \
#             #    all(current_sensor_data[k] is not None for k in ["temperatura", "humidade", "luminosidade", "gas"]):
#             #    record = { ... } # A tua lógica de record
#             #    if not history_records or ...: # A tua lógica de evitar duplicados
#             #        history_records.append(record)
#             #        # Salvar em CSV (AGORA COMENTADO)
#             #        # try:
#             #        #    df_history = pd.DataFrame(history_records)
#             #        #    os.makedirs("dados", exist_ok=True)
#             #        #    df_history.to_csv("dados/historico_aviario.csv", index=False)
#             #        # except Exception as csv_e:
#             #        #    print(f"❌ Erro ao salvar histórico em CSV: {csv_e}")

#             socketio.emit('new_sensor_data', current_sensor_data.copy())
#             print("📤 SocketIO Emitido: new_sensor_data")

#         except ValueError as e:
#             print(f"❌ Erro de conversão de payload: {e} - Payload: '{payload_str}'")
#         except Exception as e:
#             print(f"❌ Erro ao processar mensagem MQTT na callback: {e}")

# # --- Inicialização do Cliente MQTT ---
# mqtt_client = mqtt.Client()
# mqtt_client.on_connect = on_connect
# mqtt_client.on_message = on_message

# def start_mqtt_client():
#     try:
#         mqtt_client.connect(BROKER, PORT, 60)
#         mqtt_client.loop_forever()
#     except Exception as e:
#         print(f"❌ Erro fatal ao iniciar loop MQTT: {e}")

# mqtt_thread = threading.Thread(target=start_mqtt_client)
# mqtt_thread.daemon = True
# mqtt_thread.start()
# print("🚀 Thread MQTT iniciada.")

# # --- Rotas Flask ---
# @app.route('/')
# def index():
#     return render_template('index.html')

# # --- Eventos SocketIO ---
# @socketio.on('connect')
# def handle_connect():
#     print(f"🔗 Cliente WebSocket conectado: {request.sid}")
#     with data_lock:
#         emit('new_sensor_data', current_sensor_data.copy())
#         # Emitir histórico inicial será feito quando o Pandas estiver ativo

# @socketio.on('disconnect')
# def handle_disconnect():
#     print(f"🔌 Cliente WebSocket desconectado: {request.sid}")

# @socketio.on('toggle_actuator')
# def handle_toggle_actuator(data):
#     actuator_type = data.get('type')
#     new_state = int(data.get('state'))

#     print(f"⚡ Recebido pedido de toggle para {actuator_type}: {new_state}")

#     if actuator_type == "ventoinha":
#         mqtt_client.publish(TOPICO_VENTOINHA_SET, str(new_state))
#         print(f"📤 MQTT Publicado: {TOPICO_VENTOINHA_SET} = {new_state}")
#     elif actuator_type == "janela":
#         mqtt_client.publish(TOPICO_JANELA_SET, str(new_state))
#         print(f"📤 MQTT Publicado: {TOPICO_JANELA_SET} = {new_state}")
#     else:
#         print(f"⚠️ Atuador desconhecido: {actuator_type}")

# # NADA DE if __name__ == '__main__': socketio.run(...)