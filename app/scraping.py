# /mercado_livre_scraper/app/scraping.py

import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import re

load_dotenv()
USER_AGENT = os.getenv("USER_AGENT")
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = os.getenv("PROXY_PORT")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

headers = {'User-Agent': USER_AGENT}

proxies = {}
if PROXY_HOST and PROXY_PORT and PROXY_USERNAME and PROXY_PASSWORD:
    proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
    proxies = {'http': proxy_url, 'https': proxy_url}

def parse_price(price_str):
    """Converte uma string de preço (ex: 'R$ 1.234,56') para um float."""
    if not price_str:
        return 0.0
    try:
        cleaned_price = re.sub(r'[^\d,.]', '', str(price_str))
        if ',' in cleaned_price and '.' in cleaned_price:
             cleaned_price = cleaned_price.replace('.', '').replace(',', '.')
        else:
             cleaned_price = cleaned_price.replace(',', '.')
        return float(cleaned_price)
    except (ValueError, TypeError):
        return 0.0

def scrape_produto_especifico(url):
    """Realiza o scraping de uma página de produto específica do Mercado Livre com lógica aprimorada."""
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        r.raise_for_status()
        
        site = BeautifulSoup(r.content, 'html.parser')
        
        produto_info = {'link': url}

        # --- Título ---
        titulo_elem = site.select_one('h1.ui-pdp-title')
        produto_info['titulo'] = titulo_elem.get_text(strip=True) if titulo_elem else 'Título não encontrado'

        # --- IMAGEM (LÓGICA CORRIGIDA COM FALLBACKS) ---
        produto_info['imagem'] = ''
        image_selectors = [
            '.ui-pdp-gallery__figure img',              # Seletor principal para a imagem da galeria
            '[data-testid="gallery-main-picture"] img', # Seletor baseado em atributo de teste
            '.ui-pdp-image.ui-pdp-gallery__figure__image' # Outro padrão comum
        ]
        for selector in image_selectors:
            img_elem = site.select_one(selector)
            if img_elem and img_elem.get('src'):
                src = img_elem['src'].replace('-I.jpg', '-O.jpg').replace('-I.webp', '-O.webp')
                produto_info['imagem'] = src
                break # Para o loop assim que encontrar a primeira imagem válida

        # --- Lógica de Preço Aprimorada com Múltiplos Seletores ---
        preco_atual_str = "Preço não disponível"
        preco_original_str = None
        desconto_val = None
        
        # 1. Tentar meta tag primeiro (mais preciso)
        meta_price_elem = site.find('meta', itemprop='price')
        if meta_price_elem and meta_price_elem.has_attr('content'):
            try:
                price_float = float(meta_price_elem['content'])
                preco_atual_str = f"R$ {price_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except:
                pass
        
        # 2. Se não conseguiu pelo meta, tentar outros seletores
        if preco_atual_str == "Preço não disponível":
            price_selectors = [
                '.ui-pdp-price__main-container .andes-money-amount__fraction',
                '.price-tag-amount .andes-money-amount__fraction',
                '.ui-pdp-price__fraction',
                'meta[itemprop="price"]',
                '.price-tag .andes-money-amount__fraction'
            ]
            
            for selector in price_selectors:
                price_elem = site.select_one(selector)
                if price_elem:
                    if selector == 'meta[itemprop="price"]':
                        try:
                            price_float = float(price_elem.get('content', '0'))
                            preco_atual_str = f"R$ {price_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                            break
                        except:
                            continue
                    else:
                        # Para elementos de texto, buscar centavos também
                        centavos_selectors = [
                            '.ui-pdp-price__main-container .andes-money-amount__cents',
                            '.price-tag-amount .andes-money-amount__cents',
                            '.ui-pdp-price__cents'
                        ]
                        
                        centavos_elem = None
                        for cent_selector in centavos_selectors:
                            centavos_elem = site.select_one(cent_selector)
                            if centavos_elem:
                                break
                        
                        centavos = f",{centavos_elem.get_text(strip=True)}" if centavos_elem else ""
                        preco_atual_str = f"R$ {price_elem.get_text(strip=True)}{centavos}"
                        break

        # 3. Múltiplos seletores para preço original
        original_price_selectors = [
            's .andes-money-amount__fraction',  # Preço riscado
            '.ui-pdp-price__original-value .andes-money-amount__fraction',
            '.price-tag-original .andes-money-amount__fraction',
            'span.andes-money-amount--previous .andes-money-amount__fraction',
            '.ui-pdp-price__second-line .andes-money-amount__fraction'
        ]
        
        for selector in original_price_selectors:
            original_price_elem = site.select_one(selector)
            if original_price_elem:
                preco_original_str = f"R$ {original_price_elem.get_text(strip=True)}"
                break
        
        # 4. Procurar por indicadores de desconto direto
        discount_selectors = [
            '.ui-pdp-price__discount',
            '.ui-pdp-media__discount',
            '.discount-tag',
            'span[class*="discount"]',
            'span[class*="off"]',
            '.ui-pdp-promotions__discount'
        ]
        
        for selector in discount_selectors:
            discount_elem = site.select_one(selector)
            if discount_elem:
                discount_text = discount_elem.get_text(strip=True)
                match = re.search(r'(\d+)%?\s*(?:OFF|off|OFF!)', discount_text, re.IGNORECASE)
                if not match:
                    match = re.search(r'(\d+)%', discount_text)
                if match:
                    desconto_val = int(match.group(1))
                    break

        # 5. Se temos preços mas não desconto, calcular
        if not desconto_val and preco_original_str and preco_atual_str != "Preço não disponível":
            try:
                preco_atual_float = parse_price(preco_atual_str)
                preco_original_float = parse_price(preco_original_str)
                if preco_original_float > preco_atual_float > 0:
                    desconto_val = int(((preco_original_float - preco_atual_float) / preco_original_float) * 100)
            except:
                pass

        produto_info['preco_atual'] = preco_atual_str
        produto_info['preco_original'] = preco_original_str
        produto_info['desconto'] = desconto_val
        produto_info['tem_promocao'] = bool(preco_original_str and desconto_val)

        # --- Outros Detalhes ---
        condicao_elem = site.select_one('.ui-pdp-header__subtitle .ui-pdp-subtitle')
        produto_info['condicao'] = condicao_elem.get_text(strip=True) if condicao_elem else ''

        vendedor_elem = site.select_one('.ui-pdp-seller__header__title')
        produto_info['vendedor'] = vendedor_elem.get_text(strip=True) if vendedor_elem else ''
        
        desc_elem = site.select_one('.ui-pdp-description__content p')
        produto_info['descricao'] = desc_elem.get_text(strip=True) if desc_elem else ''

        produto_info.update({'disponivel': True, 'cupons': []})

        return produto_info

    except requests.RequestException as e:
        print(f"Erro de requisição ao buscar produto específico: {e}")
        return None
    except Exception as e:
        print(f"Erro ao processar página de produto específico: {e}")
        return None


