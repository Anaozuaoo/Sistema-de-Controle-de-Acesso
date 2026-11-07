#include "camera_module.h"
#include "esp_camera.h"  // 1. Inclui a biblioteca oficial
#include "esp_log.h"

static const char *TAG = "CÂMERA";

esp_err_t iniciar_camera(void) {
    // 2. Configuração de pinos (aqui entram os pinos reais da sua placa)
    camera_config_t config;
    
    // Pinos de Dados do ESP32-S3 (Padrão WROOM/Freenove)
    config.pin_d0 = 11;
    config.pin_d1 = 9;
    config.pin_d2 = 8;
    config.pin_d3 = 10;
    config.pin_d4 = 12;
    config.pin_d5 = 18;
    config.pin_d6 = 17;
    config.pin_d7 = 16;
    
    // Pinos de Controle
    config.pin_xclk = 15;
    config.pin_pclk = 13;
    config.pin_vsync = 6;
    config.pin_href = 7;
    config.pin_sccb_sda = 4;
    config.pin_sccb_scl = 5;
    config.pin_pwdn = -1;
    config.pin_reset = -1; 
    
    // Frequência e Formato
    config.xclk_freq_hz = 20000000; //clock em 20MHz
    config.ledc_timer = LEDC_TIMER_0;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_VGA; 
    config.jpeg_quality = 20;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

    // 3. Inicialização
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Erro ao iniciar a câmera: 0x%x", err);
        return err;
    }
    
    // Pega o ponteiro de controle do sensor
    sensor_t * s = esp_camera_sensor_get();
    
    if (s != NULL) {
        // Força a ativação dos algoritmos automáticos de imagem
        s->set_whitebal(s, 1);       // 1 = Habilita Balanço de Branco
        s->set_awb_gain(s, 1);       // 1 = Habilita Ganho do Balanço de Branco
        s->set_wb_mode(s, 0);        // 0 = Modo Automático (tenta encontrar a luz)
        
        s->set_exposure_ctrl(s, 1);  // 1 = Habilita Exposição Automática
        s->set_gain_ctrl(s, 1);      // 1 = Habilita Ganho Automático (ISO)
        
        // Pequenos ajustes para melhorar a imagem padrão do OV5640
        s->set_brightness(s, 1);     // Aumenta um pouco o brilho base
        s->set_saturation(s, 1);     // Melhora as cores lavadas
    }

    ESP_LOGI(TAG, "Câmera inicializada com sucesso!");
    return ESP_OK;
}