import os
import cv2
from ultralytics import YOLO

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 1. Configuração do fluxo de vídeo do ESP32-S3
esp_ip = os.getenv("ESP32_IP", "camera.local")
esp_stream_port = os.getenv("ESP32_STREAM_PORT", "81")
url_stream = f"http://{esp_ip}:{esp_stream_port}/"

print("==================================================")
print(" DETECTOR DE OBJETOS YOLOv8 - STREAM ESP32-S3     ")
print("==================================================")
print(f"Conectando ao stream: {url_stream}")

# 2. Carrega o modelo YOLOv8 Nano (leve e otimizado para inferência local em tempo real)
print("Carregando modelo YOLOv8...")
modelo = YOLO('yolov8n.pt')

# 3. Conexão com o fluxo MJPEG
camera = cv2.VideoCapture(url_stream)

if not camera.isOpened():
    print(f"Erro: Não foi possível conectar ao ESP32 em {url_stream}.")
    print("Verifique se o ESP32 está ligado, conectado à rede e com o IP correto.")
    exit(1)

print("Stream conectado com sucesso! Pressione 'q' na janela de exibição para encerrar.")

# 4. Loop de inferência e exibição
while True:
    sucesso, frame = camera.read()
    if not sucesso:
        print("Aguardando próximo frame do stream...")
        continue

    # Classes filtradas: 0 = Pessoa | 15 = Gato | 16 = Cachorro
    resultados = modelo(frame, classes=[0, 15, 16], conf=0.5)

    # Anotações gráficas na imagem
    imagem_anotada = resultados[0].plot()

    cv2.imshow("Monitoramento de Objetos - YOLOv8", imagem_anotada)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

camera.release()
cv2.destroyAllWindows()