def extrair_imagem_produto(produto_elem):
    try:
        img_selectors = ['img.ui-search-result-image__element', 'img[data-src]', 'img.ui-search-item__image', '.ui-search-result-image__element']
        for selector in img_selectors:
            img_elem = produto_elem.select_one(selector)
            if img_elem:
                src = img_elem.get('data-src') or img_elem.get('src')
                if src and 'http' in src: return src.split('?')[0]
    except Exception: pass
    return ""

def extrair_precos(produto_elem):
    precos_info = {'preco_atual': 'Preço não disponível', 'preco_original': None, 'desconto': None, 'tem_promocao': False}
    try:
        # Múltiplos seletores para preço atual
        preco_atual_selectors = [
            '.andes-money-amount__fraction',
            '.ui-search-price__part .andes-money-amount__fraction',
            '.price-tag-amount .andes-money-amount__fraction',
            '.price-tag .andes-money-amount__fraction'
        ]
        
        preco_atual_elem = None
        for selector in preco_atual_selectors:
            preco_atual_elem = produto_elem.select_one(selector)
            if preco_atual_elem:
                break
        
        if preco_atual_elem:
            preco_atual_str = preco_atual_elem.get_text().strip()
            
            # Buscar centavos em múltiplos possíveis locais
            centavos_selectors = [
                '.andes-money-amount__cents',
                '.price-tag-amount .andes-money-amount__cents',
                '.ui-search-price__part .andes-money-amount__cents'
            ]
            
            centavos_elem = None
            for selector in centavos_selectors:
                centavos_elem = produto_elem.select_one(selector)
                if centavos_elem:
                    break
            
            centavos_str = f",{centavos_elem.get_text().strip()}" if centavos_elem else ""
            precos_info['preco_atual'] = f"R$ {preco_atual_str}{centavos_str}"
        
        # Múltiplos seletores para preço original (riscado)
        preco_original_selectors = [
            '.ui-search-price__original-value .andes-money-amount__fraction',
            '.ui-search-price__second-line .andes-money-amount__fraction',
            '.price-tag-original .andes-money-amount__fraction',
            'span.andes-money-amount--previous .andes-money-amount__fraction',
            '.ui-search-item__price-second-line .andes-money-amount__fraction'
        ]
        
        preco_original_elem = None
        for selector in preco_original_selectors:
            preco_original_elem = produto_elem.select_one(selector)
            if preco_original_elem:
                break
        
        if preco_original_elem:
            precos_info['preco_original'] = f"R$ {preco_original_elem.get_text().strip()}"
            precos_info['tem_promocao'] = True
        
        # Múltiplos seletores para desconto
        desconto_selectors = [
            '.ui-search-price__discount',
            '.ui-search-item__group__element--tag',
            '.ui-search-item__tag',
            '.price-tag-discount',
            'span[class*="discount"]',
            'span[class*="off"]'
        ]
        
        desconto_elem = None
        for selector in desconto_selectors:
            desconto_elem = produto_elem.select_one(selector)
            if desconto_elem:
                desconto_text = desconto_elem.get_text().strip()
                # Procurar por padrões de desconto
                match = re.search(r'(\d+)%?\s*(?:OFF|off|OFF!)', desconto_text, re.IGNORECASE)
                if not match:
                    match = re.search(r'(\d+)%', desconto_text)
                if match:
                    precos_info['desconto'] = int(match.group(1))
                    precos_info['tem_promocao'] = True
                    break
        
        # Se temos preço atual e original mas não desconto, calcular
        if precos_info['preco_atual'] != 'Preço não disponível' and precos_info['preco_original'] and not precos_info['desconto']:
            try:
                atual = parse_price(precos_info['preco_atual'])
                original = parse_price(precos_info['preco_original'])
                if original > atual > 0:
                    desconto_calculado = int(((original - atual) / original) * 100)
                    if desconto_calculado > 0:
                        precos_info['desconto'] = desconto_calculado
                        precos_info['tem_promocao'] = True
            except:
                pass
                
    except Exception as e:
        print(f"DEBUG PRECOS (Busca): Erro ao extrair preços: {e}")
    
    return precos_info

