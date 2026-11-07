import os
import csv
import json
import math
import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_DISPONIVEL = True
except ImportError:
    SKLEARN_DISPONIVEL = False

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_GABARITOS = os.path.join(PASTA_BASE, "assinaturas_cadastradas.json")
ARQUIVO_DATASET_CSV = os.path.join(PASTA_BASE, "dataset_comportamental.csv")

COLUNAS_FEATURES_BIOMECANICAS = [
    "tempo_total_ms",
    "tempo_pausa_ms",
    "razao_pausa_tempo",
    "num_tracos",
    "vel_media",
    "vel_max",
    "vel_std",
    "acel_media",
    "acel_std",
    "jerk_medio",
    "jerk_std",
    "pressao_media",
]


def extrair_serie_temporal(pontos_brutos, num_pontos_reamostragem=64):
    """
    Recebe uma lista de pontos brutos capturados na tela touch:
        [{"x": float, "y": float, "t": float (ms), "stroke": int, "p": float (pressão/raio)}, ...]
    Retorna:
        - serie_features: matriz NumPy (N, 6) com [x_norm, y_norm, vx_norm, vy_norm, v_norm, a_norm]
        - metricas_globais: dicionário com 12 features biomecânicas/neuromotoras para o Dataset e Isolation Forest
    """
    if not pontos_brutos or len(pontos_brutos) < 8:
        raise ValueError("Assinatura muito curta. Desenhe um traço contínuo com pelo menos 8 pontos.")

    xs = np.array([float(p["x"]) for p in pontos_brutos], dtype=np.float64)
    ys = np.array([float(p["y"]) for p in pontos_brutos], dtype=np.float64)
    ts = np.array([float(p["t"]) for p in pontos_brutos], dtype=np.float64)
    strokes = np.array([int(p.get("stroke", 1)) for p in pontos_brutos], dtype=np.int32)
    pressoes = np.array([float(p.get("p", 0.5)) for p in pontos_brutos], dtype=np.float64)

    # Tempo relativo ao início do primeiro toque (em milissegundos)
    t_rel_ms = ts - ts[0]
    tempo_total_ms = float(max(t_rel_ms[-1], 1.0))

    # Calcula tempo de pausa no ar entre traços (Flight Time / Pen-up time)
    tempo_pausa_ms = 0.0
    num_tracos = int(len(np.unique(strokes)))
    for i in range(1, len(pontos_brutos)):
        if strokes[i] != strokes[i - 1]:
            dt_pausa = ts[i] - ts[i - 1]
            if dt_pausa > 0:
                tempo_pausa_ms += float(dt_pausa)

    razao_pausa_tempo = float(tempo_pausa_ms / tempo_total_ms)

    # 1. Normalização Espacial (Invariância a posição e tamanho da tela do celular/tablet)
    x_min, x_max = np.min(xs), np.max(xs)
    y_min, y_max = np.min(ys), np.max(ys)
    escala = max(x_max - x_min, y_max - y_min, 1e-5)

    x_norm = (xs - np.mean(xs)) / escala
    y_norm = (ys - np.mean(ys)) / escala

    # 2. Derivadas cinéticas de 1ª, 2ª e 3ª ordem: Velocidade (v), Aceleração (a) e Arranco/Jerk (j = da/dt)
    dt = np.diff(t_rel_ms) / 1000.0
    dt = np.where(dt <= 1e-4, 1e-4, dt)

    dx = np.diff(x_norm)
    dy = np.diff(y_norm)

    mudanca_traco = np.diff(strokes) != 0
    dx[mudanca_traco] = 0.0
    dy[mudanca_traco] = 0.0

    vx = np.concatenate([[0.0], dx / dt])
    vy = np.concatenate([[0.0], dy / dt])
    v_escalar = np.sqrt(vx ** 2 + vy ** 2)

    dv = np.diff(v_escalar)
    dv[mudanca_traco] = 0.0
    acel = np.concatenate([[0.0], dv / dt])

    da = np.diff(acel)
    da[mudanca_traco] = 0.0
    jerk = np.concatenate([[0.0], da / dt])

    vel_media = float(np.mean(v_escalar))
    vel_max = float(np.max(v_escalar))
    vel_std = float(np.std(v_escalar))
    acel_media = float(np.mean(np.abs(acel)))
    acel_std = float(np.std(acel))
    jerk_medio = float(np.mean(np.abs(jerk)))
    jerk_std = float(np.std(jerk))
    pressao_media = float(np.mean(pressoes))

    # 3. Normalização Z-Score das curvas cinéticas para o alinhamento DTW
    vx_z = (vx - np.mean(vx)) / (np.std(vx) + 1e-6)
    vy_z = (vy - np.mean(vy)) / (np.std(vy) + 1e-6)
    v_z = (v_escalar - np.mean(v_escalar)) / (np.std(v_escalar) + 1e-6)
    a_z = (acel - np.mean(acel)) / (np.std(acel) + 1e-6)

    # 4. Reamostragem temporal uniforme para N = 64 pontos
    idx_orig = np.linspace(0.0, 1.0, len(xs))
    idx_novo = np.linspace(0.0, 1.0, num_pontos_reamostragem)

    serie_features = np.column_stack([
        np.interp(idx_novo, idx_orig, x_norm) * 2.0,  # Trajetória X
        np.interp(idx_novo, idx_orig, y_norm) * 2.0,  # Trajetória Y
        np.interp(idx_novo, idx_orig, vx_z) * 1.0,    # Dinâmica Vx
        np.interp(idx_novo, idx_orig, vy_z) * 1.0,    # Dinâmica Vy
        np.interp(idx_novo, idx_orig, v_z) * 0.8,     # Perfil de Velocidade |V|
        np.interp(idx_novo, idx_orig, a_z) * 0.5,     # Perfil de Aceleração
    ])

    metricas_globais = {
        "tempo_total_ms": round(tempo_total_ms, 1),
        "tempo_pausa_ms": round(tempo_pausa_ms, 1),
        "razao_pausa_tempo": round(razao_pausa_tempo, 4),
        "num_tracos": num_tracos,
        "vel_media": round(vel_media, 4),
        "vel_max": round(vel_max, 4),
        "vel_std": round(vel_std, 4),
        "acel_media": round(acel_media, 4),
        "acel_std": round(acel_std, 4),
        "jerk_medio": round(jerk_medio, 4),
        "jerk_std": round(jerk_std, 4),
        "pressao_media": round(pressao_media, 4),
        "num_pontos_brutos": len(pontos_brutos),
    }

    return serie_features, metricas_globais


