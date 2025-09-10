# /app/selectors.py
"""
Sistema de seletores adaptativos para mudanças de layout
"""
import logging
from typing import Dict, List
from .config import ScrapingConfig

logger = logging.getLogger(__name__)

class AdaptiveSelector:
    """Sistema de seletores adaptativos para mudanças de layout"""

    def __init__(self, platform: str):
        self.platform = platform
        self.config = ScrapingConfig.get_platform_config(platform)
        self.fallback_selectors = self._get_fallback_selectors()

    def _get_fallback_selectors(self) -> Dict[str, List[str]]:
        """Retorna seletores alternativos para cada elemento"""
        fallbacks = {
            'mercadolivre': {
                'product_items': [
                    'li.ui-search-layout__item',
                    'li[data-testid="product-card"]',
                    '.ui-search-item',
                    '.item'
                ],
                'title': [
                    'h2.ui-search-item__title',
                    'h2[data-testid="product-title"]',
                    '.ui-search-item__title',
                    'h2',
                    '.title'
                ],
                'link': [
                    'a.ui-search-link',
                    'a[data-testid="product-link"]',
                    'a',
                    '.link'
                ],
                'price_current': [
                    '.andes-money-amount__fraction',
                    '[data-testid="price-value"]',
                    '.price-current',
                    '.price'
                ],
                'image': [
                    'img.ui-search-result-image__element',
                    'img[data-src]',
                    'img[src]',
                    'img'
                ]
            },
            'amazon': {
                'product_items': [
                    '[data-component-type="s-search-result"]',
                    '.s-result-item',
                    '.search-result'
                ],
                'title': [
                    'h2 .a-text-normal',
                    'h2 a span',
                    '.a-size-medium',
                    'h2'
                ],
                'link': [
                    'h2 a',
                    'a[href*="/dp/"]',
                    'a'
                ],
                'price_current': [
                    '.a-price .a-offscreen',
                    '.a-price-range .a-offscreen',
                    '.a-price'
                ],
                'image': [
                    'img.s-image',
                    'img[data-src]',
                    'img'
                ]
            }
        }
        
        return fallbacks.get(self.platform, {})
    
    def find_element(self, soup, element_type: str, required: bool = True):
        """Encontra elemento usando seletores adaptativos"""
        if not self.config:
            return None
        
        selectors = [self.config['selectors'].get(element_type, '')]
        selectors.extend(self.fallback_selectors.get(element_type, []))
        
        for selector in selectors:
            if not selector:
                continue
                
            try:
                element = soup.select_one(selector)
                if element:
                    return element
            except Exception as e:
                logger.warning(f"Erro ao usar seletor {selector}: {e}")
                continue
        
        if required:
            logger.error(f"Elemento {element_type} não encontrado com nenhum seletor")
        
        return None
    
    def find_elements(self, soup, element_type: str) -> List:
        """Encontra múltiplos elementos usando seletores adaptativos"""
        if not self.config:
            return []
        
        selectors = [self.config['selectors'].get(element_type, '')]
        selectors.extend(self.fallback_selectors.get(element_type, []))
        
        for selector in selectors:
            if not selector:
                continue
                
            try:
                elements = soup.select(selector)
                if elements:
                    return elements
            except Exception as e:
                logger.warning(f"Erro ao usar seletor {selector}: {e}")
                continue
        
        return []