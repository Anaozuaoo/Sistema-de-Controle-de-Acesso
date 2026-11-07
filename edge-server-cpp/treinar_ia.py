import cv2
import os
import sys
import numpy as np

def treinar_modelo(pasta_fotos="fotos_treinamento", arquivo_saida="cerebro_treinado.yml"):
    print("==================================================")
    print(" TREINAMENTO DO MODELO BIOMÉTRICO FACIAL (LBPH)    ")
    print("==================================================")

    cascade_path = "haarcascade_frontalface_default.xml"
    if not os.path.exists(cascade_path):
        print(f"ERRO: Arquivo '{cascade_path}' não encontrado no diretório atual.")
        return False

    detector = cv2.CascadeClassifier(cascade_path)
    recognizer = cv2.face.LBPHFaceRecognizer_create()

    if not os.path.exists(pasta_fotos):
        os.makedirs(pasta_fotos)
        print(f"Pasta '{pasta_fotos}' não existia e foi criada.")
        print(f"Por favor, adicione fotos da face autorizada dentro de '{pasta_fotos}/' e execute novamente.")
        return False

    arquivos = [f for f in os.listdir(pasta_fotos) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not arquivos:
        print(f"Nenhuma imagem encontrada em '{pasta_fotos}'. Adicione fotos e tente novamente.")
        return False

    faces = []
    ids = []
    print(f"Processando {len(arquivos)} imagens de '{pasta_fotos}'...")

    for arquivo in arquivos:
        caminho = os.path.join(pasta_fotos, arquivo)
        img = cv2.imread(caminho, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue

        rosto_detectado = detector.detectMultiScale(img, scaleFactor=1.2, minNeighbors=5)
        for (x, y, w, h) in rosto_detectado:
            faces.append(img[y:y+h, x:x+w])
            ids.append(1)  # ID 1 = Usuário autorizado padrão

    if not faces:
        print("Nenhum rosto foi detectado nas fotos fornecidas.")
        return False

    print(f"Treinando classificador LBPH com {len(faces)} amostras faciais extraídas...")
    recognizer.train(faces, np.array(ids))
    recognizer.save(arquivo_saida)

    print(f"SUCESSO! Modelo salvo em '{arquivo_saida}'.")
    return True

if __name__ == "__main__":
    pasta = sys.argv[1] if len(sys.argv) > 1 else "fotos_treinamento"
    treinar_modelo(pasta)
