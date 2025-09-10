import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import re
import random
from urllib.parse import urlencode, quote_plus
import concurrent.futures
from threading import Lock

load_dotenv()
USER_AGENT = os.getenv("USER_AGENT")
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = os.getenv("PROXY_PORT")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

headers = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

proxies = {}
if PROXY_HOST and PROXY_PORT and PROXY_USERNAME and PROXY_PASSWORD:
    proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }

# Lock para thread safety
results_lock = Lock()

def gerar_link_afiliado(url, plataforma):
    """Gera link de afiliado baseado na plataforma"""
    # IDs de afiliado - substitua pelos seus IDs reais
    affiliate_ids = {
        'shopee': 'seu_id_shopee',
        'aliexpress': 'seu_id_aliexpress', 
        'magazine': 'seu_id_magazine',
        'casasbahia': 'seu_id_casasbahia',
        'submarino': 'seu_id_submarino',
        'americanas': 'seu_id_americanas'
    }
    
    if plataforma in affiliate_ids:
        affiliate_id = affiliate_ids[plataforma]
        
        if plataforma == 'shopee':
            return f"{url}?af_siteid={affiliate_id}"
        elif plataforma == 'aliexpress':
            return f"{url}?aff_platform=link-c-tool&sk={affiliate_id}"
        elif plataforma in ['magazine', 'submarino']:
            return f"{url}?utm_source=afiliado&utm_medium=link&utm_campaign={affiliate_id}"
        elif plataforma == 'casasbahia':
            return f"{url}?parceiro={affiliate_id}"
        elif plataforma == 'americanas':
            return f"{url}?epar={affiliate_id}"
    
    return url

def scrape_shopee(produto, max_pages=2):
    """Scraping da Shopee"""
    produtos = []
    produto_formatado = quote_plus(produto)
    
    for page in range(max_pages):
        try:
            url = f'https://shopee.com.br/search?keyword={produto_formatado}&page={page}'
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Seletores para produtos da Shopee
            produto_items = soup.select('[data-sqe="item"]')
            
            for item in produto_items:
                try:
                    # Nome
                    nome_elem = item.select_one('[data-sqe="name"]')
                    nome = nome_elem.get_text().strip() if nome_elem else ""
                    
                    if not nome:
                        continue
                    
                    # Link
                    link_elem = item.select_one('a')
                    link = ""
                    if link_elem:
                        href = link_elem.get('href')
                        if href and href.startswith('/'):
                            link = f'https://shopee.com.br{href}'
                    
                    # Preço
                    preco_elem = item.select_one('[class*="price"]')
                    preco = "Preço não disponível"
                    if preco_elem:
                        preco_text = preco_elem.get_text().strip()
                        preco_match = re.search(r'[\d,]+\.?\d*', preco_text.replace('R$', '').replace(',', ''))
                        if preco_match:
                            preco = preco_match.group()
                    
                    # Imagem
                    img_elem = item.select_one('img')
                    imagem = ""
                    if img_elem:
                        imagem = img_elem.get('src') or img_elem.get('data-src', '')
                    
                    # Vendas
                    vendas_elem = item.select_one('[class*="sold"]')
                    vendas = ""
                    if vendas_elem:
                        vendas_text = vendas_elem.get_text()
                        vendas_match = re.search(r'(\d+)', vendas_text)
                        if vendas_match:
                            vendas = vendas_match.group(1)
                    
                    produto_dict = {
                        'nome': nome,
                        'link': link,
                        'link_afiliado': gerar_link_afiliado(link, 'shopee'),
                        'imagem': imagem,
                        'preco_atual': preco,
                        'preco_original': None,
                        'desconto': None,
                        'tem_promocao': False,
                        'rating': "",
                        'reviews': "",
                        'vendas': vendas,
                        'frete_gratis': 'frete grátis' in item.get_text().lower(),
                        'comissao_pct': "3.5", # Comissão média da Shopee
                        'plataforma': 'Shopee'
                    }
                    
                    produtos.append(produto_dict)
                    
                except Exception as e:
                    print(f"Erro ao processar produto Shopee: {e}")
                    continue
            
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"Erro na página {page} da Shopee: {e}")
            break
    
    return produtos

