idf_component_register(SRCS "main.c" "camera_module.c" "wifi_module.c" "server_module.c" "sd_module.c" "radar_module.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi nvs_flash esp_netif esp_event esp_psram esp_http_server mdns fatfs sdmmc)