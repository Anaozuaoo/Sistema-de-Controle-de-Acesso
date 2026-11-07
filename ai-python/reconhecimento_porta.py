import os
import cv2
import face_recognition
import requests
import time
import numpy as np
import threading
from flask import Flask, render_template_string, Response, request, jsonify
from datetime import datetime
import csv
from biometria_dtw import GerenciadorBiometriaComportamental

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- CONFIGURAÇÕES DE REDE E DISPOSITIVO ---
IP_ESP = os.getenv("ESP32_IP", "192.168.1.100")
PORTA_HTTP = os.getenv("ESP32_HTTP_PORT", "80")
PORTA_STREAM = os.getenv("ESP32_STREAM_PORT", "81")

URL_BASE = f"http://{IP_ESP}:{PORTA_HTTP}" if PORTA_HTTP != "80" else f"http://{IP_ESP}"
URL_CAPTURE = f"{URL_BASE}/capture"
URL_STREAM = f"http://{IP_ESP}:{PORTA_STREAM}/"
URL_ABRIR = f"{URL_BASE}/abrir"
URL_ANALISANDO = f"{URL_BASE}/analisando"
URL_NEGADO = f"{URL_BASE}/negado"

# --- CONFIGURAÇÕES DE SEGURANÇA E TELEGRAM ---
TOKEN_DE_ACESSO = os.getenv("AUTH_TOKEN", "SEU_TOKEN_SECRETO")
HEADERS_AUTORIZACAO = {"X-Auth-Token": TOKEN_DE_ACESSO}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PASTA_ROSTOS = os.getenv("PASTA_ROSTOS", "rostos_permitidos")

# --- CONFIGURAÇÕES DE DESEMPENHO ---
INTERVALO_CAPTURA_CAMERA = 0.001    # Captura o mais rápido possível (reduz delay de rede)
INTERVALO_IA = 0.5                  # Segundos entre análises de IA (desafoga o processador)
FATOR_REDUCAO_IA = 0.25             # Reduz o frame antes de rodar a IA
COOLDOWN_SEGUNDOS = 5
TIMEOUT_REQUESTS = 5                # Aumentado para 5s (ESP32 demora 3s para abrir a porta)

# --- VARIÁVEIS GLOBAIS (protegidas por locks) ---
lock_frame_camera = threading.Lock()
lock_frame_web = threading.Lock()
lock_rostos_tela = threading.Lock()
lock_2fa = threading.Lock()

frame_mais_recente_da_camera = None
timestamp_ultimo_frame = 0          # Substitui o uso do id() para controle de frame novo
frame_jpeg_para_web = None
rostos_detectados_na_tela = []      # Guarda as coordenadas dos rostos para o vídeo fluir
em_cooldown = threading.Event()
SALVAR_SD = False                   # Controle de backup no SD
EXIGIR_2FA_DTW = True               # Quando True, exige Face (1º Fator) + Assinatura DTW no Tablet (2º Fator)

dados_radar = {"distancia": 9999, "zona": 0, "ativo": False, "estado": 0, "standby": True}
lock_radar = threading.Lock()

# Estado da autenticação de 2 fatores (Face -> Tablet DTW)
estado_2fa = {
    "aguardando_assinatura": False,
    "usuario_facial": None,
    "expira_em": 0.0,
    "ultimo_resultado_dtw": None,
}

gerenciador_dtw = GerenciadorBiometriaComportamental()


# --- PAINEL WEB ---
app = Flask(__name__)

