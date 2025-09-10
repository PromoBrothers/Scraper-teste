# /Promo-Brothers-Scraper/app/amazon_scraping.py

import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import re
import random
import json
from urllib.parse import quote_plus

load_dotenv()
USER_AGENT = os.getenv("USER_AGENT")
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = os.getenv("PROXY_PORT")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")
USE_PROXY = os.getenv("USE_PROXY", "true").lower() == "true"

headers = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

proxies = {}
if USE_PROXY and PROXY_HOST and PROXY_PORT and PROXY_USERNAME and PROXY_PASSWORD:
    proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
    proxies = {'http': proxy_url, 'https': proxy_url}
    print("Proxy ativado para scraping da Amazon.")
else:
    print("Proxy da Amazon desativado.")

# ... (O restante do arquivo amazon_scraping.py permanece o mesmo)
def parse_price_amazon(price_str):
    """
    Converter preço da Amazon para float para cálculos matemáticos
    """
    if not price_str:
        return 0.0
    try:
        # Limpar e extrair apenas números e vírgula
        cleaned = re.sub(r'[^\d,]', '', str(price_str))
        # Tratar casos de dupla vírgula
        cleaned = re.sub(r',{2,}', ',', cleaned)
        # Converter vírgula para ponto para float
        return float(cleaned.replace(',', '.'))
    except (ValueError, TypeError):
        return 0.0

def format_amazon_price(symbol, whole, fraction):
    """
    Formatar preço da Amazon corrigindo problemas de dupla vírgula e formatação
    """
    if not symbol or not whole:
        return 'Preço não disponível'
    
    # Limpar e normalizar symbol
    symbol = symbol.strip()
    if not symbol.startswith('R$'):
        symbol = 'R$'
    
    # Limpar whole (parte inteira)
    whole = str(whole).strip().replace(',', '').replace('.', '')
    if not whole.isdigit():
        # Extrair apenas números
        whole = re.sub(r'\D', '', whole)
    
    if not whole:
        return 'Preço não disponível'
    
    # Processar fraction (centavos)
    if fraction:
        fraction = str(fraction).strip().replace(',', '').replace('.', '')
        # Extrair apenas números dos centavos
        fraction = re.sub(r'\D', '', fraction)
        
        # Garantir que tenha exatamente 2 dígitos
        if len(fraction) == 1:
            fraction = fraction + '0'  # 5 -> 50
        elif len(fraction) > 2:
            fraction = fraction[:2]  # 500 -> 50
        elif len(fraction) == 0:
            fraction = '00'
    else:
        fraction = '00'
    
    return f"{symbol}{whole},{fraction}"

def sanitize_amazon_price(price_str):
    """
    Sanitizar preços da Amazon que podem ter formatação problemática
    """
    if not price_str or price_str == 'Preço não disponível':
        return price_str
    
    # Corrigir duplas vírgulas e problemas comuns
    price_str = str(price_str).strip()
    
    # Remover duplas vírgulas
    price_str = re.sub(r',{2,}', ',', price_str)
    
    # Padrão para preço brasileiro: R$123,45
    match = re.search(r'(R\$?\s*)(\d{1,3}(?:\.\d{3})*),(\d{1,2})', price_str)
    if match:
        symbol = match.group(1).strip()
        if not symbol.startswith('R$'):
            symbol = 'R$'
        whole = match.group(2).replace('.', '')  # Remove separadores de milhares
        fraction = match.group(3)
        
        # Garantir que fraction tenha 2 dígitos
        if len(fraction) == 1:
            fraction = fraction + '0'
        
        return f"{symbol}{whole},{fraction}"
    
    # Se não conseguiu fazer o parse, tentar extrair números básicos
    numbers = re.findall(r'\d+', price_str)
    if len(numbers) >= 2:
        whole = numbers[0]
        fraction = numbers[1][:2]  # Máximo 2 dígitos para centavos
        if len(fraction) == 1:
            fraction = fraction + '0'
        return f"R${whole},{fraction}"
    elif len(numbers) == 1:
        return f"R${numbers[0]},00"
    
    return price_str
def extrair_imagem_amazon(produto_elem):
    try:
        img_elem = produto_elem.select_one('img.s-image')
        if img_elem:
            src = img_elem.get('src')
            if src and 'http' in src:
                return re.sub(r'_AC_.*?.jpg', '_AC_SL1500_.jpg', src)
    except Exception:
        pass
    return ""
