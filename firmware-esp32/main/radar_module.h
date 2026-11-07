#ifndef RADAR_MODULE_H
#define RADAR_MODULE_H

#include <stdbool.h>

// Definições de Zona para o Radar
#define ZONA_NENHUMA     0  // Sem detecção
#define ZONA_LONGE       1  // > 2 metros (Ignorar)
#define ZONA_APROXIMACAO 2  // 1m a 2m (Standby -> Acordar Câmera)
#define ZONA_PORTA       3  // <= 1m (Muito perto, acionar IA)

// Variáveis globais para o servidor acessar
extern int zona_atual;
extern int distancia_atual;
extern int estado_alvo; // 0=Ninguem, 1=Movendo, 2=Estatico, 3=Ambos
extern bool radar_ativo; 
extern bool em_standby; // Timeout de alvo estatico

// Inicializa a UART e a Task do Radar HLK-LD2410C
void iniciar_radar(void);

#endif // RADAR_MODULE_H
