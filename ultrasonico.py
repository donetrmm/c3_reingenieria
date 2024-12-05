from gpiozero import DistanceSensor
import socketio
import time
import requests
from datetime import datetime, timedelta
import pytz
import statistics
import threading

websocket_url = 'http://54.198.117.11'  
sio = socketio.Client()

sensor = DistanceSensor(echo=24, trigger=23, max_distance=6)  

personas_contadas = 0
ventana_lecturas = []  
persona_deteccionada = False
DEBOUNCE_TIME = 0.5  

personas_lock = threading.Lock()

def enviar_websocket():
    try:
        sio.connect(websocket_url)
        sio.emit('personasDentro', 12345) 
        print("Mensaje enviado al WebSocket")
        sio.disconnect()
    except Exception as e:
        print(f"Error al enviar mensaje al WebSocket: {e}")

def enviar_peticion_post():
    global personas_contadas
    timezone = pytz.timezone("America/Mexico_City")
    now = datetime.now(timezone)

    with personas_lock:
        registro_personas_adentro = {
            "fecha": now.strftime("%Y-%m-%d"),
            "hora": now.strftime("%H:00"),
            "numero_personas": personas_contadas,
            "lugar": "adentro",
            "idKit": 12345
        }
        personas_contadas = 0

    api_url = 'http://107.23.14.43/registro'
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(api_url, headers=headers, json=registro_personas_adentro)
        if response.status_code == 200:
            print("Petición POST enviada exitosamente.")
        else:
            print(f"Error en la solicitud POST: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error al enviar la petición POST: {e}")

def detectar_persona(distancia):
    global ventana_lecturas, personas_contadas, persona_deteccionada

    ventana_lecturas.append(distancia)
    if len(ventana_lecturas) > 2:
        ventana_lecturas.pop(0)

    if len(ventana_lecturas) >= 2:
        cambio_max = max(ventana_lecturas) - min(ventana_lecturas)
        desviacion = statistics.stdev(ventana_lecturas)

        if cambio_max > 30 and desviacion > 5 and not persona_deteccionada:
            persona_deteccionada = True
            with personas_lock:
                personas_contadas += 1
            print(f"¡Persona detectada! Número de personas contadas: {personas_contadas}")
            enviar_websocket()

        if cambio_max < 2 and persona_deteccionada:
            persona_deteccionada = False
            print("Persona salió del área de detección.")

def monitorizar_distancia():
    while True:
        distancia = sensor.distance * 100  
        print(f"Distancia detectada: {distancia:.2f} cm")

        detectar_persona(distancia)

        time.sleep(DEBOUNCE_TIME)

def enviar_datos_cada_hora():
    timezone = pytz.timezone("America/Mexico_City")
    while True:
        now = datetime.now(timezone)
        proxima_hora = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        tiempo_para_esperar = (proxima_hora - now).total_seconds()
        print(f"Esperando {tiempo_para_esperar:.2f} segundos para el próximo envío a la hora: {proxima_hora.strftime('%H:%M')}")

        time.sleep(tiempo_para_esperar)

        enviar_peticion_post()

def main():
    hilo_sensor = threading.Thread(target=monitorizar_distancia)
    hilo_post = threading.Thread(target=enviar_datos_cada_hora)

    hilo_sensor.start()
    hilo_post.start()

    hilo_sensor.join()
    hilo_post.join()

if __name__ == "__main__":
    main()
