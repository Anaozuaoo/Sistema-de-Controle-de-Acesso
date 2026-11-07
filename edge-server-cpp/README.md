# Edge Server C++ (Pipeline Acelerado de Inferência)

Servidor de borda de altíssimo desempenho desenvolvido em C++17 com OpenCV. Responsável pelo consumo do fluxo de vídeo MJPEG do ESP32-S3, detecção e reconhecimento facial local acelerado por pirâmide multi-escala e despacho assíncrono de comandos de controle de acesso via cliente HTTP nativo.

---

## 🚀 Principais Características

- **Otimização Multi-Escala:** O fluxo de vídeo em alta resolução é reduzido em 4x para o detector Haar Cascade localizar rostos com máxima taxa de quadros (FPS alto, mínimo uso de CPU). Ao identificar um retângulo de face, o recorte correspondente é extraído da imagem em resolução original para a predição biométrica no classificador LBPH.
- **Comunicação HTTP Nativa Limpa:** Todas as chamadas de shell legadas (`system("curl ...")`) foram completamente substituídas por uma classe nativa `HttpClient` baseada em sockets BSD/Winsock com tratamento determinístico de timeout, leitura de código de status HTTP e suporte a cabeçalhos (`X-Auth-Token`).
- **Despacho Assíncrono Desacoplado:** As requisições de rede para abertura de porta ou sinalização de alarme são disparadas em *threads* separadas com *cooldown*, garantindo que a reprodução do vídeo e a interface de monitoramento não engasguem.
- **Configuração Desacoplada de Credenciais:** Suporta parametrização por variáveis de ambiente (`ESP32_HOST`, `AUTH_TOKEN`) ou argumentos de linha de comando, sem dados sensíveis embutidos no código-fonte.

---

## 🛠️ Compilação

### Pré-requisitos
- Compilador C++17 (GCC, Clang ou MSVC)
- CMake 3.10 ou superior
- OpenCV 4.x compilado com módulo `opencv_contrib` (especificamente `face`)

### Instruções de Build

```bash
# Criar diretório de build
mkdir build
cd build

# Gerar arquivos de compilação
cmake ..

# Compilar
cmake --build . --config Release
```

---

## 🎯 Execução

### 1. Treinamento da Face Autorizada
Antes de iniciar o servidor, treine o classificador LBPH com fotos do usuário:
```bash
# Crie a pasta e coloque fotos da face (ex: fotos_treinamento/)
python treinar_ia.py fotos_treinamento
```
Isso gerará o arquivo `cerebro_treinado.yml`.

### 2. Iniciar o Servidor

Definindo variáveis de ambiente:
```bash
# No Linux / macOS
export ESP32_HOST="192.168.1.100"
export AUTH_TOKEN="SEU_TOKEN_SECRETO"
./Servidor_Seguranca

# No Windows (PowerShell)
$env:ESP32_HOST="192.168.1.100"
$env:AUTH_TOKEN="SEU_TOKEN_SECRETO"
.\Servidor_Seguranca.exe
```

Ou passando parâmetros via linha de comando:
```bash
./Servidor_Seguranca 192.168.1.100 SEU_TOKEN_SECRETO
```
