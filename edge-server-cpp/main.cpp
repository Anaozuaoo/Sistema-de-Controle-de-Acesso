#include <opencv2/opencv.hpp>
#include <opencv2/face.hpp>  
#include <iostream>
#include <thread>
#include <chrono>
#include <cstdlib>
#include <string>
#include "http_client.hpp"

using namespace std;
using namespace cv;
using namespace cv::face;

// =========================================================
// CONFIGURAÇÕES DO SERVIDOR EDGE
// =========================================================
struct EdgeConfig {
    string esp_host = "192.168.1.100";  // IP ou hostname mDNS do ESP32 (ex: "camera.local")
    int esp_http_port = 80;             // Porta do servidor REST de controle
    int esp_stream_port = 81;           // Porta do stream de vídeo MJPEG
    string auth_token = "SEU_TOKEN_SECRETO"; // Token configurado em config.h do ESP32
    string cascade_path = "haarcascade_frontalface_default.xml";
    string model_path = "cerebro_treinado.yml";
    double escala_reducao = 4.0;        // Fator de escala para otimização turbo da detecção
    double limiar_confianca = 85.0;     // Distância máxima LBPH para considerar match
    double tempo_cooldown_s = 5.0;      // Intervalo mínimo entre acionamentos sucessivos
};

auto ultimo_tempo_acao = chrono::system_clock::now();
bool primeira_execucao = true;

// Lê variável de ambiente ou retorna valor padrão
string ler_env(const string& chave, const string& padrao) {
    const char* val = getenv(chave.c_str());
    return (val != nullptr && string(val).length() > 0) ? string(val) : padrao;
}

// Disparo HTTP síncrono limpo para destrancar a porta
void acionar_abertura_esp32(const EdgeConfig& cfg) {
    cout << "\n[ACESSO PERMITIDO] Rosto autorizado detectado! Destrancando porta..." << endl;
    
    HttpResponse res = HttpClient::get(
        cfg.esp_host,
        cfg.esp_http_port,
        "/abrir",
        {{"X-Auth-Token", cfg.auth_token}},
        3000
    );

    if (res.success && res.status_code == 200) {
        cout << "[HTTP 200 OK] Porta destrancada com sucesso pelo ESP32. Resposta: " << res.body << endl;
    } else {
        cerr << "[HTTP ERRO] Falha ao destrancar: status " << res.status_code 
             << " - " << res.error_message << endl;
    }
}

// Disparo HTTP síncrono limpo para sinalizar bloqueio
void acionar_bloqueio_esp32(const EdgeConfig& cfg) {
    cout << "\n[ALERTA] Rosto desconhecido! Acionando bloqueio..." << endl;
    
    HttpResponse res = HttpClient::get(
        cfg.esp_host,
        cfg.esp_http_port,
        "/negado",
        {{"X-Auth-Token", cfg.auth_token}},
        3000
    );

    if (res.success) {
        cout << "[HTTP " << res.status_code << "] Alerta de bloqueio registrado pelo ESP32." << endl;
    } else {
        cerr << "[HTTP ERRO] Falha ao enviar alerta de bloqueio: " << res.error_message << endl;
    }
}