def vetorizar_metricas(metricas_dict):
    """Extrai o vetor numérico de 12 features biomecânicas para o Isolation Forest."""
    return np.array([float(metricas_dict.get(col, 0.0)) for col in COLUNAS_FEATURES_BIOMECANICAS], dtype=np.float64)


def salvar_linha_dataset_csv(usuario, rotulo_classe, metricas, dtw_dist=0.0):
    """
    Salva cada amostra coletada em 'dataset_comportamental.csv' para compor o
    Dataset formal do projeto (permitindo análise no Excel/Python e geração de gráficos).
    """
    existe = os.path.isfile(ARQUIVO_DATASET_CSV)
    cabecalho = ["usuario", "classe_amostra", "dtw_distancia"] + COLUNAS_FEATURES_BIOMECANICAS + ["num_pontos_brutos"]
    with open(ARQUIVO_DATASET_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if not existe:
            writer.writerow(cabecalho)
        linha = (
            [usuario, rotulo_classe, round(float(dtw_dist), 4)]
            + [metricas.get(c, 0.0) for c in COLUNAS_FEATURES_BIOMECANICAS]
            + [metricas.get("num_pontos_brutos", 0)]
        )
        writer.writerow(linha)


def calcular_dtw(serie_a, serie_b, banda_sakoe_chiba=0.25):
    """
    Calcula o alinhamento temporal ótimo DTW (Dynamic Time Warping) multidimensional
    com restrição de janela de Sakoe-Chiba.
    """
    n, m = len(serie_a), len(serie_b)
    janela = max(int(max(n, m) * banda_sakoe_chiba), abs(n - m) + 4)

    dtw_matrix = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    dtw_matrix[0, 0] = 0.0

    for i in range(1, n + 1):
        j_ini = max(1, i - janela)
        j_fim = min(m + 1, i + janela + 1)
        for j in range(j_ini, j_fim):
            diff = serie_a[i - 1] - serie_b[j - 1]
            custo_local = math.sqrt(float(np.dot(diff, diff)))
            menor_vizinho = min(
                dtw_matrix[i - 1, j],
                dtw_matrix[i, j - 1],
                dtw_matrix[i - 1, j - 1],
            )
            dtw_matrix[i, j] = custo_local + menor_vizinho

    return float(dtw_matrix[n, m] / (n + m))


class GerenciadorBiometriaComportamental:
    """
    Arquitetura Bancária Híbrida (Proposta de Projeto):
      1. Dataset Comportamental Dinâmico por usuário (salvo em JSON e exportado em CSV)
      2. Alinhamento Temporal DTW Multidimensional (Trajetória + Velocidade + Aceleração)
      3. Modelo Isolation Forest (scikit-learn) para Detecção de Anomalia Neuromotora
    """
    def __init__(self, caminho_arquivo=ARQUIVO_GABARITOS):
        self.caminho_arquivo = caminho_arquivo
        self.banco_usuarios = {}
        self.modelos_iforest = {}
        self.carregar()

    def carregar(self):
        if os.path.exists(self.caminho_arquivo):
            try:
                with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                    self.banco_usuarios = json.load(f)
                for nome in self.banco_usuarios:
                    self._treinar_isolation_forest_usuario(nome)
            except Exception as e:
                print(f"⚠️ Erro ao carregar gabaritos DTW: {e}")
                self.banco_usuarios = {}
        else:
            self.banco_usuarios = {}

    def salvar(self):
        with open(self.caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(self.banco_usuarios, f, ensure_ascii=False, indent=2)

    def _treinar_isolation_forest_usuario(self, nome_usuario):
        """
        Treina um modelo Isolation Forest (Floresta de Isolamento) sobre o Dataset
        biomecânico do usuário. Quando o usuário possui >= 5 amostras no dataset,
        o Isolation Forest aprende a fronteira de normalidade neuromotora em 12 dimensões.
        """
        if not SKLEARN_DISPONIVEL or nome_usuario not in self.banco_usuarios:
            return False

        lista_metricas = self.banco_usuarios[nome_usuario].get("metricas", [])
        if len(lista_metricas) < 5:
            return False

        X_raw = np.array([vetorizar_metricas(m) for m in lista_metricas], dtype=np.float64)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_raw)

        # Data augmentation leve (jitter gaussiano de 5% nas próprias amostras do usuário)
        # para estabilizar as árvores de isolamento em datasets de 5 a 30 amostras
        rng = np.random.default_rng(42)
        X_aug = np.vstack([
            X_scaled,
            X_scaled + rng.normal(0, 0.12, X_scaled.shape),
            X_scaled + rng.normal(0, 0.20, X_scaled.shape),
        ])

        clf = IsolationForest(
            n_estimators=150,
            contamination=0.06,
            random_state=42,
        )
        clf.fit(X_aug)

        self.modelos_iforest[nome_usuario] = {
            "scaler": scaler,
            "iforest": clf,
            "n_amostras_treino": len(lista_metricas),
        }
        return True

    def listar_usuarios(self):
        resumo = {}
        for nome, dados in self.banco_usuarios.items():
            n_amostras = len(dados.get("amostras", []))
            resumo[nome] = {
                "amostras": n_amostras,
                "iforest_ativo": nome in self.modelos_iforest,
                "meta_dataset": 15,
                "limiar_dtw": dados.get("limiar_dtw", 0.65),
                "tempo_medio_ms": dados.get("tempo_medio_ms", 0),
                "vel_media_ref": dados.get("vel_media_ref", 0),
            }
        return resumo

    def limpar_usuario(self, nome_usuario):
        nome_limpo = nome_usuario.strip()
        removido = False
        if nome_limpo in self.banco_usuarios:
            del self.banco_usuarios[nome_limpo]
            self.modelos_iforest.pop(nome_limpo, None)
            self.salvar()
            removido = True

        # Também remove as linhas desse usuário do dataset_comportamental.csv
        if os.path.isfile(ARQUIVO_DATASET_CSV):
            try:
                with open(ARQUIVO_DATASET_CSV, mode="r", encoding="utf-8") as f:
                    linhas = list(csv.reader(f, delimiter=";"))
                if linhas:
                    cabecalho = linhas[0]
                    filtradas = [cabecalho] + [
                        row for row in linhas[1:]
                        if len(row) > 0 and row[0].strip().lower() != nome_limpo.lower()
                    ]
                    with open(ARQUIVO_DATASET_CSV, mode="w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=";")
                        writer.writerows(filtradas)
            except Exception as e:
                print(f"⚠️ Erro ao limpar CSV do usuário: {e}")

        return removido

    def remover_ultima_amostra(self, nome_usuario):
        """Remove apenas a última amostra cadastrada do usuário (Desfazer) e recalibra o modelo."""
        nome_limpo = nome_usuario.strip()
        if nome_limpo not in self.banco_usuarios:
            raise ValueError(f"Usuário '{nome_limpo}' não possui amostras cadastradas.")

        registro = self.banco_usuarios[nome_limpo]
        if not registro.get("amostras"):
            del self.banco_usuarios[nome_limpo]
            self.modelos_iforest.pop(nome_limpo, None)
            self.salvar()
            raise ValueError(f"Usuário '{nome_limpo}' não possui amostras para remover.")

        registro["amostras"].pop()
        if registro.get("metricas"):
            registro["metricas"].pop()

        restantes = len(registro["amostras"])
        if restantes == 0:
            del self.banco_usuarios[nome_limpo]
            self.modelos_iforest.pop(nome_limpo, None)
            self.salvar()
            return {"usuario": nome_limpo, "total_amostras": 0, "iforest_ativo": False, "limiar_dtw": 0.65}

        # Recalcula estatísticas com as amostras que sobraram
        amostras_np = [np.array(a, dtype=np.float64) for a in registro["amostras"]]
        tempos = [m["tempo_total_ms"] for m in registro["metricas"]]
        vels = [m["vel_media"] for m in registro["metricas"]]
        registro["tempo_medio_ms"] = round(float(np.mean(tempos)), 1)
        registro["vel_media_ref"] = round(float(np.mean(vels)), 4)

        if len(amostras_np) >= 2:
            dists_internas = []
            for i in range(len(amostras_np)):
                for j in range(i + 1, len(amostras_np)):
                    dists_internas.append(calcular_dtw(amostras_np[i], amostras_np[j]))
            media_dtw = float(np.mean(dists_internas))
            std_dtw = float(np.std(dists_internas))
            registro["limiar_dtw"] = round(max(0.65, min(1.05, media_dtw + 2.5 * max(std_dtw, 0.08))), 4)
        else:
            registro["limiar_dtw"] = 0.65

        if restantes >= 5:
            iforest_ativo = self._treinar_isolation_forest_usuario(nome_limpo)
        else:
            self.modelos_iforest.pop(nome_limpo, None)
            iforest_ativo = False

        self.salvar()
        return {
            "usuario": nome_limpo,
            "total_amostras": restantes,
            "iforest_ativo": iforest_ativo,
            "limiar_dtw": registro["limiar_dtw"],
        }

    def cadastrar_amostra(self, nome_usuario, pontos_brutos):
        nome_limpo = nome_usuario.strip()
        if not nome_limpo:
            raise ValueError("Nome do usuário não pode ser vazio.")

        serie, metricas = extrair_serie_temporal(pontos_brutos)

        if nome_limpo not in self.banco_usuarios:
            self.banco_usuarios[nome_limpo] = {
                "amostras": [],
                "metricas": [],
                "limiar_dtw": 0.65,
                "tempo_medio_ms": metricas["tempo_total_ms"],
                "vel_media_ref": metricas["vel_media"],
            }

        registro = self.banco_usuarios[nome_limpo]
        registro["amostras"].append(serie.tolist())
        registro["metricas"].append(metricas)

        # Mantém até 30 amostras no Dataset pessoal do usuário
        if len(registro["amostras"]) > 30:
            registro["amostras"] = registro["amostras"][-30:]
            registro["metricas"] = registro["metricas"][-30:]

        amostras_np = [np.array(a, dtype=np.float64) for a in registro["amostras"]]
        tempos = [m["tempo_total_ms"] for m in registro["metricas"]]
        vels = [m["vel_media"] for m in registro["metricas"]]

        registro["tempo_medio_ms"] = round(float(np.mean(tempos)), 1)
        registro["vel_media_ref"] = round(float(np.mean(vels)), 4)

        dtw_ultimo = 0.0
        if len(amostras_np) >= 2:
            dists_internas = []
            for i in range(len(amostras_np)):
                for j in range(i + 1, len(amostras_np)):
                    dists_internas.append(calcular_dtw(amostras_np[i], amostras_np[j]))
            media_dtw = float(np.mean(dists_internas))
            std_dtw = float(np.std(dists_internas))
            limiar_calculado = max(0.65, min(1.05, media_dtw + 2.5 * max(std_dtw, 0.08)))
            registro["limiar_dtw"] = round(limiar_calculado, 4)
            dtw_ultimo = float(np.mean([calcular_dtw(amostras_np[-1], ref) for ref in amostras_np[:-1]]))
        else:
            registro["limiar_dtw"] = 0.65

        # Salva no arquivo CSV do Dataset Comportamental e treina o Isolation Forest
        salvar_linha_dataset_csv(nome_limpo, "GENUINO_TREINO", metricas, dtw_ultimo)
        iforest_treinado = self._treinar_isolation_forest_usuario(nome_limpo)
        self.salvar()

        return {
            "usuario": nome_limpo,
            "total_amostras": len(registro["amostras"]),
            "iforest_ativo": iforest_treinado,
            "limiar_dtw": registro["limiar_dtw"],
            "metricas_amostra": metricas,
            "arquivo_csv": os.path.basename(ARQUIVO_DATASET_CSV),
        }

    def validar_assinatura(self, pontos_brutos, usuario_esperado=None, rotulo_teste="VALIDACAO_AO_VIVO"):
        """
        Executa a validação bancária em duas camadas:
          1. DTW Multidimensional (alinhamento elástico espaço-temporal)
          2. Isolation Forest + Perfil Neuromotor (tempo, pausas, velocidade, aceleração e jerk)
        """
        if not self.banco_usuarios:
            raise ValueError("Nenhuma assinatura cadastrada no Dataset! Colete amostras na aba 'Coletar Dataset' primeiro.")

        serie_teste, metricas_teste = extrair_serie_temporal(pontos_brutos)

        candidatos = (
            [usuario_esperado]
            if (usuario_esperado and usuario_esperado in self.banco_usuarios)
            else list(self.banco_usuarios.keys())
        )

        melhor_resultado = None

        for nome in candidatos:
            dados = self.banco_usuarios[nome]
            amostras_ref = [np.array(a, dtype=np.float64) for a in dados.get("amostras", [])]
            if not amostras_ref:
                continue

            distancias = [calcular_dtw(serie_teste, ref) for ref in amostras_ref]
            distancias_ordenadas = sorted(distancias)
            # Média das 3 amostras mais próximas do dataset do usuário
            k_vizinhos = min(3, len(distancias_ordenadas))
            dtw_base = float(np.mean(distancias_ordenadas[:k_vizinhos]))

            tempo_ref = max(float(dados.get("tempo_medio_ms", metricas_teste["tempo_total_ms"])), 100.0)
            vel_ref = max(float(dados.get("vel_media_ref", metricas_teste["vel_media"])), 0.1)

            razao_tempo = metricas_teste["tempo_total_ms"] / tempo_ref
            razao_vel = metricas_teste["vel_media"] / vel_ref

            penalidade_anomalia = 0.0
            motivos_anomalia = []

            if razao_tempo > 2.1 or razao_tempo < 0.35:
                penalidade_anomalia += 0.25 * abs(math.log(max(razao_tempo, 0.1)))
                motivos_anomalia.append(f"Ritmo temporal atípico ({razao_tempo:.2f}x do padrão)")

            if razao_vel < 0.45 or razao_vel > 2.2:
                penalidade_anomalia += 0.20 * abs(math.log(max(razao_vel, 0.1)))
                motivos_anomalia.append(f"Velocidade de traço incompatível ({razao_vel:.2f}x do padrão)")

            # Avaliação pelo Isolation Forest (quando o dataset tem >= 5 amostras)
            iforest_score = None
            iforest_anomalia = False
            if nome in self.modelos_iforest:
                modelo_info = self.modelos_iforest[nome]
                vetor_12d = vetorizar_metricas(metricas_teste).reshape(1, -1)
                vetor_norm = modelo_info["scaler"].transform(vetor_12d)
                # decision_function > 0 significa normal (inlier), < 0 significa anomalia (outlier)
                iforest_score = round(float(modelo_info["iforest"].decision_function(vetor_norm)[0]), 4)
                pred_iforest = int(modelo_info["iforest"].predict(vetor_norm)[0])
                if pred_iforest == -1 or iforest_score < 0.0:
                    iforest_anomalia = True
                    penalidade_if = min(0.30, max(0.08, abs(iforest_score) * 2.5))
                    penalidade_anomalia += penalidade_if
                    motivos_anomalia.append(f"Isolation Forest detectou anomalia neuromotora (score={iforest_score})")

            custo_final = dtw_base + penalidade_anomalia
            limiar = float(dados.get("limiar_dtw", 0.65))

            similaridade_pct = max(0.0, min(100.0, 100.0 * math.exp(-0.38 * (custo_final / max(limiar, 0.5)))))
            aprovado = bool(custo_final <= limiar)

            resultado_atual = {
                "aprovado": aprovado,
                "usuario": nome,
                "distancia_dtw": round(dtw_base, 4),
                "penalidade_anomalia": round(penalidade_anomalia, 4),
                "custo_final": round(custo_final, 4),
                "limiar_dtw": round(limiar, 4),
                "similaridade_pct": round(similaridade_pct, 1),
                "iforest_ativo": nome in self.modelos_iforest,
                "iforest_score": iforest_score,
                "iforest_anomalia": iforest_anomalia,
                "amostras_no_dataset": len(amostras_ref),
                "metricas": metricas_teste,
                "tempo_ref_ms": round(tempo_ref, 1),
                "motivos_anomalia": motivos_anomalia,
            }

            if melhor_resultado is None or resultado_atual["custo_final"] < melhor_resultado["custo_final"]:
                melhor_resultado = resultado_atual

        if melhor_resultado is not None:
            classe_csv = "APROVADO_2FA" if melhor_resultado["aprovado"] else "BLOQUEADO_FRAUDE"
            if rotulo_teste != "VALIDACAO_AO_VIVO":
                classe_csv = rotulo_teste
            salvar_linha_dataset_csv(
                melhor_resultado["usuario"],
                classe_csv,
                metricas_teste,
                melhor_resultado["distancia_dtw"],
            )

        return melhor_resultado
