#include "server_module.h"
#include "config.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h" 
#include "freertos/task.h"     
#include "driver/gpio.h"
#include <string.h>
#include <stdlib.h>
#include "sd_module.h"
#include "radar_module.h"

static const char *TAG = "SERVIDOR";

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

#define PINO_LED_VERDE 2
#define PINO_LED_AMARELO 42
#define PINO_LED_VERMELHO 41
#define PINO_BOTAO 1

void destrancar_porta(void) {
    gpio_set_level(PINO_LED_VERMELHO, 0); 
    gpio_set_level(PINO_LED_AMARELO, 0);  
    gpio_set_level(PINO_LED_VERDE, 1);    
    
    vTaskDelay(3000 / portTICK_PERIOD_MS); 
    
    gpio_set_level(PINO_LED_VERDE, 0);    
    gpio_set_level(PINO_LED_VERMELHO, 1); 
}

void tarefa_botao(void *pvParameters) {
    while(1) {
        if(gpio_get_level(PINO_BOTAO) == 0) { 
            ESP_LOGI(TAG, "Botão de saída físico pressionado! Liberando acesso...");
            destrancar_porta();
            vTaskDelay(1000 / portTICK_PERIOD_MS); 
        }
        vTaskDelay(100 / portTICK_PERIOD_MS); 
    }
}

// =========================================================
// ROTA: Captura de Foto Estática (/capture)
// =========================================================
static esp_err_t capture_handler(httpd_req_t *req) {
    char buf[100];
    
    // Autenticação pelo cabeçalho X-Auth-Token
    esp_err_t res_auth = httpd_req_get_hdr_value_str(req, "X-Auth-Token", buf, sizeof(buf));
    if (res_auth != ESP_OK || strcmp(buf, TOKEN_SECRETO) != 0) {
        httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "Acesso Negado! Token invalido ou ausente.");
        return ESP_FAIL;
    }

    // Captura o frame atual da câmera
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        ESP_LOGE(TAG, "Falha na captura da imagem");
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    // Configura o cabeçalho HTTP para imagem JPEG
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");

    // Envia o payload da foto
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    
    // Devolve o buffer da câmera
    esp_camera_fb_return(fb);
    return res;
}

// =========================================================
// ROTA: Streaming Contínuo MJPEG (Porta 81, /)
// =========================================================
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if(res != ESP_OK){ return res; }

    ESP_LOGI(TAG, "Iniciando transmissão de vídeo contínua...");

    while(true){
        // Se o radar determinou Standby (sem presença ativa recente),
        // reduzimos a taxa de quadros (FPS) para economizar processamento e banda Wi-Fi
        int delay_ms = 1; 
        if (radar_ativo && em_standby) {
            delay_ms = 1000; // ~1 FPS em modo de economia
        }

        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Falha na captura da câmera");
            res = ESP_FAIL;
            break;
        }

        res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        if(res == ESP_OK){
            size_t hlen = snprintf(part_buf, 64, _STREAM_PART, fb->len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if(res == ESP_OK){
            res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
        }

        esp_camera_fb_return(fb);
        vTaskDelay(delay_ms / portTICK_PERIOD_MS);

        if(res != ESP_OK){
            ESP_LOGI(TAG, "Cliente desconectado do stream de vídeo.");
            break;
        }
    }
    return res;
}

// =========================================================
// ROTA: Comando de Abertura (/abrir)
// =========================================================
esp_err_t abrir_porta_handler(httpd_req_t *req) {
    char buf[100];
    
    esp_err_t res = httpd_req_get_hdr_value_str(req, "X-Auth-Token", buf, sizeof(buf));
    
    if (res == ESP_OK && strcmp(buf, TOKEN_SECRETO) == 0) {
        ESP_LOGI(TAG, "Acesso autorizado remotamente. Acionando relé...");
        destrancar_porta();
        httpd_resp_sendstr(req, "Porta Destrancada com Sucesso!");
        return ESP_OK;
    }
    
    ESP_LOGW(TAG, "Tentativa de acesso bloqueada! Token incorreto ou ausente.");
    httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "Acesso Negado! Token invalido ou ausente.");
    return ESP_FAIL;
}

// =========================================================
// ROTA: Indicador de Processamento (/analisando)
// =========================================================
static esp_err_t processando_handler(httpd_req_t *req) {
    gpio_set_level(PINO_LED_VERMELHO, 0);
    gpio_set_level(PINO_LED_VERDE, 0);
    gpio_set_level(PINO_LED_AMARELO, 1); 
    httpd_resp_sendstr(req, "Luz amarela acesa (analisando)!");
    return ESP_OK;
}

// =========================================================
// ROTA: Indicador de Acesso Negado (/negado)
// =========================================================
static esp_err_t negado_handler(httpd_req_t *req) {
    ESP_LOGW(TAG, "Acesso Negado acionado via rede.");
    gpio_set_level(PINO_LED_AMARELO, 0); 
    gpio_set_level(PINO_LED_VERDE, 0);   
    gpio_set_level(PINO_LED_VERMELHO, 1); 
    httpd_resp_sendstr(req, "Acesso Negado!");
    return ESP_OK;
}

// Função utilitária para decodificar URL query params
void url_decode(char *str) {
    char *pstr = str, *buf = malloc(strlen(str) + 1), *pbuf = buf;
    while (*pstr) {
        if (*pstr == '%') {
            if (pstr[1] && pstr[2]) {
                int hex;
                sscanf(pstr + 1, "%2x", &hex);
                *pbuf++ = hex;
                pstr += 2;
            }
        } else if (*pstr == '+') {
            *pbuf++ = ' ';
        } else {
            *pbuf++ = *pstr;
        }
        pstr++;
    }
    *pbuf = '\0';
    strcpy(str, buf);
    free(buf);
}

