# /mercado_livre_scraper/app/__init__.py

import sys
from flask import Flask

# Configura a codificação de E/S para UTF-8
if sys.version_info.major == 3:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def create_app():
    """Cria e configura a instância da aplicação Flask."""
    app = Flask(__name__, 
                static_folder='static',
                static_url_path='/static')

    # Configuração para servir arquivos estáticos sem cache (para desenvolvimento)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Sem cache

    # Inicializar bucket de imagens
    try:
        from .database import criar_bucket_se_nao_existir
        criar_bucket_se_nao_existir("imagens_melhoradas_tech")
    except Exception as e:
        print(f"Aviso: Não foi possível inicializar bucket: {e}")

    # Registra as rotas (Blueprints)
    from . import routes
    app.register_blueprint(routes.main_bp)

    return app