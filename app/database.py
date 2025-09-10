# /mercado_livre_scraper/app/database.py

import os
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def salvar_promocao(produto_dados, final_message=None, agendamento_data=None):
    """Salva os dados de uma promoção no Supabase."""
    try:
        if agendamento_data and isinstance(agendamento_data, datetime.datetime):
            agendamento_data = agendamento_data.isoformat()
        
        data_to_insert = {
            "titulo": produto_dados.get("titulo"),
            "preco_atual": produto_dados.get("preco_atual"),
            "preco_original": produto_dados.get("preco_original"),
            "desconto": produto_dados.get("desconto"),
            "link_produto": produto_dados.get("link"),
            "link_afiliado": produto_dados.get("afiliado_link"),
            "imagem_url": produto_dados.get("imagem"),
            "condicao": produto_dados.get("condicao"),
            "vendedor": produto_dados.get("vendedor"),
            "disponivel": produto_dados.get("disponivel"),
            "descricao": produto_dados.get("descricao"),
            "final_message": final_message,
            "agendamento": agendamento_data,
            "cupons": produto_dados.get("cupons", []),
            "processed_image_url": produto_dados.get("processed_image_url"),
            "fonte": produto_dados.get("fonte") # Adicionado para a visão unificada
        }
        
        supabase.table("promocoes").insert(data_to_insert).execute()
        print("DEBUG: Dados salvos no Supabase.")
        return True
        
    except Exception as e:
        print(f"--- ERRO AO SALVAR NO SUPABASE ---: {e}")
        return False

def listar_produtos_db(status_filter, ordem_order):
    """Lista produtos do Supabase com base nos filtros."""
    query = supabase.table("promocoes").select("*")
    if status_filter == 'agendado':
        query = query.not_.is_("agendamento", "null")
        query = query.order("agendamento", desc=(ordem_order == 'desc'))
    elif status_filter == 'nao-agendado':
        query = query.is_("agendamento", "null")
        query = query.order("created_at", desc=(ordem_order == 'desc'))
    else: # 'todos'
        query = query.order("created_at", desc=(ordem_order == 'desc'))

    response = query.execute()
    return response.data

def deletar_produto_db(produto_id):
    """Deleta um produto do Supabase pelo ID."""
    return supabase.table("promocoes").delete().eq("id", produto_id).execute()

def agendar_produto_db(produto_id, agendamento_iso):
    """Atualiza o agendamento de um produto no Supabase."""
    return supabase.table("promocoes").update({'agendamento': agendamento_iso}).eq("id", produto_id).execute()

def obter_produto_db(produto_id):
    """Busca um produto específico no Supabase pelo ID."""
    try:
        response = supabase.table("promocoes").select("*").eq("id", produto_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Erro ao buscar produto no Supabase: {e}")
        return None

def atualizar_produto_db(produto_id, dados_atualizacao):
    """Atualiza dados específicos de um produto no Supabase."""
    return supabase.table("promocoes").update(dados_atualizacao).eq("id", produto_id).execute()

# As demais funções do database.py (listar_imagens_bucket, etc.) permanecem as mesmas.
def listar_imagens_bucket(bucket_name="imagens", pasta="", search_term="", limite=20, offset=0):
    try:
        # Primeiro, vamos pegar um número maior de itens para garantir que temos dados suficientes
        response = supabase.storage.from_(bucket_name).list(path=pasta, options={'limit': 2000})
        if not response:
            return {'imagens': [], 'total': 0}
        
        # Filtrar apenas arquivos de imagem e aplicar busca
        todas_imagens = []
        for arquivo in response:
            nome = arquivo.get('name', '')
            if nome and any(nome.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
                # Aplicar filtro de busca se fornecido
                if not search_term or search_term.lower() in nome.lower():
                    caminho_completo = f"{pasta}/{nome}" if pasta else nome
                    url_publica = supabase.storage.from_(bucket_name).get_public_url(caminho_completo)
                    
                    # Extrair informações do arquivo
                    todas_imagens.append({
                        'nome': nome,
                        'url': url_publica,
                        'tamanho': arquivo.get('metadata', {}).get('size', 0) if arquivo.get('metadata') else 0,
                        'modificado_em': arquivo.get('updated_at', ''),
                        'path_completo': caminho_completo
                    })
        
        # Ordenar por data de modificação (mais recentes primeiro)
        todas_imagens.sort(key=lambda x: x.get('modificado_em', ''), reverse=True)
        
        # Calcular total depois da filtragem
        total = len(todas_imagens)
        
        # Aplicar paginação
        inicio = offset
        fim = offset + limite
        imagens_paginadas = todas_imagens[inicio:fim]
        
        return {
            'imagens': imagens_paginadas,
            'total': total,
            'limite': limite,
            'offset': offset,
            'total_paginas': (total + limite - 1) // limite if limite > 0 else 1
        }
        
    except Exception as e:
        print(f"Erro ao listar imagens do bucket: {e}")
        return {'imagens': [], 'total': 0}

def obter_url_publica_imagem(bucket_name="imagens", caminho_arquivo=""):
    try:
        return supabase.storage.from_(bucket_name).get_public_url(caminho_arquivo)
    except Exception as e:
        print(f"Erro ao obter URL pública: {e}")
        return None

def listar_pastas_bucket(bucket_name="imagens", pasta_pai=""):
    try:
        response = supabase.storage.from_(bucket_name).list(path=pasta_pai)
        pastas = []
        for item in response:
            nome = item.get('name', '')
            if not any(nome.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.txt', '.json']):
                pastas.append({
                    'nome': nome,
                    'path_completo': f"{pasta_pai}/{nome}" if pasta_pai else nome
                })
        return pastas
    except Exception as e:
        print(f"Erro ao listar pastas do bucket: {e}")
        return []

def criar_bucket_se_nao_existir(bucket_name="imagens-produtos"):
    """Cria o bucket se ele não existir."""
    try:
        # Tentar listar buckets para verificar se existe
        buckets = supabase.storage.list_buckets()
        bucket_exists = any(bucket.name == bucket_name for bucket in buckets)
        
        if not bucket_exists:
            # Criar bucket público para imagens
            supabase.storage.create_bucket(bucket_name, options={"public": True})
            print(f"DEBUG: Bucket '{bucket_name}' criado com sucesso")
        else:
            print(f"DEBUG: Bucket '{bucket_name}' já existe")
        return True
    except Exception as e:
        print(f"Erro ao criar/verificar bucket: {e}")
        return False