def extrair_preco_amazon(produto_elem):
    preco_info = {'preco_atual': 'Preço não disponível', 'preco_original': None, 'desconto': None, 'tem_promocao': False}
    try:
        # Múltiplos seletores para preço atual
        preco_atual_selectors = [
            '.a-price .a-offscreen',
            '.a-price-current .a-offscreen',
            '.a-price-whole',
            'span.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price-symbol + .a-price-whole'
        ]
        
        preco_atual_elem = None
        for selector in preco_atual_selectors:
            preco_atual_elem = produto_elem.select_one(selector)
            if preco_atual_elem:
                preco_info['preco_atual'] = sanitize_amazon_price(preco_atual_elem.get_text().strip())
                break
        
        # Se ainda não encontrou o preço atual, tentar construir
        if not preco_atual_elem or preco_info['preco_atual'] == 'Preço não disponível':
            symbol_elem = produto_elem.select_one('.a-price-symbol')
            whole_elem = produto_elem.select_one('.a-price-whole')
            fraction_elem = produto_elem.select_one('.a-price-fraction')
            
            if symbol_elem and whole_elem:
                symbol = symbol_elem.get_text().strip()
                whole = whole_elem.get_text().strip()
                fraction = fraction_elem.get_text().strip() if fraction_elem else None
                
                preco_info['preco_atual'] = format_amazon_price(symbol, whole, fraction)
        
        # Múltiplos seletores para preço original (riscado)
        preco_original_selectors = [
            '.a-text-price .a-offscreen',
            '.a-price.a-text-price .a-offscreen',
            'span.a-price.a-text-price .a-offscreen',
            '.a-price-was .a-offscreen',
            '.a-price-strike .a-offscreen',
            'span[data-a-strike="true"] .a-offscreen'
        ]
        
        preco_original_elem = None
        for selector in preco_original_selectors:
            preco_original_elem = produto_elem.select_one(selector)
            if preco_original_elem:
                preco_info['preco_original'] = sanitize_amazon_price(preco_original_elem.get_text().strip())
                preco_info['tem_promocao'] = True
                break
        
        # Procurar por indicadores diretos de desconto
        discount_selectors = [
            '.a-badge-label',
            'span[aria-label*="%"]',
            '.a-size-mini.a-color-price',
            'span.a-letter-space'
        ]
        
        for selector in discount_selectors:
            discount_elem = produto_elem.select_one(selector)
            if discount_elem:
                discount_text = discount_elem.get_text().strip()
                match = re.search(r'(\d+)%\s*(?:OFF|off|desconto)', discount_text, re.IGNORECASE)
                if not match:
                    match = re.search(r'(\d+)%', discount_text)
                if match:
                    preco_info['desconto'] = int(match.group(1))
                    preco_info['tem_promocao'] = True
                    break
        
        # Se temos preços mas não desconto, calcular
        if not preco_info['desconto'] and preco_info['preco_original'] and preco_info['preco_atual'] != 'Preço não disponível':
            try:
                atual = parse_price_amazon(preco_info['preco_atual'])
                original = parse_price_amazon(preco_info['preco_original'])
                if original > atual > 0:
                    desconto_pct = int(((original - atual) / original) * 100)
                    if desconto_pct > 0:
                        preco_info['desconto'] = desconto_pct
                        preco_info['tem_promocao'] = True
            except:
                pass
                
    except Exception as e:
        print(f"DEBUG PRECOS (Busca Amazon): Erro ao extrair preços: {e}")
    return preco_info
def extrair_rating_amazon(produto_elem):
    rating, reviews = "", ""
    try:
        rating_elem = produto_elem.select_one('.a-icon-alt')
        if rating_elem:
            rating_text = rating_elem.get_text()
            match = re.search(r'(\d[,.]\d)', rating_text)
            if match:
                rating = match.group(1).replace(',', '.')
        reviews_elem = produto_elem.select_one('.a-size-base')
        if reviews_elem and re.match(r'^\(?\d{1,3}(?:\.\d{3})*\)?$', reviews_elem.get_text().strip()):
             reviews = reviews_elem.get_text().strip()
    except Exception:
        pass
    return rating, reviews
def gerar_link_afiliado_amazon(url, affiliate_tag=None):
    amazon_tag = affiliate_tag or os.getenv("AMAZON_ASSOCIATES_TAG", "promobrothers-20")
    if not url or "amzn.to/" in url:
        return url
    if "amazon.com" in url and amazon_tag and amazon_tag != "SEU_TAG_AQUI-20":
        base_url = url.split('?')[0]
        base_url = re.sub(r'/ref=.*', '', base_url)
        return f"{base_url}?tag={amazon_tag}&linkCode=osi"
    return url
