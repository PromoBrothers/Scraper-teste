# /mercado_livre_scraper/app/services.py

import os
from dotenv import load_dotenv
import requests
import uuid
from PIL import Image
from io import BytesIO
from .database import supabase # Importa o cliente do módulo database

load_dotenv()

USER_AGENT = os.getenv("USER_AGENT")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
N8N_AI_AGENT_URL = os.getenv("N8N_AI_AGENT_URL")

headers = {'User-Agent': USER_AGENT}

def processar_imagem_para_quadrado(url_imagem, tamanho_saida=(500, 500), cor_fundo=(255, 255, 255)):
    """
    Baixa e processa a imagem para o formato quadrado.
    Redimensiona a imagem para caber *inteira* no quadrado e centraliza.
    Retorna os bytes da imagem em formato JPEG, ou None se falhar.
    """
    try:
        if not url_imagem:
            return None
        response = requests.get(url_imagem, headers=headers, timeout=15)
        response.raise_for_status()
        img_original = Image.open(BytesIO(response.content))

        # Converte para RGB se necessário, preenchendo transparências
        if img_original.mode in ('RGBA', 'P', 'LA'):
            fundo = Image.new('RGB', img_original.size, cor_fundo)
            fundo.paste(img_original, (0, 0), img_original.convert('RGBA'))
            img = fundo
        else:
            img = img_original.convert('RGB')

        # Calcula a proporção para redimensionar a imagem para caber no quadrado
        largura_img, altura_img = img.size
        largura_saida, altura_saida = tamanho_saida

        ratio = min(largura_saida / largura_img, altura_saida / altura_img)
        nova_largura = int(largura_img * ratio)
        nova_altura = int(altura_img * ratio)

        img_redimensionada = img.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)

        # Cria a imagem quadrada de fundo e cola a imagem redimensionada no centro
        img_quadrada = Image.new('RGB', tamanho_saida, cor_fundo)
        pos_x = (largura_saida - nova_largura) // 2
        pos_y = (altura_saida - nova_altura) // 2
        img_quadrada.paste(img_redimensionada, (pos_x, pos_y))

        buffer = BytesIO()
        img_quadrada.save(buffer, format='JPEG', quality=90)
        buffer.seek(0)
        
        return buffer.getvalue()

    except Exception as e:
        print(f"ERRO AO PROCESSAR IMAGEM: {e}")
        return None

def upload_imagem_processada(image_bytes, bucket_name=None):
    """Faz o upload dos bytes de uma imagem para o Supabase Storage."""
    try:
        if bucket_name is None:
            bucket_name = os.getenv('BUCKET_NAME', 'imagens-produtos')
            
        file_name = f"processed_{uuid.uuid4()}.jpg"
        
        # Upload da imagem
        upload_response = supabase.storage.from_(bucket_name).upload(
            file=image_bytes, 
            path=file_name, 
            file_options={"content-type": "image/jpeg"}
        )
        
        if upload_response:
            # Obter URL pública
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
            print(f"DEBUG: Imagem uploaded com sucesso: {public_url}")
            return public_url
        else:
            print("ERRO: Falha no upload da imagem")
            return None
            
    except Exception as e:
        print(f"ERRO NO UPLOAD PARA O SUPABASE STORAGE: {e}")
        return None

def enviar_para_webhook(payload):
    """Envia um payload para o webhook configurado e retorna a resposta."""
    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mercado-Livre-Scraper/1.0'},
        timeout=60
    )
    
    # Tentar extrair mensagem da resposta do webhook
    webhook_message = None
    if response.status_code in [200, 201, 202]:
        try:
            response_data = response.json()
            # Verificar diferentes formatos de resposta possíveis
            if isinstance(response_data, dict):
                webhook_message = (
                    response_data.get('message') or 
                    response_data.get('response') or 
                    response_data.get('text') or
                    response_data.get('content')
                )
            elif isinstance(response_data, str):
                webhook_message = response_data
        except:
            # Se não conseguir fazer parse do JSON, usar o texto bruto
            webhook_message = response.text if len(response.text) > 10 else None
    
    # Adicionar a mensagem do webhook à resposta
    response.webhook_message = webhook_message
    return response

def formatar_mensagem_com_ia(produto_dados):
    """
    Envia os dados do produto para o agente de IA do n8n e retorna a mensagem formatada.
    """
    if not N8N_AI_AGENT_URL:
        raise Exception("N8N_AI_AGENT_URL não configurada no .env")
    
    try:
        # Preparar payload para o agente de IA
        payload = {
            "titulo": produto_dados.get('titulo', ''),
            "preco_atual": produto_dados.get('preco_atual', ''),
            "preco_original": produto_dados.get('preco_original'),
            "desconto": produto_dados.get('desconto'),
            "tem_promocao": produto_dados.get('tem_promocao', False),
            "link": produto_dados.get('afiliado_link') or produto_dados.get('link', ''),
            "fonte": produto_dados.get('fonte', ''),
            "plataforma": produto_dados.get('plataforma', '')
        }
        
        # Enviar para o agente de IA do n8n
        response = requests.post(
            N8N_AI_AGENT_URL,
            json=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mercado-Livre-Scraper/1.0'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            # Assumindo que o agente retorna a mensagem no campo 'message'
            # Ajuste conforme o formato de resposta do seu agente
            if isinstance(result, dict) and 'message' in result:
                return result['message']
            elif isinstance(result, str):
                return result
            else:
                # Fallback para o primeiro valor string encontrado
                for key, value in result.items():
                    if isinstance(value, str) and len(value) > 10:
                        return value
                raise Exception(f"Formato de resposta inesperado: {result}")
        else:
            raise Exception(f"Agente de IA retornou status {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Erro ao formatar mensagem com IA: {e}")
        raise e