# /app/queue_manager.py
"""
Sistema de fila para processamento assíncrono de produtos
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class ScrapingTask:
    """Representa uma tarefa de scraping"""
    id: str
    url: str
    affiliate_link: str
    platform: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Optional[Dict] = None
    priority: int = 0  # 0 = normal, 1 = high, -1 = low
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ScrapingTask':
        return cls(**data)

class QueueManager:
    """Gerenciador de fila para processamento de produtos"""
    
    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.tasks: Dict[str, ScrapingTask] = {}
        self.queue: List[str] = []  # IDs de tarefas ordenados por prioridade
        self.processing: set = set()  # IDs de tarefas sendo processadas
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.Lock()
        self.callbacks: Dict[str, Callable] = {}
        self.running = False
        self._worker_thread = None
        
        # Estatísticas
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'retry_tasks': 0
        }
    
    def register_callback(self, event: str, callback: Callable):
        """Registra callback para eventos"""
        self.callbacks[event] = callback
    
    def _trigger_callback(self, event: str, *args, **kwargs):
        """Dispara callback se registrado"""
        if event in self.callbacks:
            try:
                self.callbacks[event](*args, **kwargs)
            except Exception as e:
                logger.error(f"Erro no callback {event}: {e}")
    
    def add_task(self, url: str, affiliate_link: str, platform: str, 
                 priority: int = 0, max_retries: int = 3) -> str:
        """Adiciona nova tarefa à fila"""
        task_id = str(uuid.uuid4())
        
        task = ScrapingTask(
            id=task_id,
            url=url,
            affiliate_link=affiliate_link,
            platform=platform,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            max_retries=max_retries,
            priority=priority
        )
        
        with self.lock:
            self.tasks[task_id] = task
            self._insert_into_queue(task_id)
            self.stats['total_tasks'] += 1
        
        logger.info(f"Tarefa {task_id} adicionada à fila (prioridade: {priority})")
        self._trigger_callback('task_added', task)
        
        # Iniciar processamento se não estiver rodando
        if not self.running:
            self.start_processing()
        
        return task_id
    
    def _insert_into_queue(self, task_id: str):
        """Insere tarefa na fila mantendo ordem de prioridade"""
        task = self.tasks[task_id]
        
        # Inserir na posição correta baseada na prioridade
        insert_pos = 0
        for i, queued_id in enumerate(self.queue):
            queued_task = self.tasks[queued_id]
            if task.priority > queued_task.priority:
                insert_pos = i
                break
            insert_pos = i + 1
        
        self.queue.insert(insert_pos, task_id)
    
    def get_task(self, task_id: str) -> Optional[ScrapingTask]:
        """Retorna tarefa por ID"""
        return self.tasks.get(task_id)
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[ScrapingTask]:
        """Retorna tarefas por status"""
        return [task for task in self.tasks.values() if task.status == status]
    
    def get_queue_status(self) -> Dict:
        """Retorna status da fila"""
        with self.lock:
            return {
                'total_tasks': len(self.tasks),
                'pending_tasks': len(self.queue),
                'processing_tasks': len(self.processing),
                'completed_tasks': len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]),
                'failed_tasks': len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED]),
                'stats': self.stats.copy()
            }
    
    def start_processing(self):
        """Inicia processamento da fila"""
        if self.running:
            return
        
        self.running = True
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
        logger.info("Processamento da fila iniciado")
    
    def stop_processing(self):
        """Para processamento da fila"""
        self.running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Processamento da fila parado")
    
    def _process_queue(self):
        """Processa tarefas da fila"""
        while self.running:
            try:
                task_id = self._get_next_task()
                if task_id:
                    self._process_task(task_id)
                else:
                    time.sleep(1)  # Aguarda se não há tarefas
            except Exception as e:
                logger.error(f"Erro no processamento da fila: {e}")
                time.sleep(5)
    
    def _get_next_task(self) -> Optional[str]:
        """Retorna próxima tarefa para processar"""
        with self.lock:
            if not self.queue:
                return None
            
            # Pega a primeira tarefa da fila
            task_id = self.queue.pop(0)
            self.processing.add(task_id)
            return task_id
    
    def _process_task(self, task_id: str):
        """Processa uma tarefa específica"""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        try:
            # Atualizar status
            task.status = TaskStatus.PROCESSING
            task.started_at = time.time()
            
            logger.info(f"Processando tarefa {task_id}: {task.url}")
            self._trigger_callback('task_started', task)
            
            # Executar scraping
            result = self._execute_scraping(task)
            
            if result:
                # Sucesso
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                task.result = result
                self.stats['completed_tasks'] += 1
                
                logger.info(f"Tarefa {task_id} concluída com sucesso")
                self._trigger_callback('task_completed', task, result)
            else:
                # Falha
                self._handle_task_failure(task)
                
        except Exception as e:
            logger.error(f"Erro ao processar tarefa {task_id}: {e}")
            task.error_message = str(e)
            self._handle_task_failure(task)
        
        finally:
            with self.lock:
                self.processing.discard(task_id)
    
    def _execute_scraping(self, task: ScrapingTask) -> Optional[Dict]:
        """Executa o scraping da tarefa"""
        # Importar aqui para evitar dependência circular
        from .scraper_factory import ScraperFactory
        
        scraper = ScraperFactory.create_scraper(task.platform)
        if not scraper:
            raise Exception(f"Scraper não encontrado para plataforma: {task.platform}")
        
        return scraper.scrape_product(task.url, task.affiliate_link)
    
    def _handle_task_failure(self, task: ScrapingTask):
        """Trata falha de tarefa"""
        task.retry_count += 1
        
        if task.retry_count < task.max_retries:
            # Retry
            task.status = TaskStatus.RETRYING
            task.error_message = f"Tentativa {task.retry_count} falhou"
            
            # Reagendar com delay exponencial
            delay = min(60, 2 ** task.retry_count)
            threading.Timer(delay, self._retry_task, [task.id]).start()
            
            self.stats['retry_tasks'] += 1
            logger.info(f"Tarefa {task.id} será retentada em {delay}s (tentativa {task.retry_count})")
            self._trigger_callback('task_retrying', task)
        else:
            # Falha definitiva
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            self.stats['failed_tasks'] += 1
            
            logger.error(f"Tarefa {task.id} falhou definitivamente após {task.retry_count} tentativas")
            self._trigger_callback('task_failed', task)
    
    def _retry_task(self, task_id: str):
        """Reagenda tarefa para retry"""
        with self.lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = TaskStatus.PENDING
                task.started_at = None
                self._insert_into_queue(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancela uma tarefa"""
        with self.lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                if task.status in [TaskStatus.PENDING, TaskStatus.RETRYING]:
                    task.status = TaskStatus.FAILED
                    task.error_message = "Cancelada pelo usuário"
                    self.queue = [tid for tid in self.queue if tid != task_id]
                    return True
        return False
    
    def clear_completed_tasks(self, older_than_hours: int = 24):
        """Remove tarefas concluídas mais antigas que X horas"""
        cutoff_time = time.time() - (older_than_hours * 3600)
        
        with self.lock:
            to_remove = []
            for task_id, task in self.tasks.items():
                if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and 
                    task.completed_at and task.completed_at < cutoff_time):
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            logger.info(f"Removidas {len(to_remove)} tarefas antigas")
            return len(to_remove)

# Instância global do gerenciador de fila
queue_manager = QueueManager()