int main(int argc, char** argv) {
    EdgeConfig cfg;

    // Carrega configurações a partir de variáveis de ambiente se disponíveis
    cfg.esp_host = ler_env("ESP32_HOST", "192.168.1.100");
    cfg.auth_token = ler_env("AUTH_TOKEN", "SEU_TOKEN_SECRETO");
    
    // Suporte a argumentos de linha de comando: ./Servidor_Seguranca [IP_OU_HOST] [TOKEN]
    if (argc >= 2) cfg.esp_host = argv[1];
    if (argc >= 3) cfg.auth_token = argv[2];

    cout << "==========================================================" << endl;
    cout << " SISTEMA DE SEGURANCA EDGE C++ (PIPELINE ACELERADO)        " << endl;
    cout << "==========================================================" << endl;
    cout << " Alvo ESP32:     http://" << cfg.esp_host << ":" << cfg.esp_http_port << endl;
    cout << " Stream Video:   http://" << cfg.esp_host << ":" << cfg.esp_stream_port << "/" << endl;
    cout << " Token Auth:     " << (cfg.auth_token == "SEU_TOKEN_SECRETO" ? "[PADRAO / EXEMPLO]" : "[CONFIGURADO]") << endl;
    cout << "==========================================================" << endl;

    CascadeClassifier face_cascade;
    if (!face_cascade.load(cfg.cascade_path)) {
        cerr << "ERRO: Arquivo classificador Haar Cascade '" << cfg.cascade_path << "' nao encontrado!" << endl;
        return -1;
    }

    Ptr<LBPHFaceRecognizer> recognizer = LBPHFaceRecognizer::create();
    try {
        recognizer->read(cfg.model_path);
        cout << "[OK] Modelo biometrico '" << cfg.model_path << "' carregado com sucesso." << endl;
    } catch (...) {
        cerr << "AVISO: Modelo '" << cfg.model_path << "' nao encontrado." << endl;
        cerr << "Execute 'python treinar_ia.py' para gerar o modelo biometrico local antes do uso." << endl;
        return -1;
    }

    string stream_url = "http://" + cfg.esp_host + ":" + to_string(cfg.esp_stream_port) + "/";
    cout << "[STREAM] Conectando ao fluxo de video: " << stream_url << endl;
    VideoCapture cap(stream_url);
    if (!cap.isOpened()) {
        cerr << "ERRO: Nao foi possivel conectar na camera do ESP32 em: " << stream_url << endl;
        cerr << "Dica: Verifique se o ESP32 esta na mesma rede e se o IP informado esta correto." << endl;
        return -1;
    }

    Mat frame, gray, gray_reduzido;
    const double ESCALA = cfg.escala_reducao;

    while (true) {
        cap >> frame;
        if (frame.empty()) {
            this_thread::sleep_for(chrono::milliseconds(10));
            continue;
        }

        // Converte para escala de cinza e equaliza histograma na resolução total
        cvtColor(frame, gray, COLOR_BGR2GRAY);
        equalizeHist(gray, gray);

        // Otimização de Performance: Reduz 4x a imagem para o Haar Cascade detectar com alta taxa de FPS
        resize(gray, gray_reduzido, Size(gray.cols / ESCALA, gray.rows / ESCALA));

        vector<Rect> faces_reduzidas;
        face_cascade.detectMultiScale(
            gray_reduzido,
            faces_reduzidas,
            1.2,
            8,
            0 | CASCADE_SCALE_IMAGE,
            Size(25, 25)
        );

        for (size_t i = 0; i < faces_reduzidas.size(); i++) {
            // Escala as coordenadas de volta para a resolução original do frame
            Rect rosto_real(
                cvRound(faces_reduzidas[i].x * ESCALA),
                cvRound(faces_reduzidas[i].y * ESCALA),
                cvRound(faces_reduzidas[i].width * ESCALA),
                cvRound(faces_reduzidas[i].height * ESCALA)
            );

            // Garante que o retângulo está dentro dos limites da imagem
            rosto_real &= Rect(0, 0, gray.cols, gray.rows);
            if (rosto_real.width <= 0 || rosto_real.height <= 0) continue;

            int id_recebido = -1;
            double confianca = 0.0;

            // O reconhecedor LBPH avalia o recorte na imagem em resolução total
            Mat rosto_recortado = gray(rosto_real);
            recognizer->predict(rosto_recortado, id_recebido, confianca);

            auto tempo_agora = chrono::system_clock::now();
            chrono::duration<double> tempo_passado = tempo_agora - ultimo_tempo_acao;
            bool pode_disparar = (tempo_passado.count() > cfg.tempo_cooldown_s || primeira_execucao);

            // Se confiança for menor que o limiar e id corresponder a usuário autorizado (ID 1)
            if (confianca < cfg.limiar_confianca && id_recebido == 1) {
                rectangle(frame, rosto_real, Scalar(0, 255, 0), 2);
                string texto = "Autorizado (" + to_string((int)confianca) + ")";
                putText(frame, texto, Point(rosto_real.x, rosto_real.y - 10),
                        FONT_HERSHEY_SIMPLEX, 0.7, Scalar(0, 255, 0), 2);

                if (pode_disparar) {
                    ultimo_tempo_acao = tempo_agora;
                    primeira_execucao = false;
                    // Dispara a requisição HTTP nativa em thread desacoplada para não travar a UI
                    thread t(acionar_abertura_esp32, cfg);
                    t.detach();
                }
            } else {
                rectangle(frame, rosto_real, Scalar(0, 0, 255), 2);
                putText(frame, "Desconhecido", Point(rosto_real.x, rosto_real.y - 10),
                        FONT_HERSHEY_SIMPLEX, 0.7, Scalar(0, 0, 255), 2);

                if (pode_disparar) {
                    ultimo_tempo_acao = tempo_agora;
                    primeira_execucao = false;
                    thread t(acionar_bloqueio_esp32, cfg);
                    t.detach();
                }
            }
        }

        imshow("Monitoramento de Seguranca Edge C++", frame);
        if (waitKey(1) == 27) break; // Tecla ESC para encerrar
    }

    cap.release();
    destroyAllWindows();
    return 0;
}
