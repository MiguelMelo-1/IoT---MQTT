import streamlit as st
import pandas as pd
from datetime import datetime
import os
import paho.mqtt.client as mqtt
import json


# === CONFIGURAÇÃO INICIAL ===
st.set_page_config(page_title="🐥 Aviário MQTT", layout="centered")
st.title("🐥 Interface do Aviário MQTT")

# MQTT – tópicos e credenciais
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

# Estado global atual
ultimos_dados = {
    "temperatura": None,
    "humidade": None,
    "luminosidade": None,
    "gas": None,
    "ventoinha": None,
    "janela": None,
    "timestamp": None,
}

estado_atuadores = {
    "Ventoinhas": False,
    "Janelas": False,
}

# Criar pasta para histórico
os.makedirs("dados", exist_ok=True)
historico = []

# === MQTT CALLBACKS ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Ligação ao broker MQTT bem-sucedida")
        for topico in TOPICOS_SUB:
            client.subscribe(topico)
            print(f"📡 Subscrito ao tópico: {topico}")
    else:
        print(f"❌ Erro na ligação MQTT. Código: {rc}")

def on_message(client, userdata, msg):
    global ultimos_dados
    try:
        payload = msg.payload.decode()
        print(f"📥 Tópico recebido: {msg.topic} | Conteúdo: {payload}")

        if msg.topic == "aviario/temperatura":
            ultimos_dados["temperatura"] = float(payload)
        elif msg.topic == "aviario/humidade":
            ultimos_dados["humidade"] = float(payload)
        elif msg.topic == "aviario/luminosidade":
            ultimos_dados["luminosidade"] = int(payload)
        elif msg.topic == "aviario/gas":
            ultimos_dados["gas"] = bool(int(payload))
        elif msg.topic == "aviario/ventoinha":
            ultimos_dados["ventoinha"] = bool(int(payload))
        elif msg.topic == "aviario/janela":
            ultimos_dados["janela"] = bool(int(payload))

        ultimos_dados["timestamp"] = datetime.now().strftime("%H:%M:%S")

        # Print estado completo atualizado
        print("📊 Estado atualizado dos sensores e atuadores:")
        for k, v in ultimos_dados.items():
            print(f"  • {k.capitalize()}: {v}")
    except Exception as e:
        print("❌ Erro ao processar mensagem MQTT:", e)

# === MQTT CLIENT ===
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

# === INTERFACE ===
st.subheader("📡 Leitura Atual dos Sensores")

if True:
    st.write(f"🌡️ Temperatura: {ultimos_dados['temperatura']} ºC")
    st.write(f"💧 Humidade: {ultimos_dados['humidade']} %")
    st.write(f"💡 Luminosidade: {ultimos_dados['luminosidade']}")
    st.write(f"🚨 Gás Detetado: {'Sim' if ultimos_dados['gas'] else 'Não'}")
    st.write(f"🌀 Ventoinha: {'Ligada' if ultimos_dados['ventoinha'] else 'Desligada'}")
    st.write(f"🖼️ Janela: {'Aberta' if ultimos_dados['janela'] else 'Fechada'}")
    st.write(f"⏱️ Última atualização: {ultimos_dados['timestamp']}")
else:
    st.warning("⚠️ À espera de dados MQTT...")

# === CONTROLO MANUAL ===
st.subheader("🛠️ Controlo Manual dos Atuadores")

def publicar_estado():
    payload = {
        "ventoinha": 1 if estado_atuadores["Ventoinhas"] else 0,
        "janela": 1 if estado_atuadores["Janelas"] else 0
    }
    client.publish("aviario/atuadores", json.dumps(payload))

estado_atuadores["Ventoinhas"] = st.toggle("🌀 Ventoinhas", value=estado_atuadores["Ventoinhas"], on_change=publicar_estado)
estado_atuadores["Janelas"] = st.toggle("🖼️ Janelas", value=estado_atuadores["Janelas"], on_change=publicar_estado)

# === HISTÓRICO ===
if ultimos_dados["temperatura"] is not None:
    registo = {
        "Hora": ultimos_dados["timestamp"],
        "Temperatura": ultimos_dados["temperatura"],
        "Humidade": ultimos_dados["humidade"],
        "Luminosidade": ultimos_dados["luminosidade"],
        "Gás": "Sim" if ultimos_dados["gas"] else "Não",
        "Ventoinhas": "Ligadas" if ultimos_dados["ventoinha"] else "Desligadas",
        "Janelas": "Abertas" if ultimos_dados["janela"] else "Fechadas"
    }
    historico.append(registo)

    df = pd.DataFrame(historico)
    df.to_csv("dados/registos_aviario.csv", index=False)

    st.subheader("📈 Histórico")
    st.line_chart(df[["Temperatura", "Humidade", "Luminosidade"]])
    st.dataframe(df.tail(10))
