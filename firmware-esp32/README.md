# Firmware ESP32-S3 (Edge Sensor & Actuator Node)

Nó embarcado baseado no microcontrolador dual-core **ESP32-S3**, responsável pela captura e transmissão de vídeo MJPEG, leitura de telemetria do radar mmWave (HLK-LD2410C), registro off-line em cartão MicroSD e controle de atuadores físicos (relé de fechadura e LEDs de status).

---

## 🛠️ Arquitetura Interna (FreeRTOS Dual-Core)

O firmware aproveita a arquitetura multi-core do ESP32-S3 para garantir taxa de quadros fluida e tempo de resposta determinístico:

- **Core 0 (Controle & REST API - Porta 80):**
  - Servidor HTTP com rotas de comando (`/abrir`, `/negado`, `/analisando`, `/salvar_sd`, `/radar`).
  - Rota de captura estática sob demanda (`/capture`).
  - Monitoramento contínuo do botão físico de saída em GPIO 1.
  - Gravação de logs de auditoria no cartão MicroSD via SDMMC (1-bit).
  - Parser UART da telemetria do radar HLK-LD2410C (distância, zona e standby).
- **Core 1 (Streaming MJPEG de Baixa Latência - Porta 81):**
  - Servidor HTTP exclusivo para transmissão contínua de quadros da câmera OV2640/OV5640.
  - Mecanismo dinâmico de economia de energia/banda: se o radar não detecta alvos próximos, a taxa de quadros é reduzida para 1 FPS (*Standby*). Ao detectar aproximação na zona da porta, o FPS máximo é restaurado instantaneamente.

---

## 📌 Pinout & Conexões de Hardware

| Periférico | Função / Sinal | Pino GPIO ESP32-S3 |
| :--- | :--- | :--- |
| **Câmera** | D0 .. D7 | GPIO 11, 9, 8, 10, 12, 18, 17, 16 |
| **Câmera** | XCLK, PCLK, VSYNC, HREF | GPIO 15, 13, 6, 7 |
| **Câmera** | I2C (SCCB) SDA, SCL | GPIO 4, 5 |
| **Radar LD2410C** | UART1 TX (ESP) -> RX (Radar) | GPIO 47 |
| **Radar LD2410C** | UART1 RX (ESP) <- TX (Radar) | GPIO 21 |
| **Cartão MicroSD**| CMD, CLK, D0 (SDMMC 1-bit) | GPIO 38, 39, 40 |
| **Atuador / LED** | LED Verde / Relé Fechadura | GPIO 2 |
| **Atuador / LED** | LED Amarelo (Processando) | GPIO 42 |
| **Atuador / LED** | LED Vermelho (Bloqueado) | GPIO 41 |
| **Entrada** | Botão de Saída Físico (Pull-up) | GPIO 1 |

---

## ⚙️ Configuração

1. Copie o arquivo de exemplo de configuração:
   ```bash
   cp main/config.h.example main/config.h
   ```
2. Edite `main/config.h` e insira suas credenciais de rede e o token de acesso:
   ```c
   #define WIFI_SSID       "SEU_SSID_WIFI"
   #define WIFI_PASS       "SUA_SENHA_WIFI"
   #define TOKEN_SECRETO   "SEU_TOKEN_SECRETO"
   #define MDNS_HOSTNAME   "camera"
   ```

---

## 🚀 Compilação e Gravação

Utilizando o **ESP-IDF v5.x**:

```bash
# Configurar o alvo para ESP32-S3
idf.py set-target esp32s3

# Compilar o firmware
idf.py build

# Gravar na placa (substitua COMx pela sua porta serial)
idf.py -p COMx flash monitor
```
