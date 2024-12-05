import cv2
import torch
from tkinter import *
from PIL import Image, ImageTk
import socketio
import time
import requests
from datetime import datetime
import threading

sio = socketio.Client()
sio.connect('http://54.198.117.11')

model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
model.eval()

detected_persons = {}
hourly_count = {}
current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
last_request_time = None

RETENTION_TIME = 2
IOU_THRESHOLD = 0.005
POST_ENDPOINT = 'http://107.23.14.43/registro'
frame_interval = 2
frame_count = 0

read_lock = threading.Lock()
write_lock = threading.Lock()
read_count = 0

def calculate_iou(box1, box2):
    x1, y1, x2, y2 = box1
    x1_b, y1_b, x2_b, y2_b = box2
    xi1 = max(x1, x1_b)
    yi1 = max(y1, y1_b)
    xi2 = min(x2, x2_b)
    yi2 = min(y2, y2_b)
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    box1_area = (x2 - x1) * (y2 - y1)
    box2_area = (x2_b - x1_b) * (y2_b - y1_b)
    union_area = box1_area + box2_area - inter_area
    iou = inter_area / union_area
    return iou

def reader_lock():
    global read_count
    with read_lock:
        read_count += 1
        if read_count == 1:
            write_lock.acquire()  

def reader_unlock():
    global read_count
    with read_lock:
        read_count -= 1
        if read_count == 0:
            write_lock.release()  

def writer_lock():
    write_lock.acquire()

def writer_unlock():
    write_lock.release()

def detect_persons(frame):
    reader_lock()
    try:
        results = model(frame)
        persons = results.pandas().xyxy[0]
        persons = persons[persons['name'] == 'person']
    finally:
        reader_unlock()
    return persons

def update_detected_persons(persons):
    global detected_persons, hourly_count, current_hour

    writer_lock()
    try:
        current_time = time.time()
        current_persons = {}

        for _, row in persons.iterrows():
            person_id = (int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax']))
            found = False
            for detected_person in detected_persons.keys():
                if calculate_iou(detected_person, person_id) > IOU_THRESHOLD:
                    found = True
                    break

            current_persons[person_id] = current_time

            if not found:
                sio.emit('personasFuera', 12345)
                hourly_count[current_hour] = hourly_count.get(current_hour, 0) + 1

        keys_to_remove = [k for k, v in detected_persons.items() if (current_time - v) > RETENTION_TIME]
        for k in keys_to_remove:
            del detected_persons[k]

        detected_persons.update(current_persons)
    finally:
        writer_unlock()

def send_hourly_count():
    global current_hour, hourly_count, last_request_time

    writer_lock()
    try:
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        if now > current_hour:
            start_hour = current_hour
            person_count = hourly_count.get(start_hour, 0)

            data = {
                'hora': start_hour.strftime('%H:%M'),
                'fecha': start_hour.strftime('%Y-%m-%d'),
                'numero_personas': person_count,
                'lugar': "afuera",
                'idKit': 12345
            }
            response = requests.post(POST_ENDPOINT, json=data)
            print(f"Datos enviados: {data} - Respuesta: {response.status_code}")

            current_hour = now
            hourly_count[current_hour] = 0

            last_request_time = time.time()
    finally:
        writer_unlock()

def process_frame():
    global cap, person_count, lbl_counter, canvas, photo, frame_count

    ret, frame = cap.read()
    if ret:
        if frame_count % frame_interval == 0:
            persons = detect_persons(frame)
            threading.Thread(target=update_detected_persons, args=(persons,)).start()

            for _, row in persons.iterrows():
                x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

            person_count.set(f"Personas detectadas: {len(persons)}")

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_pil = Image.fromarray(frame_rgb)
            photo = ImageTk.PhotoImage(image=frame_pil)

            canvas.create_image(0, 0, anchor=NW, image=photo)
        
        frame_count += 1
        if datetime.now().minute == 0 and datetime.now().second < 10:
            threading.Thread(target=send_hourly_count).start()

    window.after(10, process_frame)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

window = Tk()
window.title("Detección de Personas con YOLOv5")

canvas = Canvas(window, width=320, height=240)
canvas.pack()

person_count = StringVar()
person_count.set("Personas detectadas: 0")
lbl_counter = Label(window, textvariable=person_count)
lbl_counter.pack()

process_frame()

window.mainloop()

cap.release()
cv2.destroyAllWindows()
sio.disconnect()
