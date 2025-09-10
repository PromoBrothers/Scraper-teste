# /app/monitoring.py
"""
Sistema de monitoramento e logging avançado para web scraping
"""

import logging
import time
import json
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import psutil
import os

logger = logging.getLogger(__name__)

@dataclass
class ScrapingMetrics:
    """Métricas de scraping"""
    timestamp: float
    platform: str
    operation: str  # 'search', 'product', 'error'
    success: bool
    response_time: float
    products_found: int = 0
    error_message: Optional[str] = None
    memory_usage: float = 0.0
    cpu_usage: float = 0.0

@dataclass
class SystemMetrics:
    """Métricas do sistema"""
    timestamp: float
    memory_usage: float
    cpu_usage: float
    active_threads: int
    cache_size: int
    queue_size: int
    processing_tasks: int

class MetricsCollector:
    """Coletor de métricas do sistema"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.scraping_metrics: deque = deque(maxlen=max_history)
        self.system_metrics: deque = deque(maxlen=max_history)
        self.lock = threading.Lock()
        
        # Estatísticas agregadas
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'platform_stats': defaultdict(lambda: {'requests': 0, 'success': 0, 'errors': 0}),
            'hourly_stats': defaultdict(lambda: {'requests': 0, 'success': 0, 'errors': 0}),
            'response_times': deque(maxlen=100),
            'error_types': defaultdict(int)
        }
    
    def record_scraping_metric(self, platform: str, operation: str, success: bool, 
                              response_time: float, products_found: int = 0, 
                              error_message: str = None):
        """Registra métrica de scraping"""
        with self.lock:
            metric = ScrapingMetrics(
                timestamp=time.time(),
                platform=platform,
                operation=operation,
                success=success,
                response_time=response_time,
                products_found=products_found,
                error_message=error_message,
                memory_usage=psutil.Process().memory_info().rss / 1024 / 1024,  # MB
                cpu_usage=psutil.cpu_percent()
            )
            
            self.scraping_metrics.append(metric)
            
            # Atualizar estatísticas
            self._update_stats(metric)
    
    def record_system_metric(self, cache_size: int = 0, queue_size: int = 0, processing_tasks: int = 0):
        """Registra métrica do sistema"""
        with self.lock:
            metric = SystemMetrics(
                timestamp=time.time(),
                memory_usage=psutil.Process().memory_info().rss / 1024 / 1024,  # MB
                cpu_usage=psutil.cpu_percent(),
                active_threads=threading.active_count(),
                cache_size=cache_size,
                queue_size=queue_size,
                processing_tasks=processing_tasks
            )
            
            self.system_metrics.append(metric)
    
    def _update_stats(self, metric: ScrapingMetrics):
        """Atualiza estatísticas agregadas"""
        self.stats['total_requests'] += 1
        
        if metric.success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
            if metric.error_message:
                self.stats['error_types'][metric.error_message] += 1
        
        # Estatísticas por plataforma
        platform_stats = self.stats['platform_stats'][metric.platform]
        platform_stats['requests'] += 1
        if metric.success:
            platform_stats['success'] += 1
        else:
            platform_stats['errors'] += 1
        
        # Estatísticas por hora
        hour_key = datetime.fromtimestamp(metric.timestamp).strftime('%Y-%m-%d %H:00')
        hourly_stats = self.stats['hourly_stats'][hour_key]
        hourly_stats['requests'] += 1
        if metric.success:
            hourly_stats['success'] += 1
        else:
            hourly_stats['errors'] += 1
        
        # Tempos de resposta
        self.stats['response_times'].append(metric.response_time)
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """Retorna resumo das estatísticas"""
        with self.lock:
            total = self.stats['total_requests']
            success_rate = (self.stats['successful_requests'] / total * 100) if total > 0 else 0
            
            # Tempo médio de resposta
            response_times = list(self.stats['response_times'])
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # Top 5 plataformas por requisições
            platform_stats = dict(self.stats['platform_stats'])
            top_platforms = sorted(platform_stats.items(), key=lambda x: x[1]['requests'], reverse=True)[:5]
            
            # Top 5 erros
            top_errors = sorted(self.stats['error_types'].items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                'total_requests': total,
                'success_rate': round(success_rate, 2),
                'avg_response_time': round(avg_response_time, 2),
                'top_platforms': top_platforms,
                'top_errors': top_errors,
                'memory_usage_mb': round(psutil.Process().memory_info().rss / 1024 / 1024, 2),
                'cpu_usage': psutil.cpu_percent(),
                'active_threads': threading.active_count()
            }
    
    def get_platform_stats(self, platform: str) -> Dict[str, Any]:
        """Retorna estatísticas específicas de uma plataforma"""
        with self.lock:
            platform_stats = self.stats['platform_stats'].get(platform, {'requests': 0, 'success': 0, 'errors': 0})
            
            # Filtrar métricas da plataforma
            platform_metrics = [m for m in self.scraping_metrics if m.platform == platform]
            
            if not platform_metrics:
                return platform_stats
            
            # Calcular estatísticas adicionais
            response_times = [m.response_time for m in platform_metrics]
            avg_response_time = sum(response_times) / len(response_times)
            
            # Últimas 24 horas
            cutoff_time = time.time() - 86400
            recent_metrics = [m for m in platform_metrics if m.timestamp > cutoff_time]
            
            return {
                **platform_stats,
                'avg_response_time': round(avg_response_time, 2),
                'recent_requests_24h': len(recent_metrics),
                'success_rate': round((platform_stats['success'] / platform_stats['requests'] * 100) if platform_stats['requests'] > 0 else 0, 2)
            }
    
    def get_error_analysis(self) -> Dict[str, Any]:
        """Retorna análise de erros"""
        with self.lock:
            error_metrics = [m for m in self.scraping_metrics if not m.success]
            
            if not error_metrics:
                return {'total_errors': 0, 'error_breakdown': {}}
            
            # Agrupar erros por tipo
            error_breakdown = defaultdict(int)
            for metric in error_metrics:
                error_type = metric.error_message or 'Unknown error'
                error_breakdown[error_type] += 1
            
            # Erros por plataforma
            platform_errors = defaultdict(int)
            for metric in error_metrics:
                platform_errors[metric.platform] += 1
            
            return {
                'total_errors': len(error_metrics),
                'error_breakdown': dict(error_breakdown),
                'platform_errors': dict(platform_errors),
                'recent_errors': [asdict(m) for m in error_metrics[-10:]]  # Últimos 10 erros
            }
    
    def get_performance_trends(self, hours: int = 24) -> Dict[str, List]:
        """Retorna tendências de performance"""
        with self.lock:
            cutoff_time = time.time() - (hours * 3600)
            recent_metrics = [m for m in self.scraping_metrics if m.timestamp > cutoff_time]
            
            if not recent_metrics:
                return {'timestamps': [], 'response_times': [], 'success_rate': []}
            
            # Agrupar por hora
            hourly_data = defaultdict(lambda: {'requests': 0, 'success': 0, 'response_times': []})
            
            for metric in recent_metrics:
                hour_key = datetime.fromtimestamp(metric.timestamp).strftime('%Y-%m-%d %H:00')
                hourly_data[hour_key]['requests'] += 1
                if metric.success:
                    hourly_data[hour_key]['success'] += 1
                hourly_data[hour_key]['response_times'].append(metric.response_time)
            
            # Ordenar por timestamp
            sorted_hours = sorted(hourly_data.items())
            
            timestamps = [hour for hour, _ in sorted_hours]
            response_times = [sum(data['response_times']) / len(data['response_times']) if data['response_times'] else 0 for _, data in sorted_hours]
            success_rate = [(data['success'] / data['requests'] * 100) if data['requests'] > 0 else 0 for _, data in sorted_hours]
            
            return {
                'timestamps': timestamps,
                'response_times': [round(rt, 2) for rt in response_times],
                'success_rate': [round(sr, 2) for sr in success_rate]
            }

class HealthChecker:
    """Verificador de saúde do sistema"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.health_status = {
            'status': 'healthy',
            'last_check': time.time(),
            'issues': []
        }
    
    def check_health(self) -> Dict[str, Any]:
        """Verifica saúde do sistema"""
        issues = []
        
        # Verificar uso de memória
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        if memory_usage > 1000:  # Mais de 1GB
            issues.append(f"Alto uso de memória: {memory_usage:.1f}MB")
        
        # Verificar CPU
        cpu_usage = psutil.cpu_percent()
        if cpu_usage > 80:
            issues.append(f"Alto uso de CPU: {cpu_usage:.1f}%")
        
        # Verificar taxa de sucesso
        stats = self.metrics_collector.get_stats_summary()
        if stats['success_rate'] < 80:
            issues.append(f"Baixa taxa de sucesso: {stats['success_rate']:.1f}%")
        
        # Verificar tempo de resposta
        if stats['avg_response_time'] > 10:
            issues.append(f"Tempo de resposta alto: {stats['avg_response_time']:.1f}s")
        
        # Determinar status
        if issues:
            status = 'unhealthy' if len(issues) > 2 else 'warning'
        else:
            status = 'healthy'
        
        self.health_status = {
            'status': status,
            'last_check': time.time(),
            'issues': issues,
            'memory_usage_mb': memory_usage,
            'cpu_usage': cpu_usage,
            'success_rate': stats['success_rate'],
            'avg_response_time': stats['avg_response_time']
        }
        
        return self.health_status

