#include "sd_module.h"
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "driver/sdmmc_host.h"
#include "sdmmc_cmd.h"

static const char *TAG = "SD_CARD";

#define MOUNT_POINT "/sdcard"

// Pinos nativos do slot SD na placa Freenove ESP32-S3 WROOM
#define PIN_CMD 38
#define PIN_CLK 39
#define PIN_D0  40

bool cartao_pronto = false;
sdmmc_card_t *card = NULL;

esp_err_t iniciar_sd(void) {
    ESP_LOGI(TAG, "Tentando montar o Cartão SD...");

    esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = false,
        .max_files = 5,
        .allocation_unit_size = 16 * 1024
    };

    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    // Forçar modo de 1-bit para usar apenas os pinos essenciais
    host.flags = SDMMC_HOST_FLAG_1BIT;

    sdmmc_slot_config_t slot_config = SDMMC_SLOT_CONFIG_DEFAULT();
    slot_config.width = 1; // 1-bit
    slot_config.cmd = PIN_CMD;
    slot_config.clk = PIN_CLK;
    slot_config.d0 = PIN_D0;

    esp_err_t ret = esp_vfs_fat_sdmmc_mount(MOUNT_POINT, &host, &slot_config, &mount_config, &card);
    if (ret != ESP_OK) {
        if (ret == ESP_FAIL) {
            ESP_LOGW(TAG, "Falha ao montar o sistema de arquivos FAT. Talvez precise formatar o SD.");
        } else {
            ESP_LOGW(TAG, "Cartao SD nao encontrado ou nao inserido (Erro: %s). O sistema funcionara sem ele.", esp_err_to_name(ret));
        }
        cartao_pronto = false;
        return ESP_OK; // Retornamos OK de propósito para não travar o programa principal
    }

    ESP_LOGI(TAG, "Cartão SD montado com sucesso!");
    sdmmc_card_print_info(stdout, card);
    cartao_pronto = true;

    // Criar arquivo com cabeçalho se não existir
    FILE* f = fopen(MOUNT_POINT "/historico.csv", "r");
    if (f == NULL) {
        f = fopen(MOUNT_POINT "/historico.csv", "w");
        if (f != NULL) {
            fprintf(f, "Data e Hora;Nome Identificado;Status do Acesso\n");
            fclose(f);
            ESP_LOGI(TAG, "Arquivo historico.csv criado no Cartão SD.");
        }
    } else {
        fclose(f);
    }

    return ESP_OK;
}

void gravar_no_sd(const char* data, const char* nome, const char* status) {
    if (!cartao_pronto) {
        ESP_LOGW(TAG, "Tentativa de gravação ignorada: Cartão SD não está pronto.");
        return;
    }

    FILE* f = fopen(MOUNT_POINT "/historico.csv", "a");
    if (f == NULL) {
        ESP_LOGE(TAG, "Falha ao abrir o arquivo historico.csv para gravação.");
        return;
    }

    fprintf(f, "%s;%s;%s\n", data, nome, status);
    fclose(f);
    ESP_LOGI(TAG, "Log salvo no SD: [%s] %s - %s", data, nome, status);
}
