# /app/validators.py
"""
Sistema de validação e sanitização de dados para web scraping
"""

import re
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, urljoin
from decimal import Decimal, InvalidOperation
import unicodedata

logger = logging.getLogger(__name__)

class DataValidator:
    """Validador de dados extraídos do scraping"""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Valida se a URL é válida"""
        if not url or not isinstance(url, str):
            return False
        
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    @staticmethod
    def validate_price(price_str: str) -> bool:
        """Valida se o preço está em formato válido"""
        if not price_str or not isinstance(price_str, str):
            return False
        
        # Remove caracteres não numéricos exceto vírgula e ponto
        cleaned = re.sub(r'[^\d,.]', '', price_str)
        
        if not cleaned:
            return False
        
        # Verifica se tem pelo menos um dígito
        return bool(re.search(r'\d', cleaned))
    
    @staticmethod
    def validate_title(title: str) -> bool:
        """Valida se o título é válido"""
        if not title or not isinstance(title, str):
            return False
        
        # Remove espaços extras
        cleaned = ' '.join(title.split())
        
        # Deve ter pelo menos 3 caracteres
        return len(cleaned) >= 3
    
    @staticmethod
    def validate_image_url(url: str) -> bool:
        """Valida se a URL da imagem é válida"""
        if not DataValidator.validate_url(url):
            return False
        
        # Verifica se é uma URL de imagem
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']
        url_lower = url.lower()
        
        return any(url_lower.endswith(ext) for ext in image_extensions) or 'image' in url_lower

class DataSanitizer:
    """Sanitizador de dados extraídos do scraping"""
    
    @staticmethod
    def sanitize_title(title: str) -> str:
        """Sanitiza título do produto"""
        if not title:
            return ""
        
        # Normalizar unicode
        title = unicodedata.normalize('NFKD', title)
        
        # Remover caracteres de controle
        title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
        
        # Remover tags HTML
        title = re.sub(r'<[^>]+>', '', title)
        
        # Remover espaços extras
        title = ' '.join(title.split())
        
        # Limitar tamanho
        return title[:200] if len(title) > 200 else title
    
    @staticmethod
    def sanitize_price(price_str: str) -> str:
        """Sanitiza preço do produto"""
        if not price_str:
            return "0,00"
        
        # Remove caracteres não numéricos exceto vírgula e ponto
        cleaned = re.sub(r'[^\d,.]', '', price_str)
        
        if not cleaned:
            return "0,00"
        
        # Normaliza formato brasileiro (vírgula para decimais)
        if ',' in cleaned and '.' in cleaned:
            # Formato: 1.234,56 -> 1234,56
            cleaned = cleaned.replace('.', '').replace(',', '.')
            cleaned = f"{float(cleaned):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif ',' in cleaned:
            # Formato: 1234,56 -> 1234,56
            cleaned = cleaned
        elif '.' in cleaned:
            # Formato: 1234.56 -> 1234,56
            cleaned = cleaned.replace('.', ',')
        
        return cleaned
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """Sanitiza URL do produto"""
        if not url:
            return ""
        
        # Remove espaços
        url = url.strip()
        
        # Adiciona protocolo se necessário
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Remove parâmetros desnecessários
        parsed = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        return clean_url
    
    @staticmethod
    def sanitize_image_url(url: str) -> str:
        """Sanitiza URL da imagem"""
        if not url:
            return ""
        
        # Remove espaços
        url = url.strip()
        
        # Converte URLs relativas para absolutas
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            # Precisa do domínio base - será tratado no scraper específico
            pass
        
        # Remove parâmetros de redimensionamento desnecessários
        url = re.sub(r'[?&]w=\d+', '', url)
        url = re.sub(r'[?&]h=\d+', '', url)
        url = re.sub(r'[?&]q=\d+', '', url)
        
        return url
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitiza texto geral"""
        if not text:
            return ""
        
        # Normalizar unicode
        text = unicodedata.normalize('NFKD', text)
        
        # Remover caracteres de controle
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Remover tags HTML
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remover espaços extras
        text = ' '.join(text.split())
        
        return text