def scrape_mercadolivre(produto, max_pages=3):
    produto_formatado = produto.replace(' ', '-')
    resultados = []
    for page in range(1, max_pages + 1):
        try:
            url_final = f'https://lista.mercadolivre.com.br/{produto_formatado}_Desde_{(page - 1) * 50 + 1}' if page > 1 else f'https://lista.mercadolivre.com.br/{produto_formatado}'
            r = requests.get(url_final, headers=headers, proxies=proxies, timeout=20)
            if r.status_code != 200: break
            site = BeautifulSoup(r.content, 'html.parser')
            produtos_encontrados = site.select('li.ui-search-layout__item')
            if not produtos_encontrados: break
            for produto_elem in produtos_encontrados:
                try:
                    titulo_elem = produto_elem.select_one('h2.ui-search-item__title')
                    link_elem = produto_elem.select_one('a.ui-search-link')
                    if not titulo_elem or not link_elem: continue
                    titulo = titulo_elem.get_text().strip()
                    link = link_elem.get('href')
                    precos_info = extrair_precos(produto_elem)
                    imagem_url = extrair_imagem_produto(produto_elem)
                    if titulo and link:
                        resultados.append({'titulo': titulo, **precos_info, 'imagem': imagem_url, 'link': link})
                except Exception: continue
            time.sleep(2)
        except Exception as e:
            print(f"Erro ao processar página de busca do Mercado Livre: {e}")
            break
    return resultados

def busca_alternativa(produto):
    return []