def scrape_produto_amazon_especifico(url, afiliado_link=None):
    try:
        print(f"Fazendo scraping do produto Amazon: {url}")
        response = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        produto = {'link': url}
        produto['nome'] = soup.select_one('#productTitle').get_text().strip()
        img_tag = soup.select_one('#landingImage')
        if img_tag and img_tag.has_attr('data-a-dynamic-image'):
            img_json = json.loads(img_tag['data-a-dynamic-image'])
            produto['imagem'] = list(img_json.keys())[0]
        else:
            produto['imagem'] = ''
        # Múltiplos seletores para preço atual na página do produto
        preco_atual_selectors = [
            '.a-price .a-offscreen',
            '.a-price-current .a-offscreen',  
            'span.a-price.apexPriceToPay .a-offscreen',
            '#apex_desktop .a-price .a-offscreen',
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen'
        ]
        
        produto['preco_atual'] = 'Preço não disponível'
        for selector in preco_atual_selectors:
            preco_atual_elem = soup.select_one(selector)
            if preco_atual_elem:
                produto['preco_atual'] = sanitize_amazon_price(preco_atual_elem.get_text().strip())
                break
        
        # Múltiplos seletores para preço original
        preco_original_selectors = [
            '.a-text-price .a-offscreen',
            '.a-price.a-text-price .a-offscreen',
            'span.a-price.a-text-price .a-offscreen',
            '.a-price-was .a-offscreen',
            '.basisPrice .a-offscreen',
            'span[data-a-strike="true"] .a-offscreen'
        ]
        
        produto['preco_original'] = None
        for selector in preco_original_selectors:
            preco_original_elem = soup.select_one(selector)
            if preco_original_elem:
                produto['preco_original'] = sanitize_amazon_price(preco_original_elem.get_text().strip())
                break
        
        # Procurar desconto direto na página do produto
        desconto = None
        discount_selectors = [
            '.savingPriceOverride',
            '.a-badge-label',
            'span[aria-label*="%"]',
            '.a-size-large.a-color-price'
        ]
        
        for selector in discount_selectors:
            discount_elem = soup.select_one(selector)
            if discount_elem:
                discount_text = discount_elem.get_text().strip()
                match = re.search(r'(\d+)%', discount_text)
                if match:
                    desconto = int(match.group(1))
                    break
        
        # Se não encontrou desconto direto mas tem preços, calcular
        if not desconto and produto['preco_original'] and produto['preco_atual'] != 'Preço não disponível':
            try:
                atual = parse_price_amazon(produto['preco_atual'])
                original = parse_price_amazon(produto['preco_original'])
                if original > atual > 0:
                    desconto = int(((original - atual) / original) * 100)
            except:
                pass
        
        produto['desconto'] = desconto
        produto['tem_promocao'] = bool(produto['preco_original'] and desconto)
        produto['rating'], produto['reviews'] = extrair_rating_amazon(soup)
        produto['fonte'] = 'Amazon'
        produto['comissao_pct'] = "8.0"
        produto['link_afiliado'] = afiliado_link or gerar_link_afiliado_amazon(url)
        print(f"Produto Amazon extraído com sucesso: {produto['nome'][:50]}...")
        return produto
    except requests.RequestException as e:
        print(f"Erro de requisição ao buscar produto Amazon: {e}")
        raise
    except Exception as e:
        print(f"Erro no scraping Amazon: {e}")
        raise
def scrape_amazon(produto, max_pages=2, categoria=""):
    produtos = []
    produto_formatado = quote_plus(produto)
    for page in range(1, max_pages + 1):
        try:
            url = f'https://www.amazon.com.br/s?k={produto_formatado}&page={page}'
            print(f"Fazendo scraping da página {page}: {url}")
            time.sleep(random.uniform(1.5, 3.5))
            response = requests.get(url, headers=headers, proxies=proxies, timeout=20)
            if response.status_code != 200:
                print(f"Status code: {response.status_code}, parando a busca na Amazon.")
                break
            soup = BeautifulSoup(response.content, 'html.parser')
            produtos_encontrados = soup.select('[data-component-type="s-search-result"]')
            if not produtos_encontrados:
                print("Nenhum produto encontrado nesta página da Amazon.")
                continue
            for item in produtos_encontrados:
                try:
                    nome_elem = item.select_one('h2 .a-text-normal')
                    if not nome_elem: continue
                    nome = nome_elem.get_text().strip()
                    link_elem = item.select_one('h2 a')
                    link = f"https://www.amazon.com.br{link_elem['href']}" if link_elem else ""
                    preco_info = extrair_preco_amazon(item)
                    imagem = extrair_imagem_amazon(item)
                    rating, reviews = extrair_rating_amazon(item)
                    produto_dict = {
                        'nome': nome, 'link': link, 'link_afiliado': gerar_link_afiliado_amazon(link),
                        'imagem': imagem, 'comissao_pct': "8.0", 'fonte': 'Amazon',
                        'rating': rating, 'reviews': reviews, **preco_info
                    }
                    produtos.append(produto_dict)
                    print(f"Produto Amazon adicionado: {nome[:50]}...")
                except Exception as e:
                    print(f"Erro ao processar produto da Amazon: {e}")
                    continue
        except requests.RequestException as e:
            print(f"Erro na requisição da página {page} da Amazon: {e}")
            break
        except Exception as e:
            print(f"Erro geral na página {page} da Amazon: {e}")
            continue
    print(f"Scraping da Amazon concluído. Total: {len(produtos)} produtos.")
    return produtos