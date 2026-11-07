import cv2
import numpy as np
import os
import glob

def extrair_palavras_da_imagem(caminho_imagem, pasta_saida, prefixo_nome):
    """
    Lê uma imagem de anotações, foca na tinta escura,
    encontra as palavras e recorta cada uma, salvando na pasta_saida.
    """
    if not os.path.exists(pasta_saida):
        os.makedirs(pasta_saida)

    # 1. Carregar a imagem
    imagem = cv2.imread(caminho_imagem)
    if imagem is None:
        print(f"⚠️ Erro ao ler imagem: {caminho_imagem}")
        return 0
        
    imagem_cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

    # 2. Binarização (Destacar o texto preto no fundo branco)
    # Usa limiarização de Otsu para separar perfeitamente a tinta do papel
    _, binaria = cv2.threshold(imagem_cinza, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    # 3. Dilatação (Juntar letras próximas para formar palavras inteiras)
    # Usamos um kernel retangular largo para juntar a palavra horizontalmente
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
    dilatada = cv2.dilate(binaria, kernel, iterations=1)

    # 4. Encontrar os contornos (caixas em volta das palavras)
    contornos, _ = cv2.findContours(dilatada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    contador = 0
    for contorno in contornos:
        x, y, w, h = cv2.boundingRect(contorno)
        
        # Filtro de tamanho para ignorar pontinhos de sujeira, vírgulas soltas ou a página inteira
        if w > 40 and h > 20 and w < imagem.shape[1] * 0.8:
            # Adicionar uma pequena margem (padding) ao redor da palavra para a IA respirar
            margem = 8
            x1 = max(0, x - margem)
            y1 = max(0, y - margem)
            x2 = min(imagem.shape[1], x + w + margem)
            y2 = min(imagem.shape[0], y + h + margem)
            
            recorte = imagem[y1:y2, x1:x2]
            
            # Salva o recorte
            nome_arquivo = f"{pasta_saida}/{prefixo_nome}_{contador:04d}.png"
            cv2.imwrite(nome_arquivo, recorte)
            contador += 1
            
    print(f"✅ [{os.path.basename(caminho_imagem)}] Extraídas {contador} palavras/frases curtas.")
    return contador

def processar_pasta(pasta_origem, pasta_destino):
    print("🚀 Iniciando extração mágica de palavras...")
    total_recortes = 0
    
    arquivos = glob.glob(f"{pasta_origem}/*.jpg") + glob.glob(f"{pasta_origem}/*.png")
    
    if len(arquivos) == 0:
        print(f"⚠️ Nenhuma imagem encontrada na pasta '{pasta_origem}'.")
        print("Coloque as imagens lá e rode o script novamente.")
        return

    for arquivo in arquivos:
        # Usa o nome antes do primeiro underscore para ser o nome da pasta (o autor da letra)
        nome_base = os.path.splitext(os.path.basename(arquivo))[0]
        autor = nome_base.split("_")[0] if "_" in nome_base else "desconhecido"
        
        pasta_autor = os.path.join(pasta_destino, autor)
        qtd = extrair_palavras_da_imagem(arquivo, pasta_autor, nome_base)
        total_recortes += qtd
        
    print(f"\n🎉 Finalizado! Um total de {total_recortes} recortes foram gerados e organizados em '{pasta_destino}'.")

if __name__ == "__main__":
    PASTA_ANOTACOES = "dataset_bruto"
    PASTA_RECORTES = "dataset_recortado"
    
    # Se a pasta não existe, cria e avisa o usuário
    if not os.path.exists(PASTA_ANOTACOES):
        os.makedirs(PASTA_ANOTACOES)
        print(f"📂 Criei a pasta vazia '{PASTA_ANOTACOES}'.")
        print("👉 POR FAVOR, COLOQUE SUAS IMAGENS (PNG/JPG) NELA.")
        print("💡 DICA: Nomeie os arquivos com o nome da pessoa seguido de '_'.")
        print("Exemplo: 'joao_nota1.jpg', 'joao_nota2.jpg', 'maria_fisica.png'.")
    else:
        processar_pasta(PASTA_ANOTACOES, PASTA_RECORTES)