class ProductDataValidator:
    """Validador específico para dados de produtos"""
    
    def __init__(self):
        self.validator = DataValidator()
        self.sanitizer = DataSanitizer()
    
    def validate_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida e sanitiza dados completos do produto"""
        validated_data = {}
        errors = []
        warnings = []
        
        # Validar e sanitizar título
        title = product_data.get('titulo') or product_data.get('nome') or product_data.get('title', '')
        if self.validator.validate_title(title):
            validated_data['titulo'] = self.sanitizer.sanitize_title(title)
        else:
            # Preservar dados de fallback se disponíveis
            if product_data.get('_fallback') or product_data.get('_blocked'):
                validated_data['titulo'] = title  # Manter título original do fallback
            else:
                errors.append("Título inválido ou ausente")
                validated_data['titulo'] = "Produto sem título"
        
        # Validar e sanitizar URL
        url = product_data.get('link') or product_data.get('url', '')
        if self.validator.validate_url(url):
            validated_data['link'] = self.sanitizer.sanitize_url(url)
        else:
            errors.append("URL inválida")
            validated_data['link'] = ""
        
        # Validar e sanitizar preço atual
        preco_atual = product_data.get('preco_atual') or product_data.get('price_current', '')
        if self.validator.validate_price(preco_atual):
            validated_data['preco_atual'] = self.sanitizer.sanitize_price(preco_atual)
        else:
            # Preservar dados de fallback se disponíveis
            if product_data.get('_fallback') or product_data.get('_blocked'):
                validated_data['preco_atual'] = preco_atual  # Manter preço original do fallback
            else:
                warnings.append("Preço atual inválido")
                validated_data['preco_atual'] = "Preço não disponível"
        
        # Validar e sanitizar preço original
        preco_original = product_data.get('preco_original') or product_data.get('price_original', '')
        if preco_original and self.validator.validate_price(preco_original):
            validated_data['preco_original'] = self.sanitizer.sanitize_price(preco_original)
        else:
            validated_data['preco_original'] = None
        
        # Validar e sanitizar URL da imagem
        imagem = product_data.get('imagem') or product_data.get('image', '')
        if imagem and self.validator.validate_image_url(imagem):
            validated_data['imagem'] = self.sanitizer.sanitize_image_url(imagem)
        else:
            warnings.append("URL da imagem inválida")
            validated_data['imagem'] = ""
        
        # Calcular desconto se possível
        desconto = self._calculate_discount(
            validated_data['preco_atual'],
            validated_data['preco_original']
        )
        validated_data['desconto'] = desconto
        validated_data['tem_promocao'] = desconto is not None and desconto > 0
        
        # Outros campos
        validated_data['fonte'] = product_data.get('fonte', '')
        validated_data['plataforma'] = product_data.get('plataforma', '')
        validated_data['rating'] = product_data.get('rating', '')
        validated_data['reviews'] = product_data.get('reviews', '')
        validated_data['vendas'] = product_data.get('vendas', '')
        validated_data['frete_gratis'] = product_data.get('frete_gratis', False)
        validated_data['comissao_pct'] = product_data.get('comissao_pct', '')
        
        # Preservar campos de fallback
        if product_data.get('_fallback'):
            validated_data['_fallback'] = True
        if product_data.get('_blocked'):
            validated_data['_blocked'] = True
        
        # Link de afiliado
        afiliado_link = product_data.get('afiliado_link') or product_data.get('link_afiliado', '')
        if afiliado_link and self.validator.validate_url(afiliado_link):
            validated_data['afiliado_link'] = self.sanitizer.sanitize_url(afiliado_link)
        else:
            validated_data['afiliado_link'] = validated_data['link']
        
        # Adicionar metadados de validação
        validated_data['_validation'] = {
            'errors': errors,
            'warnings': warnings,
            'is_valid': len(errors) == 0
        }
        
        return validated_data
    
    def _calculate_discount(self, preco_atual: str, preco_original: str) -> Optional[int]:
        """Calcula percentual de desconto"""
        if not preco_original or preco_atual == "Preço não disponível":
            return None
        
        try:
            # Converte preços para float
            atual = self._price_to_float(preco_atual)
            original = self._price_to_float(preco_original)
            
            if original <= 0 or atual <= 0:
                return None
            
            if atual >= original:
                return None
            
            desconto = int(((original - atual) / original) * 100)
            return max(0, min(99, desconto))  # Limitar entre 0 e 99%
            
        except (ValueError, TypeError, ZeroDivisionError):
            return None
    
    def _price_to_float(self, price_str: str) -> float:
        """Converte string de preço para float"""
        if not price_str:
            return 0.0
        
        # Remove caracteres não numéricos exceto vírgula e ponto
        cleaned = re.sub(r'[^\d,.]', '', price_str)
        
        if not cleaned:
            return 0.0
        
        # Converte para float
        if ',' in cleaned and '.' in cleaned:
            # Formato: 1.234,56
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            # Formato: 1234,56
            cleaned = cleaned.replace(',', '.')
        
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

# Instância global
product_validator = ProductDataValidator()
