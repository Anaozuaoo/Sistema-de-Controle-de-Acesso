#ifndef SD_MODULE_H
#define SD_MODULE_H

#include <stdbool.h>
#include "esp_err.h"

// Inicializa o cartão SD (não trava se não encontrar o cartão)
esp_err_t iniciar_sd(void);

// Escreve uma linha no historico.csv se o cartão estiver inserido
void gravar_no_sd(const char* data, const char* nome, const char* status);

// Variável global para sabermos se o cartão está pronto para uso
extern bool cartao_pronto;

#endif // SD_MODULE_H