def scrape_magazine_luiza(produto, max_pages=2):
    """Scraping do Magazine Luiza"""
    produtos = []
    produto_formatado = quote_plus(produto)
    
    for page in range(1, max_pages + 1):
        try:
            url = f'https://www.magazineluiza.com.br/busca/{produto_formatado}/?page={page}'
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Seletores para produtos do Magazine Luiza
            produto_items = soup.select('[data-testid="product-card"]')
            
            for item in produto_items:
                try:
                    # Nome
                    nome_elem = item.select_one('h2, [data-testid="product-title"]')
                    nome = nome_elem.get_text().strip() if nome_elem else ""
                    
                    if not nome:
                        continue
                    
                    # Link
                    link_elem = item.select_one('a')
                    link = ""
                    if link_elem:
                        href = link_elem.get('href')
                        if href:
                            if href.startswith('/'):
                                link = f'https://www.magazineluiza.com.br{href}'
                            else:
                                link = href
                    
                    # Preço atual
                    preco_elem = item.select_one('[data-testid="price-value"]')
                    preco = "Preço não disponível"
                    if preco_elem:
                        preco_text = preco_elem.get_text().strip()
                        preco_match = re.search(r'[\d,]+\.?\d*', preco_text.replace('R$', '').replace(',', ''))
                        if preco_match:
                            preco = preco_match.group()
                    
                    # Preço original (se houver desconto)
                    preco_original = None
                    desconto = None
                    preco_original_elem = item.select_one('[data-testid="price-original"]')
                    if preco_original_elem:
                        original_text = preco_original_elem.get_text().strip()
                        original_match = re.search(r'[\d,]+\.?\d*', original_text.replace('R$', '').replace(',', ''))
                        if original_match:
                            preco_original = original_match.group()
                            
                            # Calcular desconto
                            try:
                                atual = float(preco.replace(',', '.'))
                                original = float(preco_original.replace(',', '.'))
                                desconto = int(((original - atual) / original) * 100)
                            except:
                                pass
                    
                    # Imagem
                    img_elem = item.select_one('img')
                    imagem = ""
                    if img_elem:
                        imagem = img_elem.get('src') or img_elem.get('data-src', '')
                    
                    produto_dict = {
                        'nome': nome,
                        'link': link,
                        'link_afiliado': gerar_link_afiliado(link, 'magazine'),
                        'imagem': imagem,
                        'preco_atual': preco,
                        'preco_original': preco_original,
                        'desconto': desconto,
                        'tem_promocao': desconto is not None,
                        'rating': "",
                        'reviews': "",
                        'vendas': "",
                        'frete_gratis': 'frete grátis' in item.get_text().lower(),
                        'comissao_pct': "4.0", # Comissão média do Magazine Luiza
                        'plataforma': 'Magazine Luiza'
                    }
                    
                    produtos.append(produto_dict)
                    
                except Exception as e:
                    print(f"Erro ao processar produto Magazine Luiza: {e}")
                    continue
            
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"Erro na página {page} do Magazine Luiza: {e}")
            break
    
    return produtos

def scrape_casas_bahia(produto, max_pages=2):
    """Scraping das Casas Bahia"""
    produtos = []
    produto_formatado = quote_plus(produto)
    
    for page in range(1, max_pages + 1):
        try:
            url = f'https://www.casasbahia.com.br/{produto_formatado}?page={page}'
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            produto_items = soup.select('[data-testid="product-card"]')
            
            for item in produto_items:
                try:
                    nome_elem = item.select_one('h3, [data-testid="product-name"]')
                    nome = nome_elem.get_text().strip() if nome_elem else ""
                    
                    if not nome:
                        continue
                    
                    link_elem = item.select_one('a')
                    link = ""
                    if link_elem:
                        href = link_elem.get('href')
                        if href:
                            if href.startswith('/'):
                                link = f'https://www.casasbahia.com.br{href}'
                            else:
                                link = href
                    
                    preco_elem = item.select_one('[class*="price"]')
                    preco = "Preço não disponível"
                    if preco_elem:
                        preco_text = preco_elem.get_text().strip()
                        preco_match = re.search(r'[\d,]+\.?\d*', preco_text.replace('R$', '').replace(',', ''))
                        if preco_match:
                            preco = preco_match.group()
                    
                    img_elem = item.select_one('img')
                    imagem = ""
                    if img_elem:
                        imagem = img_elem.get('src') or img_elem.get('data-src', '')
                    
                    produto_dict = {
                        'nome': nome,
                        'link': link,
                        'link_afiliado': gerar_link_afiliado(link, 'casasbahia'),
                        'imagem': imagem,
                        'preco_atual': preco,
                        'preco_original': None,
                        'desconto': None,
                        'tem_promocao': False,
                        'rating': "",
                        'reviews': "",
                        'vendas': "",
                        'frete_gratis': 'frete grátis' in item.get_text().lower(),
                        'comissao_pct': "3.0", # Comissão média das Casas Bahia
                        'plataforma': 'Casas Bahia'
                    }
                    
                    produtos.append(produto_dict)
                    
                except Exception as e:
                    print(f"Erro ao processar produto Casas Bahia: {e}")
                    continue
            
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"Erro na página {page} das Casas Bahia: {e}")
            break
    
    return produtos

