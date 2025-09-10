# /app/cache_manager.py
"""
Sistema de cache para otimizar performance do web scraping
"""

import time
import hashlib
import json
import threading
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Entrada do cache"""
    data: Any
    timestamp: float
    ttl: float
    access_count: int = 0
    last_accessed: float = 0.0
    
    def is_expired(self) -> bool:
        """Verifica se a entrada expirou"""
        return time.time() - self.timestamp > self.ttl
    
    def is_stale(self, max_age: float) -> bool:
        """Verifica se a entrada está obsoleta"""
        return time.time() - self.timestamp > max_age

class CacheManager:
    """Gerenciador de cache com TTL e LRU"""
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self.access_order: list = []  # Para implementar LRU
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired_cleanups': 0
        }
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Gera chave única baseada nos argumentos"""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Recupera valor do cache"""
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # Verificar se expirou
            if entry.is_expired():
                del self.cache[key]
                self.access_order.remove(key)
                self.stats['misses'] += 1
                self.stats['expired_cleanups'] += 1
                return None
            
            # Atualizar estatísticas de acesso
            entry.access_count += 1
            entry.last_accessed = time.time()
            
            # Mover para o final da lista (mais recente)
            self.access_order.remove(key)
            self.access_order.append(key)
            
            self.stats['hits'] += 1
            return entry.data
    
    def set(self, key: str, data: Any, ttl: Optional[float] = None) -> None:
        """Armazena valor no cache"""
        with self.lock:
            if ttl is None:
                ttl = self.default_ttl
            
            # Verificar se precisa remover itens para fazer espaço
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()
            
            # Criar entrada
            entry = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=ttl
            )
            
            self.cache[key] = entry
            
            # Atualizar ordem de acesso
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
    
    def _evict_lru(self):
        """Remove o item menos recentemente usado"""
        if not self.access_order:
            return
        
        # Remove o primeiro item da lista (menos recente)
        lru_key = self.access_order.pop(0)
        if lru_key in self.cache:
            del self.cache[lru_key]
            self.stats['evictions'] += 1
    
    def delete(self, key: str) -> bool:
        """Remove item do cache"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                if key in self.access_order:
                    self.access_order.remove(key)
                return True
            return False
    
    def clear(self):
        """Limpa todo o cache"""
        with self.lock:
            self.cache.clear()
            self.access_order.clear()
    
    def cleanup_expired(self) -> int:
        """Remove itens expirados do cache"""
        with self.lock:
            expired_keys = []
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                if key in self.access_order:
                    self.access_order.remove(key)
            
            self.stats['expired_cleanups'] += len(expired_keys)
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': round(hit_rate, 2),
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'expired_cleanups': self.stats['expired_cleanups']
            }
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Retorna informações sobre uso de memória"""
        with self.lock:
            total_size = 0
            for entry in self.cache.values():
                try:
                    size = len(json.dumps(entry.data, default=str))
                    total_size += size
                except:
                    total_size += 1000  # Estimativa para dados não serializáveis
            
            return {
                'estimated_size_bytes': total_size,
                'estimated_size_mb': round(total_size / 1024 / 1024, 2),
                'entry_count': len(self.cache)
            }

class CachedScraper:
    """Decorator para adicionar cache a métodos de scraping"""
    
    def __init__(self, cache_manager: CacheManager, ttl: float = 3600):
        self.cache_manager = cache_manager
        self.ttl = ttl
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            # Gerar chave baseada na função e argumentos
            key = self.cache_manager._generate_key(func.__name__, *args, **kwargs)
            
            # Tentar recuperar do cache
            cached_result = self.cache_manager.get(key)
            if cached_result is not None:
                logger.debug(f"Cache hit para {func.__name__}")
                return cached_result
            
            # Executar função e armazenar resultado
            logger.debug(f"Cache miss para {func.__name__}")
            result = func(*args, **kwargs)
            
            if result is not None:
                self.cache_manager.set(key, result, self.ttl)
            
            return result
        
        return wrapper

# Instâncias globais
cache_manager = CacheManager(max_size=1000, default_ttl=3600)
cached_scraper = CachedScraper(cache_manager)

# Função para limpeza automática de cache
def start_cache_cleanup(interval: int = 300):
    """Inicia limpeza automática do cache em background"""
    def cleanup_worker():
        while True:
            try:
                time.sleep(interval)
                cleaned = cache_manager.cleanup_expired()
                if cleaned > 0:
                    logger.info(f"Cache cleanup: {cleaned} itens expirados removidos")
            except Exception as e:
                logger.error(f"Erro na limpeza do cache: {e}")
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("Cache cleanup iniciado")

# Iniciar limpeza automática
start_cache_cleanup()
