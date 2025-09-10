# /mercado_livre_scraper/run.py

import os
import sys
from app import create_app

print("Starting Mercado Livre Scraper...", file=sys.stderr)

try:
    app = create_app()
    print("Flask app created successfully!", file=sys.stderr)
except Exception as e:
    print(f"Error creating Flask app: {e}", file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.getenv('PORT', 80))
    
    print(f"Starting server on 0.0.0.0:{port}, debug={debug_mode}", file=sys.stderr)
    
    try:
        # Adicionado threaded=True para melhor responsividade
        app.run(host='0.0.0.0', debug=debug_mode, port=port, threaded=True)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)