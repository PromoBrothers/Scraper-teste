import logging
import time
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from .config import ScrapingConfig
from .anti_bot import AntiBotManager
from .selectors import AdaptiveSelector
from .validators import product_validator
from .cache_manager import cached_scraper
from . import amazon_scraping  # Para funções de sanitização de preços

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    def __init__(self, platform: str):
        self.platform = platform
        self.config = ScrapingConfig.get_platform_config(platform)
        self.anti_bot = AntiBotManager()
        self.selector = AdaptiveSelector(platform)

    @abstractmethod
    def scrape_product(self, url: str, affiliate_link: str = "") -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def scrape_search(self, query: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        pass

    def _validate_and_sanitize(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        return product_validator.validate_product(product_data)

class MercadoLivreScraper(BaseScraper):
    def __init__(self):
        super().__init__('mercadolivre')

    @cached_scraper
    def scrape_product(self, url: str, affiliate_link: str = "") -> Optional[Dict[str, Any]]:
        try:
            response = self.anti_bot.make_request(url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            if not soup:
                logger.error("Página de produto não encontrada")
                return None
            product_data = self._extract_product_data(soup, url, affiliate_link)
            return self._validate_and_sanitize(product_data)
        except Exception as e:
            logger.error(f"Erro ao fazer scraping do produto ML: {e}")
            return None

    def scrape_search(self, query: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        products = []
        query_formatted = query.replace(' ', '-')
        for page in range(1, max_pages + 1):
            try:
                if page == 1:
                    url = f"{self.config['base_url']}/{query_formatted}"
                else:
                    offset = (page - 1) * self.config['pagination']['step']
                    url = f"{self.config['base_url']}/{query_formatted}_Desde_{offset + 1}"
                response = self.anti_bot.make_request(url)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                if not soup:
                    break
                product_items = self.selector.find_elements(soup, 'product_items')
                for item in product_items:
                    try:
                        product_data = self._extract_search_item_data(item)
                        if product_data:
                            validated_data = self._validate_and_sanitize(product_data)
                            products.append(validated_data)
                    except Exception as e:
                        logger.warning(f"Erro ao processar item da busca: {e}")
                        continue
                time.sleep(self.anti_bot.get_page_delay())
            except Exception as e:
                logger.error(f"Erro na página {page} da busca ML: {e}")
                break
        return products

    def _extract_product_data(self, soup, url: str, affiliate_link: str) -> Dict[str, Any]:
        title_elem = self.selector.find_element(soup, 'title')
        title = title_elem.get_text(strip=True) if title_elem else "Produto sem título"
        price_elem = self.selector.find_element(soup, 'price_current')
        price_cents_elem = self.selector.find_element(soup, 'price_cents')
        preco_atual = "Preço não disponível"
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            cents_text = f",{price_cents_elem.get_text(strip=True)}" if price_cents_elem else ""
            preco_atual = f"R$ {price_text}{cents_text}"
        original_price_elem = self.selector.find_element(soup, 'price_original')
        preco_original = None
        if original_price_elem:
            preco_original = f"R$ {original_price_elem.get_text(strip=True)}"
        img_elem = self.selector.find_element(soup, 'image')
        imagem = ""
        if img_elem:
            src = img_elem.get('src') or img_elem.get('data-src', '')
            if src:
                src = src.replace('-I.jpg', '-O.jpg').replace('-I.webp', '-O.webp')
                imagem = src
        return {
            'titulo': title,
            'link': url,
            'afiliado_link': affiliate_link or url,
            'preco_atual': preco_atual,
            'preco_original': preco_original,
            'imagem': imagem,
            'fonte': 'Mercado Livre',
            'plataforma': 'Mercado Livre'
        }

    def _extract_search_item_data(self, item) -> Dict[str, Any]:
        title_elem = self.selector.find_element(item, 'title')
        title = title_elem.get_text(strip=True) if title_elem else ""
        if not title:
            return None
        link_elem = self.selector.find_element(item, 'link')
        link = ""
        if link_elem:
            href = link_elem.get('href', '')
            if href.startswith('/'):
                link = f"https://mercadolivre.com.br{href}"
            else:
                link = href
        price_elem = self.selector.find_element(item, 'price_current')
        price_cents_elem = self.selector.find_element(item, 'price_cents')
        preco_atual = "Preço não disponível"
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            cents_text = f",{price_cents_elem.get_text(strip=True)}" if price_cents_elem else ""
            preco_atual = f"R$ {price_text}{cents_text}"
        original_price_elem = self.selector.find_element(item, 'price_original')
        preco_original = None
        if original_price_elem:
            preco_original = f"R$ {original_price_elem.get_text(strip=True)}"
        img_elem = self.selector.find_element(item, 'image')
        imagem = ""
        if img_elem:
            src = img_elem.get('src') or img_elem.get('data-src', '')
            if src:
                imagem = src.split('?')[0]
        return {
            'titulo': title,
            'link': link,
            'afiliado_link': link,
            'preco_atual': preco_atual,
            'preco_original': preco_original,
            'imagem': imagem,
            'fonte': 'Mercado Livre',
            'plataforma': 'Mercado Livre'
        }

class AmazonScraper(BaseScraper):
    def __init__(self):
        super().__init__('amazon')

    def scrape_product(self, url: str, affiliate_link: str = "") -> Optional[Dict[str, Any]]:
        try:
            response = self.anti_bot.make_request_via_api(url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            if not soup:
                logger.error("Página de produto não encontrada via API")
                return None
            product_data = self._extract_product_data(soup, url, affiliate_link)
            if (product_data.get('titulo') == 'Produto sem título' or
                product_data.get('preco_atual') == 'Preço não disponível'):
                logger.warning("Não foi possível extrair dados completos, mesmo com a API.")
                return self._create_fallback_product(url, affiliate_link)
            return self._validate_and_sanitize(product_data)
        except Exception as e:
            logger.error(f"Erro ao fazer scraping do produto Amazon via API: {e}")
            return self._create_fallback_product(url, affiliate_link)

    def _is_amazon_blocked(self, response, soup) -> bool:
        if response.status_code in [403, 429, 503, 500]:
            return True
        content_lower = response.text.lower()
        blocked_indicators = [
            'captcha', 'robot', 'bot detection', 'suspicious activity',
            'please verify', 'security check', 'unusual traffic',
            'access denied', 'blocked', 'error', 'not found'
        ]
        if any(indicator in content_lower for indicator in blocked_indicators):
            return True
        title_elem = soup.select_one('#productTitle')
        if not title_elem or not title_elem.get_text(strip=True):
            return True
        if len(response.text) < 5000:
            return True
        return False

    def _create_fallback_product(self, url: str, affiliate_link: str) -> Dict[str, Any]:
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        asin = asin_match.group(1) if asin_match else "UNKNOWN"
        product_data = {
            'titulo': f"Produto Amazon {asin}",
            'link': url,
            'afiliado_link': affiliate_link or self._generate_affiliate_link(url),
            'preco_atual': "Preço não disponível",
            'plataforma': 'Amazon',
            '_fallback': True,
            '_blocked': True
        }
        return self._validate_and_sanitize(product_data)

    def scrape_search(self, query: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        products = []
        query_encoded = query.replace(' ', '+')
        for page in range(1, max_pages + 1):
            try:
                url = f"{self.config['search_url']}?k={query_encoded}&page={page}"
                response = self.anti_bot.make_request(url)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                if not soup:
                    break
                product_items = self.selector.find_elements(soup, 'product_items')
                for item in product_items:
                    try:
                        product_data = self._extract_search_item_data(item)
                        if product_data:
                            validated_data = self._validate_and_sanitize(product_data)
                            products.append(validated_data)
                    except Exception as e:
                        logger.warning(f"Erro ao processar item da busca Amazon: {e}")
                        continue
                time.sleep(self.anti_bot.get_page_delay())
            except Exception as e:
                logger.error(f"Erro na página {page} da busca Amazon: {e}")
                break
        return products

    def _extract_product_data(self, soup, url: str, affiliate_link: str) -> Dict[str, Any]:
        title = "Produto sem título"
        title_selectors = ['#productTitle', 'h1.a-size-large', 'h1[data-automation-id="product-title"]', '.product-title', 'h1']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                if title_text and len(title_text) > 3:
                    title = title_text
                    break
        
        preco_atual = "Preço não disponível"
        preco_original = None

        price_container_selectors = ['#corePrice_desktop', '#corePrice_feature_div', '[data-feature-name="corePrice"]']
        price_container = None
        for selector in price_container_selectors:
            price_container = soup.select_one(selector)
            if price_container:
                break
        
        if price_container:
            price_whole_elem = price_container.select_one('.a-price-whole')
            price_fraction_elem = price_container.select_one('.a-price-fraction')
            if price_whole_elem and price_fraction_elem:
                whole = price_whole_elem.get_text(strip=True)
                fraction = price_fraction_elem.get_text(strip=True)
                preco_atual = amazon_scraping.format_amazon_price("R$", whole, fraction)
            
            original_price_elem = price_container.select_one('.basisPrice .a-offscreen, span[data-a-strike="true"] .a-offscreen')
            if original_price_elem:
                preco_original = amazon_scraping.sanitize_amazon_price(original_price_elem.get_text(strip=True))
        
        if preco_atual == "Preço não disponível":
            price_selectors = ['.a-price .a-offscreen', '.a-price-range .a-offscreen', '[data-a-price]']
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    if price_text:
                        preco_atual = amazon_scraping.sanitize_amazon_price(price_text)
                        break

        if not preco_original:
            original_price_selectors = [
                '.basisPrice .a-offscreen',
                'span[data-a-strike="true"] .a-offscreen',
                '#corePrice_desktop .a-text-price .a-offscreen',
            ]
            for selector in original_price_selectors:
                original_price_elem = soup.select_one(selector)
                if original_price_elem:
                    preco_original_text = amazon_scraping.sanitize_amazon_price(original_price_elem.get_text(strip=True))
                    if preco_original_text != preco_atual:
                        preco_original = preco_original_text
                        break

        if preco_original == preco_atual:
            preco_original = None

        imagem = ""
        image_selectors = ['#landingImage', '#imgTagWrapperId img', '.a-dynamic-image', '#main-image-container img', '.a-button-selected img']
        for selector in image_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                if img_elem.has_attr('data-a-dynamic-image'):
                    import json
                    try:
                        img_data = json.loads(img_elem['data-a-dynamic-image'])
                        imagem = list(img_data.keys())[0]
                        break
                    except:
                        pass
                src = img_elem.get('src') or img_elem.get('data-src')
                if src and 'http' in src:
                    imagem = src
                    break

        rating, reviews = "", ""
        return {
            'titulo': title, 'link': url, 'afiliado_link': affiliate_link or self._generate_affiliate_link(url),
            'preco_atual': preco_atual, 'preco_original': preco_original, 'imagem': imagem,
            'rating': rating, 'reviews': reviews, 'fonte': 'Amazon', 'plataforma': 'Amazon',
            'comissao_pct': '8.0'
        }

    def _extract_search_item_data(self, item) -> Dict[str, Any]:
        title_elem = item.select_one('h2 .a-text-normal')
        title = title_elem.get_text(strip=True) if title_elem else ""
        if not title: return None
        link_elem = item.select_one('h2 a')
        link = ""
        if link_elem:
            href = link_elem.get('href', '')
            link = f"https://www.amazon.com.br{href}" if href.startswith('/') else href
        price_elem = item.select_one('.a-price .a-offscreen')
        preco_atual = amazon_scraping.sanitize_amazon_price(price_elem.get_text(strip=True)) if price_elem else "Preço não disponível"
        original_price_elem = item.select_one('.a-text-price .a-offscreen')
        preco_original = amazon_scraping.sanitize_amazon_price(original_price_elem.get_text(strip=True)) if original_price_elem else None
        img_elem = item.select_one('img.s-image')
        imagem = ""
        if img_elem:
            src = img_elem.get('src', '')
            if src: imagem = re.sub(r'_AC_.*?.jpg', '_AC_SL1500_.jpg', src)
        rating, reviews = "", ""
        rating_elem = item.select_one('.a-icon-alt')
        if rating_elem:
            match = re.search(r'(\d[,.]\d)', rating_elem.get_text())
            if match: rating = match.group(1).replace(',', '.')
        reviews_elem = item.select_one('.a-size-base')
        reviews = reviews_elem.get_text(strip=True) if reviews_elem else ""
        return {
            'titulo': title, 'link': link, 'afiliado_link': self._generate_affiliate_link(link),
            'preco_atual': preco_atual, 'preco_original': preco_original, 'imagem': imagem,
            'rating': rating, 'reviews': reviews, 'fonte': 'Amazon', 'plataforma': 'Amazon',
            'comissao_pct': '8.0'
        }

    def _generate_affiliate_link(self, url: str) -> str:
        if not url or "amzn.to/" in url:
            return url
        affiliate_tag = ScrapingConfig.AFFILIATE_IDS.get('amazon', '')
        if affiliate_tag and "amazon.com" in url:
            base_url = url.split('?')[0]
            base_url = re.sub(r'/ref=.*', '', base_url)
            return f"{base_url}?tag={affiliate_tag}&linkCode=osi"
        return url
    
class ScraperFactory:
    _scrapers = {
        'mercadolivre': MercadoLivreScraper,
        'amazon': AmazonScraper,
    }

    @classmethod
    def create_scraper(cls, platform: str) -> Optional[BaseScraper]:
        platform = platform.lower()
        if platform in cls._scrapers:
            return cls._scrapers[platform]()
        logger.error(f"Scraper não encontrado para plataforma: {platform}")
        return None

    @classmethod
    def get_available_platforms(cls) -> List[str]:
        return list(cls._scrapers.keys())

    @classmethod
    def detect_platform_from_url(cls, url: str) -> Optional[str]:
        return ScrapingConfig.detect_platform(url)