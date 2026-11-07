#include "radar_module.h"
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "RADAR";

// Configurações da UART para o LD2410C
#define UART_RADAR UART_NUM_1
#define PIN_TX 47 // Liga no RX do Radar (Cabo de 25cm está OK)
#define PIN_RX 21 // Liga no TX do Radar (Cabo de 25cm está OK)
#define BUF_SIZE 256

int zona_atual = ZONA_NENHUMA;
int distancia_atual = 9999;
int estado_alvo = 0;
bool radar_ativo = false;
bool em_standby = true;

static void radar_task(void *arg) {
    uint8_t data[BUF_SIZE];
    uint8_t header[] = {0xF4, 0xF3, 0xF2, 0xF1};
    int dist_cm = 9999;
    
    while (1) {
        // Tenta ler os dados que chegaram no buffer da UART
        int len = uart_read_bytes(UART_RADAR, data, BUF_SIZE - 1, 50 / portTICK_PERIOD_MS);
        if (len > 0) {
            radar_ativo = true;
            
            // Busca pelo cabeçalho padrão do LD2410C no meio dos bytes lidos
            for (int i = 0; i < len - 10; i++) {
                if (data[i] == header[0] && data[i+1] == header[1] && 
                    data[i+2] == header[2] && data[i+3] == header[3]) {
                    
                    // O protocolo Básico do LD2410 diz:
                    // [i+0 a i+3]: F4 F3 F2 F1
                    // [i+4 a i+5]: Length
                    // [i+6]: Data Type (0x02 para Basic, 0x01 para Engineering)
                    // [i+7]: Head (0xAA)
                    // [i+8]: Estado do alvo (0=Ninguém, 1=Movendo, 2=Estático, 3=Ambos)
                    
                    if (data[i+6] == 0x02 || data[i+6] == 0x01) { // Verifica se é um frame válido
                        uint8_t target_state = data[i+8];
                        estado_alvo = target_state;
                        
                        if (target_state == 0) {
                            dist_cm = 9999; // Ninguém
                        } else {
                            // Distância movendo: bytes 9 (Low) e 10 (High)
                            int dist_mov = data[i+9] | (data[i+10] << 8);
                            
                            // Distância estático: bytes 12 (Low) e 13 (High)
                            int dist_stat = data[i+12] | (data[i+13] << 8);
                            
                            dist_cm = 9999;
                            if ((target_state == 1 || target_state == 3) && dist_mov > 0) {
                                dist_cm = dist_mov;
                            }
                            if ((target_state == 2 || target_state == 3) && dist_stat > 0) {
                                if (dist_stat < dist_cm) {
                                    dist_cm = dist_stat;
                                }
                            }
                        }
                    }
                    
                    // --- LÓGICA DE ZONAS ---
                    int zona_anterior = zona_atual;
                    
                    if (dist_cm == 9999) {
                        zona_atual = ZONA_NENHUMA;
                    } else if (dist_cm <= 100) {
                        zona_atual = ZONA_PORTA; // <= 1m
                    } else if (dist_cm <= 200) {
                        zona_atual = ZONA_APROXIMACAO; // 1m a 2m
                    } else {
                        zona_atual = ZONA_LONGE; // > 2m
                    }
                    
                    distancia_atual = dist_cm;

                    // --- LÓGICA DE STANDBY INTELIGENTE ---
                    static TickType_t tempo_ultimo_movimento = 0;
                    
                    // Se estiver se movendo, atualiza o relógio
                    if (estado_alvo == 1 || estado_alvo == 3) {
                        tempo_ultimo_movimento = xTaskGetTickCount();
                    }
                    
                    if (zona_atual < ZONA_APROXIMACAO) {
                        // Ninguém por perto, vai dormir
                        em_standby = true;
                    } else {
                        // Tem alguém perto! Mas está se mexendo?
                        // pdTICKS_TO_MS converte ticks para milissegundos
                        if (estado_alvo == 2 && (xTaskGetTickCount() - tempo_ultimo_movimento) * portTICK_PERIOD_MS > 10000) { // 10 segundos = 10000 ms
                            em_standby = true; // Timeout! Planta balançando ou pessoa parada há 10s
                        } else {
                            em_standby = false; // Acorda a câmera!
                        }
                    }

                    
                    if (zona_atual != zona_anterior) {
                        ESP_LOGI(TAG, "Zona alterada: %d (Distância alvo: %d cm)", zona_atual, (dist_cm == 9999 ? 0 : dist_cm));
                    }
                    
                    // Achou um frame válido, podemos parar de buscar neste buffer
                    break;
                }
            }
        }
        
        // Dá um pequeno respiro para o FreeRTOS não travar a CPU
        vTaskDelay(20 / portTICK_PERIOD_MS);
    }
}

void iniciar_radar(void) {
    // Configura a velocidade da porta (Baud Rate padrão do LD2410C é 256000)
    uart_config_t uart_config = {
        .baud_rate = 256000,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    
    ESP_LOGI(TAG, "Inicializando Radar HLK-LD2410C (Pinos: TX ESP=%d, RX ESP=%d)", PIN_TX, PIN_RX);
    
    // Instala e configura a UART
    ESP_ERROR_CHECK(uart_driver_install(UART_RADAR, BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_RADAR, &uart_config));
    
    // Como os pinos 43 e 44 são padrão do UART0, forçamos o UART1 a assumir o controle deles
    ESP_ERROR_CHECK(uart_set_pin(UART_RADAR, PIN_TX, PIN_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    // Cria a Task de leitura infinita
    xTaskCreate(radar_task, "radar_task", 4096, NULL, 10, NULL);
}
