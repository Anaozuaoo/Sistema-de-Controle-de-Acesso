# AI Python Server & Web Dashboard

Servidor de Inteligência Artificial multimodal com painel Web integrado (Flask), combinando **Reconhecimento Facial 128D** (1º Fator) e **Biometria Comportamental Dinâmica por DTW e Isolation Forest** (2º Fator via tablet/smartphone touch).

---

## 🧠 Recursos e Algoritmos

1. **Reconhecimento Facial de Alta Fidelidade (1º Fator):**
   - Utiliza rede neural dlib (`face_recognition`) para extração de embeddings faciais de 128 dimensões.
   - Treinamento on-the-fly carregando imagens contidas no diretório `rostos_permitidos/`.
2. **Autenticação Biométrica Multimodal 2FA (DTW + Dinâmica Neuromotora):**
   - Coleta pontos táteis na tela touch (coordenadas $(x, y)$, tempo em ms, pressão e identificação de traço).
   - Extrai 12 atributos biomecânicos e cinéticos: tempo de traço, tempo de pausa no ar (*flight time*), velocidade média/máxima/desvio, aceleração e *jerk* (derivada da aceleração).
   - Realiza alinhamento elástico espaço-temporal via **Dynamic Time Warping (DTW)**.
   - Aplica modelo **Isolation Forest** treinado com dados cinéticos para detectar anomalias neuromotoras e tentativas de fraude ou coerção.
3. **Painel Web & Interface Touch Tablet:**
   - Exibição de stream de vídeo MJPEG em tempo real com overlay de caixas delimitadoras e telemetria do radar mmWave.
   - Interface web touch interativa para assinatura na rota `/tablet`.
   - Botão de destravamento manual com auditoria.
4. **Notificações Push e Auditoria em Tempo Real:**
   - Alertas automáticos via Telegram Bot com envio da foto do intruso em caso de acesso negado.
   - Registro duplicado de auditoria: log local em `historico_acessos.csv` e persistência remota no cartão MicroSD do ESP32 via rota `/salvar_sd`.

---

## 🛠️ Configuração e Execução

### 1. Criar e Ativar Ambiente Virtual

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar no Windows
.\venv\Scripts\activate

# Ativar no Linux / macOS
source venv/bin/activate
```

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

*(Nota para Windows: a biblioteca `dlib` pode requerer `cmake` ou compilação C++. Caso prefira, utilize o wheel pré-compilado compatível com sua versão de Python).*

### 3. Configurar Variáveis de Ambiente

Copie o arquivo de exemplo:
```bash
cp .env.example .env
```
Edite `.env` preenchendo o IP do ESP32, o token secreto e as credenciais do Telegram (se desejar).

### 4. Executar o Servidor

```bash
python reconhecimento_porta.py
```
Acesse o painel em seu navegador:
- Painel Geral: [http://localhost:5000](http://localhost:5000)
- Interface de Assinatura DTW (Tablet): [http://localhost:5000/tablet](http://localhost:5000/tablet)