def scrape_submarino(produto, max_pages=2):
    """Scraping do Submarino"""
    produtos = []
    produto_formatado = quote_plus(produto)
    
    for page in range(1, max_pages + 1):
        try:
            url = f'https://www.submarino.com.br/busca/{produto_formatado}?page={page}'
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            if response.status_code != 200:
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            produto_items = soup.select('[data-testid="product-card"]')
            
            for item in produto_items:
                try:
                    nome_elem = item.select_one('h3, [data-testid="product-name"]')
                    nome = nome_elem.get_text().strip() if nome_elem else ""
                    
                    if not nome:
                        continue
                    
                    link_elem = item.select_one('a')
                    link = ""
                    if link_elem:
                        href = link_elem.get('href')
                        if href:
                            if href.startswith('/'):
                                link = f'https://www.submarino.com.br{href}'
                            else:
                                link = href
                    
                    preco_elem = item.select_one('[class*="price"]')
                    preco = "Preço não disponível"
                    if preco_elem:
                        preco_text = preco_elem.get_text().strip()
                        preco_match = re.search(r'[\d,]+\.?\d*', preco_text.replace('R$', '').replace(',', ''))
                        if preco_match:
                            preco = preco_match.group()
                    
                    img_elem = item.select_one('img')
                    imagem = ""
                    if img_elem:
                        imagem = img_elem.get('src') or img_elem.get('data-src', '')
                    
                    produto_dict = {
                        'nome': nome,
                        'link': link,
                        'link_afiliado': gerar_link_afiliado(link, 'submarino'),
                        'imagem': imagem,
                        'preco_atual': preco,
                        'preco_original': None,
                        'desconto': None,
                        'tem_promocao': False,
                        'rating': "",
                        'reviews': "",
                        'vendas': "",
                        'frete_gratis': 'frete grátis' in item.get_text().lower(),
                        'comissao_pct': "4.5", # Comissão média do Submarino
                        'plataforma': 'Submarino'
                    }
                    
                    produtos.append(produto_dict)
                    
                except Exception as e:
                    print(f"Erro ao processar produto Submarino: {e}")
                    continue
            
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"Erro na página {page} do Submarino: {e}")
            break
    
    return produtos

def filtrar_por_preco(produtos, preco_min="", preco_max=""):
    """Filtra produtos por faixa de preço"""
    if not preco_min and not preco_max:
        return produtos
    
    produtos_filtrados = []
    
    for produto in produtos:
        if produto['preco_atual'] == 'Preço não disponível':
            continue
            
        try:
            preco = float(produto['preco_atual'].replace(',', '.'))
            
            if preco_min and preco < float(preco_min):
                continue
                
            if preco_max and preco > float(preco_max):
                continue
                
            produtos_filtrados.append(produto)
            
        except (ValueError, TypeError):
            continue
    
    return produtos_filtrados

def ordenar_produtos(produtos, ordenacao):
    """Ordena produtos conforme critério especificado"""
    if ordenacao == 'menor_preco':
        return sorted(produtos, key=lambda p: float(p['preco_atual'].replace(',', '.')) 
                     if p['preco_atual'] != 'Preço não disponível' else float('inf'))
    
    elif ordenacao == 'maior_desconto':
        return sorted(produtos, key=lambda p: p['desconto'] or 0, reverse=True)
    
    elif ordenacao == 'mais_vendidos':
        return sorted(produtos, key=lambda p: int(p['vendas'] or 0), reverse=True)
    
    # Default: relevância (mantém ordem original)
    return produtos

def scrape_afiliados(produto, max_pages=2, plataforma="todas", ordenacao="relevancia", preco_min="", preco_max=""):
    """Função principal para scraping de múltiplas plataformas de afiliados"""
    print(f"Iniciando scraping de afiliados para: {produto}")
    
    all_produtos = []
    
    # Definir quais plataformas usar
    plataformas_ativas = {
        'shopee': scrape_shopee,
        'magazine': scrape_magazine_luiza, 
        'casasbahia': scrape_casas_bahia,
        'submarino': scrape_submarino
    }
    
    if plataforma != "todas" and plataforma in plataformas_ativas:
        plataformas_ativas = {plataforma: plataformas_ativas[plataforma]}
    
    # Executar scraping em paralelo para melhor performance
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_plataforma = {
            executor.submit(func, produto, max_pages): nome 
            for nome, func in plataformas_ativas.items()
        }
        
        for future in concurrent.futures.as_completed(future_to_plataforma):
            plataforma_nome = future_to_plataforma[future]
            try:
                produtos = future.result()
                print(f"✅ {plataforma_nome}: {len(produtos)} produtos encontrados")
                
                with results_lock:
                    all_produtos.extend(produtos)
                    
            except Exception as e:
                print(f"❌ Erro no scraping da {plataforma_nome}: {e}")
    
    print(f"Total de produtos antes dos filtros: {len(all_produtos)}")
    
    # Aplicar filtros
    if preco_min or preco_max:
        all_produtos = filtrar_por_preco(all_produtos, preco_min, preco_max)
        print(f"Após filtro de preço: {len(all_produtos)} produtos")
    
    # Ordenar produtos
    all_produtos = ordenar_produtos(all_produtos, ordenacao)
    
    # Limitar resultados para evitar sobrecarga
    max_resultados = 50
    if len(all_produtos) > max_resultados:
        all_produtos = all_produtos[:max_resultados]
        print(f"Limitado a {max_resultados} produtos para melhor performance")
    
    print(f"✅ Scraping finalizado: {len(all_produtos)} produtos retornados")
    return all_produtos