HTML_PAINEL = """
<!DOCTYPE html>
<html lang="pt-PT">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel de Segurança AI - 2 Fatores</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e2f; color: white; text-align: center; margin: 0; padding: 20px; }
        .container { background-color: #2a2a40; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); max-width: 850px; margin: 0 auto; }
        h1 { color: #4CAF50; margin-bottom: 5px; }
        .status { margin-bottom: 15px; font-size: 16px; color: #aaa; }
        .video-feed { width: 100%; max-width: 640px; border-radius: 10px; border: 3px solid #4CAF50; margin-bottom: 15px; }
        .btn { padding: 13px 28px; font-size: 16px; font-weight: bold; color: white; background-color: #007BFF; border: none; border-radius: 8px; cursor: pointer; transition: 0.3s; margin: 6px; text-decoration: none; display: inline-block; }
        .btn:hover { background-color: #0056b3; transform: scale(1.03); }
        .btn-tablet { background-color: #9C27B0; }
        .btn-tablet:hover { background-color: #7B1FA2; }
        .toggles { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; margin-top: 15px; background: #1f1f30; padding: 14px; border-radius: 10px; }
        .badge-2fa { margin: 10px auto; padding: 10px 18px; border-radius: 8px; max-width: 620px; font-weight: bold; background: #33334d; color: #ffd54f; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ Central de Segurança AI (ESP32-S3 + DTW)</h1>
        <p class="status">Monitoramento Biométrico Multimodal: Reconhecimento Facial + Dinâmica Comportamental (DTW)</p>
        <div id="banner_2fa" class="badge-2fa">Carregando status do 2º Fator (DTW)...</div>
        <img id="foto_feed" src="/video_feed" class="video-feed" alt="A aguardar ligação à câmara...">
        <br>
        <button class="btn" onclick="abrirPortaManual()">🔓 Desbloquear Porta Manualmente</button>
        <a href="/tablet" target="_blank" class="btn btn-tablet">✍️ Abrir Interface Touch / Tablet (DTW)</a>
        <div class="toggles">
            <label style="font-size: 16px; cursor: pointer;">
                <input type="checkbox" id="dtw_toggle" onchange="toggle2FA()" checked style="width: 18px; height: 18px; vertical-align: middle;">
                Exigir 2º Fator Comportamental (Assinatura DTW no Tablet)
            </label>
            <label style="font-size: 16px; cursor: pointer;">
                <input type="checkbox" id="sd_toggle" onchange="toggleSD()" style="width: 18px; height: 18px; vertical-align: middle;">
                Salvar Backup no Cartão SD (ESP32)
            </label>
        </div>
    </div>
    <script>
        function abrirPortaManual() {
            fetch('/comando_abrir').then(response => {
                if (response.ok) alert('Sucesso! Comando de abertura enviado.');
            });
        }
        function toggleSD() {
            fetch('/toggle_sd').then(response => response.text()).then(state => {
                console.log("SD Backup state: " + state);
            });
        }
        function toggle2FA() {
            fetch('/toggle_2fa').then(response => response.json()).then(data => {
                document.getElementById('dtw_toggle').checked = data.exigir_2fa;
                atualizarStatus2FA();
            });
        }
        function atualizarStatus2FA() {
            fetch('/api/status_2fa').then(r => r.json()).then(data => {
                document.getElementById('dtw_toggle').checked = data.exigir_2fa;
                const b = document.getElementById('banner_2fa');
                if (!data.exigir_2fa) {
                    b.style.background = '#2e4a32';
                    b.style.color = '#a5d6a7';
                    b.innerText = 'Modo 1 Fator Ativo: Reconhecimento Facial abre a porta diretamente.';
                } else if (data.aguardando_assinatura) {
                    b.style.background = '#5c4300';
                    b.style.color = '#ffe082';
                    b.innerText = '⏳ 1º Fator OK (' + data.usuario_facial + ')! Aguardando assinatura DTW em /tablet (' + data.segundos_restantes + 's)...';
                } else {
                    b.style.background = '#33334d';
                    b.style.color = '#b39ddb';
                    b.innerText = '🔒 Modo 2 Fatores Ativo: Rosto na Câmera + Assinatura Dinâmica DTW no Tablet (/tablet)';
                }
            }).catch(() => {});
        }
        setInterval(atualizarStatus2FA, 1500);
        atualizarStatus2FA();
    </script>
</body>
</html>
"""