class AlertManager:
    """Gerenciador de alertas"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alert_thresholds = {
            'error_rate': 20,  # %
            'response_time': 15,  # segundos
            'memory_usage': 1000,  # MB
            'cpu_usage': 80  # %
        }
        self.last_alerts = {}
        self.alert_cooldown = 300  # 5 minutos
    
    def check_alerts(self) -> List[Dict[str, Any]]:
        """Verifica se há alertas para disparar"""
        alerts = []
        current_time = time.time()
        
        stats = self.metrics_collector.get_stats_summary()
        
        # Verificar taxa de erro
        error_rate = 100 - stats['success_rate']
        if error_rate > self.alert_thresholds['error_rate']:
            alert_key = 'error_rate'
            if self._should_alert(alert_key, current_time):
                alerts.append({
                    'type': 'error_rate',
                    'message': f"Taxa de erro alta: {error_rate:.1f}%",
                    'severity': 'high',
                    'timestamp': current_time
                })
                self.last_alerts[alert_key] = current_time
        
        # Verificar tempo de resposta
        if stats['avg_response_time'] > self.alert_thresholds['response_time']:
            alert_key = 'response_time'
            if self._should_alert(alert_key, current_time):
                alerts.append({
                    'type': 'response_time',
                    'message': f"Tempo de resposta alto: {stats['avg_response_time']:.1f}s",
                    'severity': 'medium',
                    'timestamp': current_time
                })
                self.last_alerts[alert_key] = current_time
        
        # Verificar uso de memória
        if stats['memory_usage_mb'] > self.alert_thresholds['memory_usage']:
            alert_key = 'memory_usage'
            if self._should_alert(alert_key, current_time):
                alerts.append({
                    'type': 'memory_usage',
                    'message': f"Alto uso de memória: {stats['memory_usage_mb']:.1f}MB",
                    'severity': 'medium',
                    'timestamp': current_time
                })
                self.last_alerts[alert_key] = current_time
        
        # Verificar CPU
        if stats['cpu_usage'] > self.alert_thresholds['cpu_usage']:
            alert_key = 'cpu_usage'
            if self._should_alert(alert_key, current_time):
                alerts.append({
                    'type': 'cpu_usage',
                    'message': f"Alto uso de CPU: {stats['cpu_usage']:.1f}%",
                    'severity': 'medium',
                    'timestamp': current_time
                })
                self.last_alerts[alert_key] = current_time
        
        return alerts
    
    def _should_alert(self, alert_key: str, current_time: float) -> bool:
        """Verifica se deve disparar alerta (considerando cooldown)"""
        if alert_key not in self.last_alerts:
            return True
        
        return current_time - self.last_alerts[alert_key] > self.alert_cooldown

# Instâncias globais
metrics_collector = MetricsCollector()
health_checker = HealthChecker(metrics_collector)
alert_manager = AlertManager(metrics_collector)

# Configurar logging
def setup_logging():
    """Configura sistema de logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('scraping.log'),
            logging.StreamHandler()
        ]
    )
    
    # Logger específico para métricas
    metrics_logger = logging.getLogger('metrics')
    metrics_handler = logging.FileHandler('metrics.log')
    metrics_handler.setFormatter(logging.Formatter('%(message)s'))
    metrics_logger.addHandler(metrics_handler)
    metrics_logger.setLevel(logging.INFO)

# Inicializar logging
setup_logging()