// =========================================================
// ROTA: Registro de Log no Cartão SD (/salvar_sd)
// =========================================================
static esp_err_t salvar_sd_handler(httpd_req_t *req) {
    char buf[100];
    
    // Autenticação
    esp_err_t res = httpd_req_get_hdr_value_str(req, "X-Auth-Token", buf, sizeof(buf));
    if (res != ESP_OK || strcmp(buf, TOKEN_SECRETO) != 0) {
        httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "Acesso Negado!");
        return ESP_FAIL;
    }

    size_t buf_len = httpd_req_get_url_query_len(req) + 1;
    if (buf_len > 1) {
        char* query = malloc(buf_len);
        if (httpd_req_get_url_query_str(req, query, buf_len) == ESP_OK) {
            char param_data[50] = {0};
            char param_nome[50] = {0};
            char param_status[100] = {0};

            httpd_query_key_value(query, "data", param_data, sizeof(param_data));
            httpd_query_key_value(query, "nome", param_nome, sizeof(param_nome));
            httpd_query_key_value(query, "status", param_status, sizeof(param_status));

            url_decode(param_data);
            url_decode(param_nome);
            url_decode(param_status);

            gravar_no_sd(param_data, param_nome, param_status);
        }
        free(query);
    }
    
    httpd_resp_sendstr(req, "Salvo com sucesso no SD");
    return ESP_OK;
}

// =========================================================
// ROTA: Leitura de Telemetria do Radar mmWave (/radar)
// =========================================================
static esp_err_t radar_info_handler(httpd_req_t *req) {
    char json_response[150];
    snprintf(json_response, sizeof(json_response), 
             "{\"distancia\": %d, \"zona\": %d, \"ativo\": %s, \"estado\": %d, \"standby\": %s}", 
             distancia_atual, zona_atual, radar_ativo ? "true" : "false",
             estado_alvo, em_standby ? "true" : "false");
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, json_response);
    return ESP_OK;
}

// =========================================================
// INICIALIZAÇÃO DOS SERVIDORES HTTP (CORE 0 e CORE 1)
// =========================================================
void iniciar_servidor(void) {
    
    gpio_reset_pin(PINO_LED_VERDE);
    gpio_set_direction(PINO_LED_VERDE, GPIO_MODE_OUTPUT);
    
    gpio_reset_pin(PINO_LED_AMARELO);
    gpio_set_direction(PINO_LED_AMARELO, GPIO_MODE_OUTPUT);
    
    gpio_reset_pin(PINO_LED_VERMELHO);
    gpio_set_direction(PINO_LED_VERMELHO, GPIO_MODE_OUTPUT);

    gpio_reset_pin(PINO_BOTAO);
    gpio_set_direction(PINO_BOTAO, GPIO_MODE_INPUT);
    gpio_pullup_en(PINO_BOTAO); 
    
    gpio_set_level(PINO_LED_VERMELHO, 1);
    gpio_set_level(PINO_LED_VERDE, 0);
    gpio_set_level(PINO_LED_AMARELO, 0);
    
    xTaskCreate(tarefa_botao, "Botao Saida", 2048, NULL, 10, NULL);

    // 1. SERVIDOR DE CONTROLE REST E FOTO -> CORE 0
    httpd_config_t config_controle = HTTPD_DEFAULT_CONFIG();
    config_controle.server_port = 80; 
    config_controle.core_id = 0; 

    httpd_handle_t servidor_controle = NULL;

    if (httpd_start(&servidor_controle, &config_controle) == ESP_OK) {
        httpd_uri_t rota_capture = { .uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_capture);

        httpd_uri_t rota_porta = { .uri = "/abrir", .method = HTTP_GET, .handler = abrir_porta_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_porta);

        httpd_uri_t rota_amarelo = { .uri = "/analisando", .method = HTTP_GET, .handler = processando_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_amarelo);

        httpd_uri_t rota_negado = { .uri = "/negado", .method = HTTP_GET, .handler = negado_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_negado);

        httpd_uri_t rota_salvar_sd = { .uri = "/salvar_sd", .method = HTTP_GET, .handler = salvar_sd_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_salvar_sd);

        httpd_uri_t rota_radar = { .uri = "/radar", .method = HTTP_GET, .handler = radar_info_handler, .user_ctx = NULL };
        httpd_register_uri_handler(servidor_controle, &rota_radar);

        ESP_LOGI(TAG, "Servidor de Controle REST pronto no CORE 0 (Porta 80).");
    }

    // 2. SERVIDOR DE VÍDEO (Stream Contínuo MJPEG) -> CORE 1
    httpd_config_t config_stream = HTTPD_DEFAULT_CONFIG();
    config_stream.server_port = 81;
    config_stream.ctrl_port = 32769; 
    config_stream.core_id = 1;       

    httpd_handle_t servidor_stream = NULL;

    if (httpd_start(&servidor_stream, &config_stream) == ESP_OK) {
        httpd_uri_t rota_video = {
            .uri       = "/",
            .method    = HTTP_GET,
            .handler   = stream_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(servidor_stream, &rota_video);
        
        ESP_LOGI(TAG, "Servidor de Vídeo MJPEG pronto no CORE 1 (Porta 81).");
    }
}