HTML_TABLET = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Biometria Comportamental DTW - Tablet</title>
    <style>
        * { box-sizing: border-box; user-select: none; -webkit-user-select: none; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: #12121e; color: #f0f0f5; margin: 0; padding: 12px; text-align: center; }
        .card { max-width: 720px; margin: 0 auto; background: #1e1e30; border-radius: 16px; padding: 16px; box-shadow: 0 8px 25px rgba(0,0,0,0.6); }
        h2 { margin: 4px 0 8px; color: #bb86fc; font-size: 22px; }
        .tabs { display: flex; gap: 8px; justify-content: center; margin-bottom: 12px; }
        .tab-btn { flex: 1; max-width: 240px; padding: 10px; border: 1px solid #3f3f60; background: #26263d; color: #ccc; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .tab-btn.active { background: #7c4dff; color: white; border-color: #b388ff; }
        .status-banner { padding: 10px 14px; border-radius: 10px; margin-bottom: 12px; font-weight: 600; font-size: 15px; background: #292942; color: #ffd54f; }
        .canvas-wrap { position: relative; width: 100%; max-width: 660px; margin: 0 auto; border: 2px dashed #5e5ce6; border-radius: 12px; background: #0d0d17; overflow: hidden; touch-action: none; }
        canvas { display: block; width: 100%; height: 280px; touch-action: none; cursor: crosshair; }
        .metrics-live { display: flex; justify-content: space-around; font-size: 13px; color: #9fa8da; margin: 8px 0; background: #161625; padding: 8px; border-radius: 8px; }
        .controls { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 10px; }
        .btn { padding: 12px 22px; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; color: white; }
        .btn-clear { background: #546e7a; }
        .btn-validate { background: #00c853; flex: 1; max-width: 280px; }
        .btn-train { background: #ff9100; flex: 1; max-width: 280px; }
        .input-user { padding: 10px 14px; border-radius: 8px; border: 1px solid #4a4a6a; background: #141422; color: white; font-size: 15px; width: 220px; }
        .result-box { margin-top: 14px; padding: 14px; border-radius: 10px; text-align: left; font-size: 14px; display: none; }
        .result-ok { background: rgba(0, 200, 83, 0.15); border: 1px solid #00c853; color: #b9f6ca; }
        .result-fail { background: rgba(255, 82, 82, 0.15); border: 1px solid #ff5252; color: #ff8a80; }
    </style>
</head>
<body>
    <div class="card">
        <h2>✍️ Interface Touch Comportamental (DTW)</h2>
        <div class="tabs">
            <button class="tab-btn active" id="tab_auth" onclick="mudarModo('auth')">🔐 Autenticar (2º Fator)</button>
            <button class="tab-btn" id="tab_train" onclick="mudarModo('train')">➕ Cadastrar Gabarito</button>
        </div>

        <div id="status_banner" class="status-banner">
            Aguardando identificação ou assinatura na superfície de toque...
        </div>

        <div id="painel_usuario" style="margin-bottom: 10px;">
            <label for="nome_usuario" style="font-size: 14px; color: #ccc;">Usuário: </label>
            <input type="text" id="nome_usuario" class="input-user" value="Roberto" oninput="sincronizarStatusCamera()" placeholder="Ex: Roberto ou Joao">
            <span id="badge_qtd_dataset" style="display:inline-block; margin-left:8px; padding:6px 10px; border-radius:6px; background:#2b2b45; color:#80d8ff; font-size:13px; font-weight:bold;">
                Dataset: 0 amostras
            </span>
        </div>

        <div class="canvas-wrap">
            <canvas id="touch_canvas" width="660" height="280"></canvas>
        </div>

        <div class="metrics-live">
            <span id="m_pts">Pontos (X,Y): 0</span>
            <span id="m_tempo">Tempo (Δt): 0 ms</span>
            <span id="m_tracos">Traços: 0</span>
        </div>

        <div class="controls">
            <button class="btn btn-clear" onclick="limparCanvas()">🧹 Limpar Quadro</button>
            <button class="btn btn-validate" id="btn_acao_auth" onclick="enviarAssinaturaAuth()">✅ Validar Assinatura (DTW)</button>
            <button class="btn btn-train" id="btn_acao_train" style="display:none;" onclick="enviarAmostraTreino()">💾 Salvar Amostra no Dataset</button>
        </div>

        <div class="controls" id="controles_delete_dataset" style="display:none; margin-top: 8px;">
            <button class="btn" style="background:#f57c00; font-size:14px; padding:9px 16px;" onclick="deletarUltimaAmostra()">↩️ Apagar Última Amostra</button>
            <button class="btn" style="background:#d32f2f; font-size:14px; padding:9px 16px;" onclick="deletarUsuarioInteiro()">🗑️ Deletar Todo Dataset do Usuário</button>
        </div>

        <div id="resultado_box" class="result-box"></div>
        <p style="font-size: 12px; color: #777; margin-top: 12px;">
            Captura vetorial em tempo real: coordenadas (X, Y), marcação temporal (t), velocidade cinética (v) e aceleração (a).
        </p>
    </div>

    <script>
        const canvas = document.getElementById('touch_canvas');
        const ctx = canvas.getContext('2d');
        let modoAtual = 'auth';
        let desenhando = false;
        let strokeAtual = 0;
        let pontos = [];
        let tInicio = null;
        let ultimoPonto = null;

        function ajustarCanvas() {
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
            desenharGrade();
        }

        function desenharGrade() {
            ctx.fillStyle = '#0d0d17';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#1f1f35';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(30, canvas.height * 0.72);
            ctx.lineTo(canvas.width - 30, canvas.height * 0.72);
            ctx.stroke();
        }

        window.addEventListener('resize', ajustarCanvas);
        setTimeout(ajustarCanvas, 50);

        function obterCoordenadas(e) {
            const rect = canvas.getBoundingClientRect();
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            let pressao = 0.5;
            if (typeof e.pressure === 'number' && e.pressure > 0) pressao = e.pressure;
            else if (e.touches && e.touches[0] && e.touches[0].force > 0) pressao = e.touches[0].force;
            return {
                x: clientX - rect.left,
                y: clientY - rect.top,
                t: performance.now(),
                p: pressao
            };
        }

        function iniciarTraco(e) {
            e.preventDefault();
            desenhando = true;
            const p = obterCoordenadas(e);
            if (tInicio === null) tInicio = p.t;
            strokeAtual += 1;
            const pontoReg = { x: p.x, y: p.y, t: p.t, stroke: strokeAtual, p: p.p };
            pontos.push(pontoReg);
            ultimoPonto = pontoReg;
            atualizarMetricasLive();
        }

        function moverTraco(e) {
            if (!desenhando) return;
            e.preventDefault();
            const p = obterCoordenadas(e);
            const pontoReg = { x: p.x, y: p.y, t: p.t, stroke: strokeAtual, p: p.p };
            pontos.push(pontoReg);

            if (ultimoPonto) {
                const dt = Math.max(1, p.t - ultimoPonto.t);
                const dist = Math.hypot(p.x - ultimoPonto.x, p.y - ultimoPonto.y);
                const vel = dist / dt; // px/ms
                // Cor dinâmica conforme a velocidade do traço (azul=lento, verde=médio, ciano/rosa=rápido)
                ctx.strokeStyle = vel > 0.8 ? '#00e5ff' : (vel > 0.3 ? '#00e676' : '#ffab00');
                ctx.lineWidth = 3.2;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.beginPath();
                ctx.moveTo(ultimoPonto.x, ultimoPonto.y);
                ctx.lineTo(p.x, p.y);
                ctx.stroke();
            }
            ultimoPonto = pontoReg;
            atualizarMetricasLive();
        }

        function finalizarTraco(e) {
            if (!desenhando) return;
            e.preventDefault();
            desenhando = false;
            ultimoPonto = null;
        }

        canvas.addEventListener('pointerdown', iniciarTraco);
        canvas.addEventListener('pointermove', moverTraco);
        canvas.addEventListener('pointerup', finalizarTraco);
        canvas.addEventListener('pointercancel', finalizarTraco);

        function atualizarMetricasLive() {
            document.getElementById('m_pts').innerText = 'Pontos (X,Y): ' + pontos.length;
            const dur = pontos.length > 1 ? Math.round(pontos[pontos.length - 1].t - pontos[0].t) : 0;
            document.getElementById('m_tempo').innerText = 'Tempo (Δt): ' + dur + ' ms';
            document.getElementById('m_tracos').innerText = 'Traços: ' + strokeAtual;
        }

        function limparCanvas() {
            pontos = [];
            strokeAtual = 0;
            tInicio = null;
            ultimoPonto = null;
            desenharGrade();
            atualizarMetricasLive();
        }

        function mudarModo(novoModo) {
            modoAtual = novoModo;
            document.getElementById('tab_auth').classList.toggle('active', novoModo === 'auth');
            document.getElementById('tab_train').classList.toggle('active', novoModo === 'train');
            document.getElementById('btn_acao_auth').style.display = novoModo === 'auth' ? 'inline-block' : 'none';
            document.getElementById('btn_acao_train').style.display = novoModo === 'train' ? 'inline-block' : 'none';
            document.getElementById('controles_delete_dataset').style.display = novoModo === 'train' ? 'flex' : 'none';
            document.getElementById('resultado_box').style.display = 'none';
            limparCanvas();
        }

        function deletarUltimaAmostra() {
            const usuario = document.getElementById('nome_usuario').value.trim();
            if (!usuario) return;
            fetch('/api/dtw/deletar_ultima', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ usuario: usuario })
            })
            .then(r => r.json())
            .then(res => {
                if (res.erro) {
                    mostrarResultado(false, '⚠️ ' + res.erro);
                } else {
                    mostrarResultado(true,
                        '↩️ <b>Última amostra de ' + res.usuario + ' apagada!</b><br>' +
                        '• Restam <b>' + res.total_amostras + ' amostras</b> no Dataset | Limiar DTW: <b>' + res.limiar_dtw + '</b>'
                    );
                    sincronizarStatusCamera();
                }
            });
        }

        function deletarUsuarioInteiro() {
            const usuario = document.getElementById('nome_usuario').value.trim();
            if (!usuario) return;
            if (!confirm('Tem certeza que deseja DELETAR TODAS as amostras de "' + usuario + '" do Dataset?')) return;
            fetch('/api/dtw/deletar_usuario', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ usuario: usuario })
            })
            .then(r => r.json())
            .then(res => {
                if (res.erro) {
                    mostrarResultado(false, '⚠️ ' + res.erro);
                } else {
                    mostrarResultado(true, '🗑️ <b>Todo o Dataset de "' + res.usuario + '" foi zerado com sucesso!</b> Você pode cadastrar novas amostras do zero.');
                    sincronizarStatusCamera();
                }
            });
        }

        function mostrarResultado(ok, htmlTexto) {
            const box = document.getElementById('resultado_box');
            box.className = 'result-box ' + (ok ? 'result-ok' : 'result-fail');
            box.innerHTML = htmlTexto;
            box.style.display = 'block';
        }

        function enviarAmostraTreino() {
            const usuario = document.getElementById('nome_usuario').value.trim();
            if (pontos.length < 8) {
                mostrarResultado(false, '⚠️ Desenhe sua assinatura na tela antes de salvar.');
                return;
            }
            fetch('/api/dtw/treinar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ usuario: usuario, pontos: pontos })
            })
            .then(r => r.json())
            .then(res => {
                if (res.erro) {
                    mostrarResultado(false, '❌ ' + res.erro);
                } else {
                    const m = res.metricas_amostra;
                    const statusIF = res.iforest_ativo
                        ? '🟢 <b>ATIVO (Treinado em 12 dimensões)</b>'
                        : '🟡 Coletando Dataset (faltam ' + Math.max(0, 5 - res.total_amostras) + ' amostras p/ ativar Isolation Forest)';
                    mostrarResultado(true,
                        '✅ <b>Amostra #' + res.total_amostras + ' salva no Dataset de ' + res.usuario + '!</b> (Arquivo: <code>' + res.arquivo_csv + '</code>)<br>' +
                        '• Isolation Forest (Anomalia): ' + statusIF + '<br>' +
                        '• Limiar DTW Calibrado: <b>' + res.limiar_dtw + '</b><br>' +
                        '• Features Neuromotoras: Tempo = <b>' + m.tempo_total_ms + ' ms</b> | Pausas = <b>' + m.tempo_pausa_ms + ' ms</b> | Vel. = <b>' + m.vel_media + '</b> | Arranco (Jerk) = <b>' + m.jerk_medio + '</b>'
                    );
                    limparCanvas();
                }
            });
        }

        function enviarAssinaturaAuth() {
            const usuario = document.getElementById('nome_usuario').value.trim();
            if (pontos.length < 8) {
                mostrarResultado(false, '⚠️ Assinatura muito curta! Assine no quadro acima.');
                return;
            }
            fetch('/api/dtw/validar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ usuario: usuario, pontos: pontos })
            })
            .then(r => r.json())
            .then(res => {
                if (res.erro) {
                    mostrarResultado(false, '❌ ' + res.erro);
                    return;
                }
                const m = res.metricas;
                const txtIF = res.iforest_ativo
                    ? ('Score Isolation Forest: <b>' + res.iforest_score + '</b> ' + (res.iforest_anomalia ? '(⚠️ Anomalia)' : '(Normal)'))
                    : 'Isolation Forest: aguardando >= 5 amostras no dataset';
                const motivos = (res.motivos_anomalia && res.motivos_anomalia.length > 0)
                    ? '<br>• Anomalias Detectadas: <b>' + res.motivos_anomalia.join(' | ') + '</b>'
                    : '';
                if (res.aprovado) {
                    mostrarResultado(true,
                        '🟢 <b>ACESSO BANCÁRIO AUTORIZADO (' + res.usuario + ') - Porta Destrancada!</b><br>' +
                        '• Similaridade Comportamental: <b>' + res.similaridade_pct + '%</b> (Dataset: ' + res.amostras_no_dataset + ' amostras)<br>' +
                        '• Custo DTW Final: <b>' + res.custo_final + '</b> (Limiar: ' + res.limiar_dtw + ') | ' + txtIF + '<br>' +
                        '• Telemetria: Tempo = <b>' + m.tempo_total_ms + ' ms</b> (Ref: ' + res.tempo_ref_ms + ' ms) | Vel. = <b>' + m.vel_media + '</b> | Arranco (Jerk) = <b>' + m.jerk_medio + '</b>'
                    );
                } else {
                    mostrarResultado(false,
                        '🔴 <b>ACESSO NEGADO - Fraude ou Anomalia Comportamental!</b><br>' +
                        '• Similaridade Comportamental: <b>' + res.similaridade_pct + '%</b> (Dataset: ' + res.amostras_no_dataset + ' amostras)<br>' +
                        '• Custo DTW Final: <b>' + res.custo_final + '</b> (Excedeu Limiar: ' + res.limiar_dtw + ') | ' + txtIF + '<br>' +
                        '• Telemetria: Tempo = <b>' + m.tempo_total_ms + ' ms</b> (Ref: ' + res.tempo_ref_ms + ' ms) | Arranco (Jerk) = <b>' + m.jerk_medio + '</b>' +
                        motivos
                    );
                }
                limparCanvas();
            });
        }

        function sincronizarStatusCamera() {
            fetch('/api/status_2fa').then(r => r.json()).then(data => {
                const banner = document.getElementById('status_banner');
                if (data.aguardando_assinatura && data.usuario_facial) {
                    banner.style.background = '#1b5e20';
                    banner.style.color = '#b9f6ca';
                    banner.innerText = '📸 1º Fator Confirmado: Rosto de ' + data.usuario_facial + ' reconhecido! Assine abaixo (' + data.segundos_restantes + 's)';
                    document.getElementById('nome_usuario').value = data.usuario_facial;
                } else {
                    banner.style.background = '#292942';
                    banner.style.color = '#ffd54f';
                    banner.innerText = '✍️ Superfície Pronta: Assine para validar o perfil comportamental (DTW) ou aguarde o 1º fator facial.';
                }
                const uAtual = document.getElementById('nome_usuario').value.trim();
                const badge = document.getElementById('badge_qtd_dataset');
                if (data.usuarios_cadastrados && data.usuarios_cadastrados[uAtual]) {
                    const info = data.usuarios_cadastrados[uAtual];
                    badge.innerText = 'Dataset: ' + info.amostras + ' amostras ' + (info.iforest_ativo ? '(IForest 🟢)' : '');
                } else {
                    badge.innerText = 'Dataset: 0 amostras';
                }
            }).catch(() => {});
        }
        setInterval(sincronizarStatusCamera, 1500);
        sincronizarStatusCamera();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAINEL)

@app.route('/tablet')
def pagina_tablet():
    return render_template_string(HTML_TABLET)

@app.route('/comando_abrir')
def comando_abrir():
    enviar_comando_esp(URL_ABRIR)
    return "OK", 200

@app.route('/toggle_sd')
def toggle_sd():
    global SALVAR_SD
    SALVAR_SD = not SALVAR_SD
    return str(SALVAR_SD), 200

@app.route('/toggle_2fa')
def toggle_2fa():
    global EXIGIR_2FA_DTW
    EXIGIR_2FA_DTW = not EXIGIR_2FA_DTW
    return jsonify({"exigir_2fa": EXIGIR_2FA_DTW})

@app.route('/api/status_2fa')
def api_status_2fa():
    agora = time.time()
    with lock_2fa:
        if estado_2fa["aguardando_assinatura"] and agora > estado_2fa["expira_em"]:
            estado_2fa["aguardando_assinatura"] = False
            estado_2fa["usuario_facial"] = None
        restante = max(0, int(estado_2fa["expira_em"] - agora)) if estado_2fa["aguardando_assinatura"] else 0
        return jsonify({
            "exigir_2fa": EXIGIR_2FA_DTW,
            "aguardando_assinatura": estado_2fa["aguardando_assinatura"],
            "usuario_facial": estado_2fa["usuario_facial"],
            "segundos_restantes": restante,
            "usuarios_cadastrados": gerenciador_dtw.listar_usuarios(),
        })

@app.route('/api/dtw/treinar', methods=['POST'])
def api_dtw_treinar():
    try:
        dados = request.get_json(force=True)
        usuario = dados.get("usuario", "Roberto")
        pontos = dados.get("pontos", [])
        res = gerenciador_dtw.cadastrar_amostra(usuario, pontos)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 400

@app.route('/api/dtw/deletar_ultima', methods=['POST'])
def api_dtw_deletar_ultima():
    try:
        dados = request.get_json(force=True)
        usuario = dados.get("usuario", "Roberto")
        res = gerenciador_dtw.remover_ultima_amostra(usuario)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 400

@app.route('/api/dtw/deletar_usuario', methods=['POST'])
def api_dtw_deletar_usuario():
    try:
        dados = request.get_json(force=True)
        usuario = dados.get("usuario", "Roberto")
        removido = gerenciador_dtw.limpar_usuario(usuario)
        if not removido:
            return jsonify({"erro": f"Usuário '{usuario}' não encontrado no Dataset."}), 404
        return jsonify({"usuario": usuario, "removido": True}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 400

@app.route('/api/dtw/validar', methods=['POST'])
def api_dtw_validar():
    try:
        dados = request.get_json(force=True)
        pontos = dados.get("pontos", [])
        usuario_req = dados.get("usuario", "").strip()

        with lock_2fa:
            usuario_alvo = estado_2fa["usuario_facial"] or (usuario_req if usuario_req else None)

        enviar_comando_esp(URL_ANALISANDO)
        resultado = gerenciador_dtw.validar_assinatura(pontos, usuario_esperado=usuario_alvo)

        with lock_2fa:
            estado_2fa["ultimo_resultado_dtw"] = resultado
            if resultado["aprovado"]:
                estado_2fa["aguardando_assinatura"] = False
                estado_2fa["usuario_facial"] = None

        if resultado["aprovado"]:
            print(f"\n🟢 [2º FATOR DTW APROVADO] Usuário: {resultado['usuario']} | Similaridade: {resultado['similaridade_pct']}% | DTW: {resultado['custo_final']}")
            threading.Thread(target=enviar_comando_esp, args=(URL_ABRIR,), daemon=True).start()
            registar_acesso(
                resultado["usuario"],
                f"🟢 Acesso 2FA Concedido (DTW {resultado['similaridade_pct']}%)"
            )
        else:
            print(f"\n🔴 [2º FATOR DTW NEGADO] Usuário tentado: {resultado['usuario']} | Custo DTW: {resultado['custo_final']} > Limiar {resultado['limiar_dtw']}")
            threading.Thread(target=enviar_comando_esp, args=(URL_NEGADO,), daemon=True).start()
            registar_acesso(
                resultado["usuario"],
                f"🔴 Fraude Comportamental Bloqueada (DTW {resultado['similaridade_pct']}%)"
            )
            with lock_frame_camera:
                frame_alerta = frame_mais_recente_da_camera.copy() if frame_mais_recente_da_camera is not None else None
            if frame_alerta is not None:
                threading.Thread(target=enviar_alerta_telegram, args=(frame_alerta,), daemon=True).start()

        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 400

def gerar_frames_web():
    while True:
        with lock_frame_web:
            frame_atual = frame_jpeg_para_web

        if frame_atual is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_atual + b'\r\n')
        else:
            # Só exibe isso se a câmara falhar ou estiver a ligar pela primeira vez
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "Sem sinal da camera...", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            _, jpeg = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        # Limita a taxa de envio da stream para ~30 FPS para não sobrecarregar
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(gerar_frames_web(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ==========================================================
# CÂMERA (Thread Rápida e Independente)
# ==========================================================
def ler_camera_sem_parar():
    global frame_mais_recente_da_camera, frame_jpeg_para_web, timestamp_ultimo_frame
    print(f"📸 A conectar ao stream de vídeo da câmera em: {URL_STREAM} ...")

    while True:
        # Abre o stream usando o OpenCV (que roda em C++ e é extremamente rápido)
        cap = cv2.VideoCapture(URL_STREAM)
        
        if not cap.isOpened():
            print("⚠️ Falha ao abrir stream da câmara. Tentando novamente em 2 segundos...")
            time.sleep(2)
            continue

        print("🟢 Conectado ao stream de vídeo com sucesso!")
        
        while True:
            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("⚠️ Perda de sinal do stream de vídeo. Tentando reconectar...")
                    break

                # 1. Guarda o frame limpo para a IA ler de forma atômica
                with lock_frame_camera:
                    frame_mais_recente_da_camera = frame.copy()
                    agora = time.time()
                    tempo_entre_frames = agora - timestamp_ultimo_frame
                    timestamp_ultimo_frame = agora

                # 2. Faz uma cópia para desenhar e enviar para a web sem bloquear a IA
                frame_desenho = frame.copy()

                # Pega dados atuais do radar
                with lock_radar:
                    dist = dados_radar["distancia"]
                    zona = dados_radar["zona"]
                    ativo = dados_radar["ativo"]
                    estado = dados_radar["estado"]
                    standby = dados_radar["standby"]

                # Lógica de Standby e Radar Visual
                if ativo:
                    if standby:
                        cv2.putText(frame_desenho, "STANDBY: Esperando presenca...", (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 255), 2)
                    
                    # Desenhar Minimapa de Radar (HUD)
                    h, w, _ = frame_desenho.shape
                    centro_radar = (w - 100, h - 20)
                    raio_max = 80
                    
                    # Fundo do Radar (Arco 180 graus)
                    cv2.ellipse(frame_desenho, centro_radar, (raio_max, raio_max), 180, 0, 180, (0, 50, 0), -1)
                    cv2.ellipse(frame_desenho, centro_radar, (raio_max, raio_max), 180, 0, 180, (0, 255, 0), 2)
                    cv2.ellipse(frame_desenho, centro_radar, (int(raio_max*0.5), int(raio_max*0.5)), 180, 0, 180, (0, 255, 0), 1)
                    
                    # Pontinho do alvo e Cores (Movendo vs Estático)
                    if dist != 9999 and dist <= 300:
                        cor_alvo = (0, 255, 255) if estado == 2 else (0, 0, 255) # Amarelo se respirando, Vermelho se movendo
                        dist_mapeada = int((dist / 300.0) * raio_max)
                        cv2.circle(frame_desenho, (centro_radar[0], centro_radar[1] - dist_mapeada), 5, cor_alvo, -1)
                        
                        # Texto indicativo do estado
                        texto_estado = "Parado (Respira)" if estado == 2 else "Em Movimento"
                        cv2.putText(frame_desenho, texto_estado, (w - 180, h - 135), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor_alvo, 1)
                    
                    # Texto Distância
                    txt_dist = f"Dist: {dist}cm" if dist != 9999 else "Ninguem"
                    cv2.putText(frame_desenho, txt_dist, (w - 160, h - 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                with lock_rostos_tela:
                    rostos_atuais = list(rostos_detectados_na_tela)

                # Desenha os retângulos baseados no último processamento da IA
                for (top, right, bottom, left, nome) in rostos_atuais:
                    cor = (0, 255, 0) if nome != "Desconhecido" else (0, 0, 255)
                    cv2.rectangle(frame_desenho, (left, top), (right, bottom), cor, 2)
                    cv2.rectangle(frame_desenho, (left, bottom - 35), (right, bottom), cor, cv2.FILLED)
                    cv2.putText(frame_desenho, nome, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

                # 3. Atualiza a web SEMPRE (com ou sem rosto) para o vídeo nunca travar
                ret_jpg, jpeg = cv2.imencode('.jpg', frame_desenho, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ret_jpg:
                    with lock_frame_web:
                        frame_jpeg_para_web = jpeg.tobytes()

            except Exception as e:
                print(f"⚠️ Erro no loop do stream: {e}")
                break
            
            # Pequeno respiro para a thread não consumir 100% da CPU à toa
            time.sleep(0.001)

        cap.release()
        time.sleep(1)


# ==========================================================
# CÉREBRO DA IA (Thread de Segundo Plano Controlada)
# ==========================================================
def processar_ia_continuamente():
    global rostos_detectados_na_tela
    ultimo_timestamp_analisado = 0

    while True:
        try:
            with lock_frame_camera:
                frame_atual = frame_mais_recente_da_camera
                timestamp_atual = timestamp_ultimo_frame

            # O uso do timestamp evita bugs de reciclagem de id() na memória
            if frame_atual is not None and timestamp_atual != ultimo_timestamp_analisado:
                frame_ia = frame_atual.copy()
                ultimo_timestamp_analisado = timestamp_atual

                frame_pequeno = cv2.resize(frame_ia, (0, 0), fx=FATOR_REDUCAO_IA, fy=FATOR_REDUCAO_IA)
                rgb_frame_pequeno = np.ascontiguousarray(frame_pequeno[:, :, ::-1])
                
                # Passo 1: Localiza apenas. Muito mais rápido e não bloqueia tanto o GIL.
                localizacao_rostos = face_recognition.face_locations(rgb_frame_pequeno, model="hog")

                if len(localizacao_rostos) > 0:
                    nomes_na_tela = []
                    # Passo 2: O encoding pesado só ocorre se houver um rosto validado.
                    rostos_encodings = face_recognition.face_encodings(rgb_frame_pequeno, localizacao_rostos)

                    for encoding in rostos_encodings:
                        matches = face_recognition.compare_faces(rostos_autorizados, encoding)
                        nome_identificado = "Desconhecido"
                        if True in matches:
                            nome_identificado = nomes_autorizados[matches.index(True)]
                        nomes_na_tela.append(nome_identificado)

                    escala = int(1 / FATOR_REDUCAO_IA)
                    novos_rostos = []
                    for (top, right, bottom, left), nome in zip(localizacao_rostos, nomes_na_tela):
                        novos_rostos.append((top * escala, right * escala, bottom * escala, left * escala, nome))

                    with lock_rostos_tela:
                        rostos_detectados_na_tela = novos_rostos

                    # Ação de abrir porta se alguém foi reconhecido e cooldown permite
                    if not em_cooldown.is_set():
                        em_cooldown.set()
                        threading.Thread(
                            target=processar_acesso_background,
                            args=(nomes_na_tela, frame_ia.copy()),
                            daemon=True
                        ).start()
                else:
                    with lock_rostos_tela:
                        rostos_detectados_na_tela = []

        except Exception as e:
            print(f"⚠️ Erro IA: {e}")

        # Respira para liberar o CPU
        time.sleep(INTERVALO_IA)


# ==========================================================
# FUNÇÕES DE REDE E ALERTAS
# ==========================================================
def atualizar_dados_radar():
    url_radar = f"http://{IP_ESP}/radar"
    session = requests.Session()
    # Adicionamos "Connection: close" para forçar o ESP32 a não prender o socket (evita erro 23 - out of sockets)
    headers = HEADERS_AUTORIZACAO.copy()
    headers["Connection"] = "close"
    
    while True:
        try:
            resposta = session.get(url_radar, headers=headers, timeout=2)
            if resposta.status_code == 200:
                dados = resposta.json()
                with lock_radar:
                    dados_radar["distancia"] = dados.get("distancia", 9999)
                    dados_radar["zona"] = dados.get("zona", 0)
                    dados_radar["ativo"] = dados.get("ativo", False)
                    dados_radar["estado"] = dados.get("estado", 0)
                    dados_radar["standby"] = dados.get("standby", True)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erro ao buscar radar: {e}")
        except Exception as e:
            print(f"⚠️ Erro inesperado no radar: {e}")
        time.sleep(0.5)

def enviar_alerta_telegram(frame_imagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_TOKEN == "SEU_TELEGRAM_BOT_TOKEN":
        print("[TELEGRAM] Token ou Chat ID não configurados no .env. Alerta pulado.")
        return
    print("A enviar alerta para o Telegram...")
    _, img_codificada = cv2.imencode('.jpg', frame_imagem)
    url_telegram = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    dados = {"chat_id": TELEGRAM_CHAT_ID, "caption": "🚨 ALERTA: Rosto desconhecido detetado na porta!"}
    arquivos = {"photo": ("alerta.jpg", img_codificada.tobytes(), "image/jpeg")}
    try:
        requests.post(url_telegram, data=dados, files=arquivos, timeout=10)
    except Exception as e:
        print(f"⚠️ Erro ao enviar alerta Telegram: {e}")


def registar_acesso(nome, status):
    ficheiro = "historico_acessos.csv"
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    existe = os.path.isfile(ficheiro)
    with open(ficheiro, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        if not existe:
            writer.writerow(['Data e Hora', 'Nome Identificado', 'Status do Acesso'])
        writer.writerow([agora, nome, status])
    
    if SALVAR_SD:
        import urllib.parse
        try:
            params = urllib.parse.urlencode({'data': agora, 'nome': nome, 'status': status})
            url_sd = f"http://{IP_ESP}/salvar_sd?{params}"
            requests.get(url_sd, headers=HEADERS_AUTORIZACAO, timeout=TIMEOUT_REQUESTS)
        except Exception as e:
            print(f"⚠️ Erro ao enviar log para SD: {e}")


def enviar_comando_esp(url):
    try:
        requests.get(url, headers=HEADERS_AUTORIZACAO, timeout=TIMEOUT_REQUESTS)
    except Exception as e:
        print(f"⚠️ Erro ao enviar comando para ESP: {e}")


def processar_acesso_background(nomes_encontrados, frame_copia):
    try:
        enviar_comando_esp(URL_ANALISANDO)
        time.sleep(0.5)
        alguem_autorizado = False

        for nome in nomes_encontrados:
            if nome != "Desconhecido":
                alguem_autorizado = True
                if EXIGIR_2FA_DTW:
                    with lock_2fa:
                        estado_2fa["aguardando_assinatura"] = True
                        estado_2fa["usuario_facial"] = nome
                        estado_2fa["expira_em"] = time.time() + 60.0
                    print(f"\n🟡 [1º Fator OK] Rosto de '{nome}' reconhecido! Aguardando assinatura DTW em /tablet (60s)...")
                else:
                    print(f"\n🟢 Acesso Concedido para: {nome}! A abrir a porta...")
                    enviar_comando_esp(URL_ABRIR)
                    registar_acesso(nome, "🟢 Acesso Concedido (Facial)")
                break

        if not alguem_autorizado:
            print("\n🔴 Rosto Desconhecido. Acesso Negado.")
            enviar_comando_esp(URL_NEGADO)
            registar_acesso("Desconhecido", "🔴 Acesso Negado (Alerta)")
            enviar_alerta_telegram(frame_copia)
    finally:
        # Garante que o cooldown só vai começar a contar DEPOIS que todo o processo
        # (incluindo o tempo de upload pro Telegram) finalizar.
        threading.Timer(COOLDOWN_SEGUNDOS, em_cooldown.clear).start()


# ==========================================================
# INICIALIZAÇÃO DO SISTEMA
# ==========================================================
rostos_autorizados = []
nomes_autorizados = []
print(f"A ler a pasta '{PASTA_ROSTOS}' e a treinar a IA...")

if os.path.exists(PASTA_ROSTOS):
    for nome_arquivo in os.listdir(PASTA_ROSTOS):
        if nome_arquivo.lower().endswith((".jpg", ".jpeg", ".png")):
            caminho_imagem = os.path.join(PASTA_ROSTOS, nome_arquivo)
            imagem_lida = cv2.imread(caminho_imagem)
            if imagem_lida is None:
                continue

            imagem_rgb = cv2.cvtColor(imagem_lida, cv2.COLOR_BGR2RGB)
            imagem_perfeita = np.ascontiguousarray(imagem_rgb, dtype=np.uint8)
            encodings = face_recognition.face_encodings(imagem_perfeita)

            if len(encodings) > 0:
                rostos_autorizados.append(encodings[0])
                nome = os.path.splitext(nome_arquivo)[0]
                nomes_autorizados.append(nome)
                print(f"- Rosto de '{nome}' treinado com sucesso!")
else:
    print(f"⚠️ Pasta '{PASTA_ROSTOS}' não encontrada. Nenhum rosto autorizado foi carregado.")

# INICIA AS THREADS
threading.Thread(target=ler_camera_sem_parar, daemon=True).start()
threading.Thread(target=processar_ia_continuamente, daemon=True).start()
threading.Thread(target=atualizar_dados_radar, daemon=True).start()

if __name__ == '__main__':
    print("\n🚀 Sistema Otimizado e Fluido! Painel Central: http://localhost:5000 | Tablet DTW: http://localhost:5000/tablet")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
