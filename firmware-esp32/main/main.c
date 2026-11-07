#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "camera_module.h"
#include "wifi_module.h"
#include "server_module.h"
#include "sd_module.h"
#include "radar_module.h"

void app_main(void) {
    printf("Iniciando o sistema...\n");

    iniciar_wifi();
    vTaskDelay(2000 / portTICK_PERIOD_MS); 

    iniciar_sd(); // Inicia o Cartão SD
    iniciar_radar(); // Inicia o Radar na UART1

    if (iniciar_camera() == 0) {
        printf("Hardware da câmera pronto!\n");
        
        // Inicia o servidor Web somente se a câmera funcionou
        iniciar_servidor();
    } else {
        printf("Falha na câmera.\n");
    }

    // Isso impede que o app_main termine, mantendo o ESP32 focado nas requisições HTTP
    while(1) {
        vTaskDelay(1000 / portTICK_PERIOD_MS);
    }
}