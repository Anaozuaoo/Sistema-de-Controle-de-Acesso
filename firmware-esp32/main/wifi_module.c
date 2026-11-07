#include "wifi_module.h"
#include "config.h"
#include "esp_wifi.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "mdns.h"

static const char *TAG = "WIFI";

// Função que escuta os eventos de rede Wi-Fi e IP
static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Desconectado da rede Wi-Fi. Tentando reconectar...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "Conectado com sucesso! Endereço IP: " IPSTR, IP2STR(&event->ip_info.ip));
    }
}

void iniciar_wifi(void) {
    // 1. Inicializa a memória não-volátil (NVS) - Necessário para RF e calibração
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 2. Prepara a infraestrutura de rede (LwIP)
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    // 3. Configura o Wi-Fi com valores padrão
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    // 4. Registra handlers para eventos de Wi-Fi e IP
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    // 5. Aplica SSID e Senha a partir de config.h
    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    
    // 6. Inicializa o rádio Wi-Fi
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "Módulo Wi-Fi iniciado. Aguardando concessão de IP...");

    // 7. Inicializa o serviço mDNS para resolução por nome local (ex: http://camera.local)
    esp_err_t err = mdns_init();
    if (err == ESP_OK) {
        mdns_hostname_set(MDNS_HOSTNAME);
        mdns_instance_name_set("ESP32-S3 Security Camera Node");
        ESP_LOGI(TAG, "Serviço mDNS ativo como http://%s.local", MDNS_HOSTNAME);
    } else {
        ESP_LOGW(TAG, "Falha ao inicializar mDNS (erro: %d)", err);
    }
}
