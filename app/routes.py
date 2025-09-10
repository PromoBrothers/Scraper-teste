# app/routes.py

from flask import Blueprint, render_template, request, jsonify
import datetime
import pytz
import time
import requests # Adicionado para tratar exceções de request
import os
import re
import logging

# Importa as funções dos outros módulos
from . import scraping, services, database
from . import amazon_scraping # Importa o módulo da Amazon

# Importa o novo sistema unificado
from .scraper_factory import ScraperFactory
from .queue_manager import queue_manager
from .monitoring import metrics_collector, health_checker, alert_manager
from .cache_manager import cache_manager
from .validators import product_validator

main_bp = Blueprint('main', __name__)


def formatar_mensagem_marketing(produto_dados):
    """
    Formata a mensagem de marketing com base nas regras de categoria e promoção,
    calculando o desconto sempre que possível.
    """
    def extrair_valor_numerico(preco_str):
        """Função auxiliar para converter string de preço em float."""
        if not preco_str:
            return 0.0
        try:
            # Lógica robusta para tratar formatos como "1.079,10" e "1,079,10"
            preco_limpo = str(preco_str).replace('R$', '').strip().replace('.', '').replace(',', '.')
            return float(preco_limpo)
        except (ValueError, TypeError):
            return 0.0

    categorias = {
    'BATONS/MAQUIAGEM LABIAL': {
        'keywords': ['batom', 'gloss', 'lip tint', 'lábios', 'lipstick','balm labial', 'hidratante labial'],
        'frases': [
            "Lábios irresistíveis o dia todo! 💋",
            "Cor intensa com hidratação! 💄",
            "Beleza que começa no sorriso! 😍",
            "Textura leve, cor poderosa! 🌟",
            "Brilho e conforto para seus lábios! ✨"
        ]
    },
    'MAQUIAGEM OLHOS': {
        'keywords': ['máscara', 'rímel', 'delineador', 'sombra', 'paleta', 'cílios'],
        'frases': [
            "Olhar marcante em segundos! 👁️",
            "Cílios de impacto garantido! 🔥",
            "Seu olhar, seu poder! 💫",
            "Cor e intensidade no olhar! 🎨",
            "Olhos que conquistam sem esforço! 😉"
        ]
    },
    'ESMALTES/UNHAS': {
        'keywords': ['esmalte', 'unha', 'nail', 'cutícula'],
        'frases': [
            "Unhas de salão sem sair de casa! 💅",
            "Cores vibrantes que duram! 🌈",
            "Mãos que impressionam em cada detalhe! 🌸",
            "Unhas perfeitas, todos os dias! ✨",
            "Acabamento profissional em minutos! 🖤"
        ]
    },
    'CUIDADOS COM A PELE': {
        'keywords': ['pele', 'facial', 'creme', 'hidratante', 'skincare', 'ácido', 'sérum', 'protetor solar'],
        'frases': [
            "Sua pele merece esse cuidado! 💧",
            "Ritual de skincare completo! 🌿",
            "Beleza que vem de dentro pra fora! 🌸",
            "Proteção e hidratação na medida certa! ☀️",
            "Rotina simples, resultados incríveis! ✨"
        ]
    },
    'CUIDADOS COM O CABELO': {
        'keywords': ['cabelo', 'shampoo', 'condicionador', 'máscara capilar', 'finalizador'],
        'frases': [
            "Brilho e maciez em cada fio! ✨",
            "Recuperação intensa pro seu cabelo! 💆‍♀️",
            "Cabelos que atraem olhares! 😍",
            "Força e vitalidade da raiz às pontas! 🌿",
            "O tratamento que seu cabelo merece! 🌟"
        ]
    },
    'PERFUMES': {
        'keywords': ['perfume', 'fragrância', 'colônia', 'deo parfum', 'eau de toilette'],
        'frases': [
            "Fragrância que marca presença! 🌹",
            "Seu aroma, sua identidade! 🧴",
            "Perfume que traduz sua essência! 💫",
            "Notas que encantam em cada instante! 🌼",
            "Um toque de sofisticação no seu dia! 🕊️"
        ]
    },
    'CORPO & BANHO': {
        'keywords': ['sabonete', 'hidratante corporal', 'óleo', 'loção', 'body', 'creme hidratante'],
        'frases': [
            "Banho relaxante com cuidado extra! 🛁",
            "Pele macia da cabeça aos pés! 🧼",
            "Sensação de frescor e bem-estar! 🌿",
            "Autocuidado que transforma seu dia! ✨",
            "Toque suave que dura o dia todo! 💕"
        ]
    }
    }

    titulo = produto_dados.get('titulo', '')
    link = produto_dados.get('afiliado_link') or produto_dados.get('link', '')
    preco_atual_str = produto_dados.get('preco_atual', '')
    preco_original_str = produto_dados.get('preco_original')

    preco_atual_num = extrair_valor_numerico(preco_atual_str)
    preco_original_num = extrair_valor_numerico(preco_original_str)
    
    desconto_num = 0
    tem_promocao = False

    if preco_original_num > preco_atual_num > 0:
        tem_promocao = True
        desconto_num = round(((preco_original_num - preco_atual_num) / preco_original_num) * 100)

    frase_categoria = "Aproveite a oferta! ✨"
    for cat in categorias.values():
        if any(keyword in titulo.lower() for keyword in cat['keywords']):
            frase_categoria = cat['frases'][0]
            break

    if tem_promocao and desconto_num > 0:
        mensagem = (
            f"✨ *{titulo}*\n"
            f"💰 DE: ~~{preco_original_str}~~ POR: *{preco_atual_str}*\n"
            f"🎯 {desconto_num}% OFF\n"
            f"💬 {frase_categoria}\n"
            f"🛒 {link}\n\n"
            f"👾 Grupo de ofertas: https://linktr.ee/promobrothers.shop"
        )
    else:
        mensagem = (
            f"✨ *{titulo}*\n"
            f"💰 *{preco_atual_str}*\n"
            f"💬 {frase_categoria}\n"
            f"🛒 {link}\n\n"
            f"👾 Grupo de ofertas: https://linktr.ee/promobrothers.shop"
        )
        
    return mensagem.strip()

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/amazon')
def amazon():
    return render_template('amazon.html')

@main_bp.route('/afiliados')
def afiliados():
    return render_template('afiliados.html')

@main_bp.route('/teste')
def teste():
    return jsonify({'status': 'funcionando', 'mensagem': 'Flask está rodando!'})

@main_bp.route('/buscar', methods=['POST'])
def buscar():
    try:
        data = request.get_json()
        produto = data.get('produto', '').strip()
        if not produto:
            return jsonify({'error': 'Produto não pode estar vazio'}), 400
        max_pages = data.get('max_pages', 2)
        resultados = scraping.scrape_mercadolivre(produto, max_pages)
        if not resultados:
            resultados = scraping.busca_alternativa(produto)
        return jsonify({'success': True, 'resultados': resultados, 'total': len(resultados)})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/buscar-amazon', methods=['POST'])
def buscar_amazon():
    try:
        data = request.get_json()
        produto = data.get('produto', '').strip()
        if not produto:
            return jsonify({'error': 'Produto não pode estar vazio'}), 400
        max_pages = data.get('max_pages', 2)
        categoria = data.get('categoria', '')
        resultados = amazon_scraping.scrape_amazon(produto, max_pages, categoria)
        return jsonify({'success': True, 'produtos': resultados, 'total': len(resultados)})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/produto-amazon', methods=['POST'])
def produto_amazon():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        afiliado_link = data.get('afiliado_link', '').strip()
        if not url:
            return jsonify({'error': 'URL não pode estar vazia'}), 400
        if not ('amazon.com' in url or 'amzn.to' in url):
            return jsonify({'error': 'URL deve ser da Amazon'}), 400
        produto = amazon_scraping.scrape_produto_amazon_especifico(url, afiliado_link)
        return jsonify({'success': True, 'produto': produto})
    except Exception as e:
        return jsonify({'error': f'Erro ao analisar produto: {str(e)}'}), 500

@main_bp.route('/buscar-afiliados', methods=['POST'])
def buscar_afiliados():
    try:
        data = request.get_json()
        produto = data.get('produto', '').strip()
        if not produto:
            return jsonify({'error': 'Produto não pode estar vazio'}), 400
        max_pages = data.get('max_pages', 2)
        plataforma = data.get('plataforma', 'todas')
        ordenacao = data.get('ordenacao', 'relevancia')
        preco_min = data.get('preco_min', '')
        preco_max = data.get('preco_max', '')
        from . import affiliate_scraping
        resultados = affiliate_scraping.scrape_afiliados(
            produto=produto, max_pages=max_pages, plataforma=plataforma,
            ordenacao=ordenacao, preco_min=preco_min, preco_max=preco_max
        )
        return jsonify({'success': True, 'produtos': resultados, 'total': len(resultados)})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/produto', methods=['POST'])
def buscar_produto():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL não pode estar vazia'}), 400
        if 'mercadolivre.com' not in url and 'mercadolibre.com' not in url:
            return jsonify({'error': 'URL deve ser do Mercado Livre'}), 400
        produto = scraping.scrape_produto_especifico(url)
        if produto:
            return jsonify({'success': True, 'produto': produto})
        else:
            return jsonify({'error': 'Não foi possível extrair informações do produto'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/webhook', methods=['POST'])
def enviar_webhook():
    produto_para_salvar = {}
    try:
        data = request.get_json()
        tipo = data.get('type', 'mensagem')
        afiliado_link = data.get('afiliado_link', '').strip()
        
        if tipo == 'produto':
            produto_dados = data.get('produto', {})
            if not produto_dados:
                return jsonify({'error': 'Dados do produto não podem estar vazios'}), 400
            
            produto_para_salvar = produto_dados.copy()
            produto_para_salvar['afiliado_link'] = afiliado_link

            original_image_url = produto_para_salvar.get('imagem')
            if original_image_url:
                image_bytes = services.processar_imagem_para_quadrado(original_image_url)
                if image_bytes:
                    produto_para_salvar['processed_image_url'] = services.upload_imagem_processada(image_bytes)
            
            # Usar webhook para gerar mensagem ao invés de geração local
            try:
                mensagem_formatada = services.formatar_mensagem_com_ia(produto_para_salvar)
            except Exception as e:
                print(f"Erro ao gerar mensagem via webhook: {e}")
                # Fallback para geração local se webhook falhar
                mensagem_formatada = formatar_mensagem_marketing(produto_para_salvar)

            payload = { "message": mensagem_formatada, "produto_dados": produto_para_salvar }
            
            response = services.enviar_para_webhook(payload)
            
            # Usar a mensagem do webhook se disponível, senão usar a mensagem local
            final_message_to_return = response.webhook_message if hasattr(response, 'webhook_message') and response.webhook_message else mensagem_formatada
            
            database.salvar_promocao(produto_para_salvar, final_message=final_message_to_return)

            return jsonify({
                'success': True, 
                'message': 'Webhook enviado.', 
                'final_message': final_message_to_return,
                'image_url': produto_para_salvar.get('processed_image_url') or original_image_url,
                'webhook_status': response.status_code
            })
        else:
            return jsonify({'error': 'Tipo de webhook inválido para esta operação'}), 400
        
    except Exception as e:
        final_message_erro = f'Erro interno: {str(e)}'
        if produto_para_salvar:
            database.salvar_promocao(produto_para_salvar, final_message=final_message_erro)
        return jsonify({'error': final_message_erro}), 500

@main_bp.route('/webhook/processar', methods=['POST'])
def processar_produto_webhook():
    """Endpoint para processar produto automaticamente a partir da URL e link de afiliado"""
    try:
        data = request.get_json()
        url_produto = data.get('url_produto', '').strip()
        afiliado_link = data.get('afiliado_link', '').strip()
        
        if not url_produto:
            return jsonify({'error': 'URL do produto é obrigatória'}), 400
        
        if not afiliado_link:
            return jsonify({'error': 'Link de afiliado é obrigatório'}), 400
        
        # Detectar plataforma automaticamente
        platform = ScraperFactory.detect_platform_from_url(url_produto)
        if not platform:
            return jsonify({'error': 'Plataforma não suportada'}), 400
        
        # Criar scraper
        scraper = ScraperFactory.create_scraper(platform)
        if not scraper:
            return jsonify({'error': f'Scraper não disponível para {platform}'}), 400
        
        # Fazer scraping do produto
        start_time = time.time()
        try:
            produto_dados = scraper.scrape_product(url_produto, afiliado_link)
            response_time = time.time() - start_time
            
            print(f"DEBUG: Produto dados antes da validação: {produto_dados}")
            print(f"DEBUG: Blocked: {produto_dados.get('_blocked')}")
            print(f"DEBUG: Fallback: {produto_dados.get('_fallback')}")
            
            if not produto_dados:
                return jsonify({'error': 'Produto não encontrado ou não foi possível extrair dados'}), 404
            
            # Registrar métricas
            metrics_collector.record_scraping_metric(
                platform=platform,
                operation='webhook_product',
                success=True,
                response_time=response_time,
                products_found=1
            )
            
            # Processar imagem se disponível
            original_image_url = produto_dados.get('imagem')
            if original_image_url:
                try:
                    image_bytes = services.processar_imagem_para_quadrado(original_image_url)
                    if image_bytes:
                        produto_dados['processed_image_url'] = services.upload_imagem_processada(image_bytes)
                except Exception as e:
                    print(f"Erro ao processar imagem: {e}")
            
            # Usar webhook para gerar mensagem ao invés de geração local
            try:
                mensagem_formatada = services.formatar_mensagem_com_ia(produto_dados)
            except Exception as e:
                print(f"Erro ao gerar mensagem via webhook: {e}")
                # Fallback para geração local se webhook falhar
                mensagem_formatada = formatar_mensagem_marketing(produto_dados)
            
            # Enviar para webhook
            payload = {
                "message": mensagem_formatada,
                "produto_dados": produto_dados
            }
            
            webhook_response = services.enviar_para_webhook(payload)
            
            # Usar a mensagem do webhook se disponível, senão usar a mensagem local
            final_message_to_return = webhook_response.webhook_message if hasattr(webhook_response, 'webhook_message') and webhook_response.webhook_message else mensagem_formatada
            
            # Salvar no banco de dados
            database.salvar_promocao(produto_dados, final_message=final_message_to_return)
            
            return jsonify({
                'success': True,
                'message': 'Produto processado e webhook enviado com sucesso!',
                'produto': produto_dados,
                'final_message': final_message_to_return,
                'image_url': produto_dados.get('processed_image_url') or original_image_url,
                'webhook_status': webhook_response.status_code,
                'platform': platform,
                'response_time': round(response_time, 2)
            })
            
        except Exception as e:
            response_time = time.time() - start_time
            metrics_collector.record_scraping_metric(
                platform=platform,
                operation='webhook_product',
                success=False,
                response_time=response_time,
                error_message=str(e)
            )
            raise
            
    except Exception as e:
        return jsonify({'error': f'Erro ao processar produto: {str(e)}'}), 500

@main_bp.route('/produtos/<string:produto_id>', methods=['DELETE'])
def deletar_produto(produto_id):
    try:
        response = database.deletar_produto_db(produto_id)
        if response.data:
            return jsonify({'success': True, 'message': 'Produto deletado com sucesso!'}), 200
        else:
            return jsonify({'success': False, 'error': 'Produto não encontrado ou não foi possível deletar.'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/agendar_produto/<string:produto_id>', methods=['POST'])
def agendar_produto(produto_id):
    try:
        data = request.get_json()
        agendamento = data.get('agendamento')
        if not agendamento:
            return jsonify({'error': 'Dados de agendamento são obrigatórios'}), 400
        try:
            naive_dt = datetime.datetime.fromisoformat(agendamento)
            timezone_br = pytz.timezone('America/Sao_Paulo')
            agendamento_dt_br = timezone_br.localize(naive_dt)
            agendamento_dt_utc = agendamento_dt_br.astimezone(pytz.utc)
            agendamento_iso = agendamento_dt_utc.isoformat()
        except (ValueError, pytz.UnknownTimeZoneError) as ve:
            return jsonify({'error': f'Formato de data inválido: {ve}. Use YYYY-MM-DDTHH:MM'}), 400
        response = database.agendar_produto_db(produto_id, agendamento_iso)
        if response.data and len(response.data) > 0:
            return jsonify({'success': True, 'message': 'Produto agendado com sucesso!', 'agendamento': agendamento_dt_br.strftime('%Y-%m-%d %H:%M:%S')})
        else:
            return jsonify({'success': False, 'error': f'Produto com ID {produto_id} não encontrado.'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/produtos', methods=['GET'])
def listar_produtos():
    try:
        # CORREÇÃO: Lendo os parâmetros da URL da requisição
        status_filter = request.args.get('status', 'agendado')
        ordem_order = request.args.get('ordem', 'desc')
        
        produtos = database.listar_produtos_db(status_filter, ordem_order)
        
        # Converte as datas para o fuso horário de São Paulo para exibição
        for produto in produtos:
            for key in ["agendamento", "created_at"]:
                if produto.get(key) and isinstance(produto[key], str):
                    try:
                        dt_utc = datetime.datetime.fromisoformat(produto[key].replace('Z', '+00:00'))
                        dt_br = dt_utc.astimezone(pytz.timezone('America/Sao_Paulo'))
                        produto[key] = dt_br.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass # Deixa a data como está se houver erro de formato
                        
        return jsonify({'success': True, 'produtos': produtos})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao listar produtos do Supabase: {str(e)}'}), 500
    
@main_bp.route('/produtos/<string:produto_id>', methods=['GET'])
def obter_produto(produto_id):
    try:
        produto = database.obter_produto_db(produto_id)
        if produto:
            return jsonify({'success': True, 'produto': produto})
        else:
            return jsonify({'success': False, 'error': 'Produto não encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/produtos/<string:produto_id>', methods=['PUT'])
def editar_produto(produto_id):
    try:
        data = request.get_json()
        dados_atualizacao = {}

        # Coleta todos os campos que podem ser atualizados
        if 'imagem_url' in data:
            dados_atualizacao['imagem_url'] = data['imagem_url']
        if 'final_message' in data:
            dados_atualizacao['final_message'] = data['final_message']
        if 'preco_com_cupom' in data:
            dados_atualizacao['preco_com_cupom'] = data['preco_com_cupom']
        if 'cupom_info' in data:
            dados_atualizacao['cupom_info'] = data['cupom_info']

        # Verifica se pelo menos um campo foi enviado para atualização
        if not dados_atualizacao:
            return jsonify({'error': 'Pelo menos um campo deve ser fornecido para edição'}), 400

        # Chama a função do banco de dados para atualizar o produto
        response = database.atualizar_produto_db(produto_id, dados_atualizacao)

        if response.data:
            return jsonify({'success': True, 'message': 'Produto atualizado com sucesso!'})
        else:
            return jsonify({'success': False, 'error': f'Produto com ID {produto_id} não encontrado ou não foi possível atualizar.'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/enviar_produto_agendado/<string:produto_id>', methods=['POST'])
def enviar_produto_agendado(produto_id):
    try:
        data = request.get_json()
        afiliado_link = data.get('afiliado_link', '').strip()
        produto_db = database.obter_produto_db(produto_id)
        if not produto_db:
            return jsonify({'error': 'Produto não encontrado'}), 404
        if produto_db.get('final_message'):
            mensagem_completa = produto_db.get('final_message')
        else:
            produto_para_formatar = {
                'titulo': produto_db.get('titulo'),
                'link': produto_db.get('link_produto'),
                'link_afiliado': afiliado_link or produto_db.get('afiliado_link'),
                'preco_atual': produto_db.get('preco_com_cupom') or produto_db.get('preco_atual'),
                'preco_original': produto_db.get('preco_original'),
                'desconto': produto_db.get('desconto'),
                'tem_promocao': produto_db.get('tem_promocao')
            }
            # Usar webhook para gerar mensagem ao invés de geração local
            try:
                mensagem_completa = services.formatar_mensagem_com_ia(produto_para_formatar)
            except Exception as e:
                print(f"Erro ao gerar mensagem via webhook: {e}")
                # Fallback para geração local se webhook falhar
                mensagem_completa = formatar_mensagem_marketing(produto_para_formatar)
        payload = {"message": mensagem_completa.strip()}
        response = services.enviar_para_webhook(payload)
        
        # Usar a mensagem do webhook se disponível, senão usar a mensagem local
        final_message_to_return = response.webhook_message if hasattr(response, 'webhook_message') and response.webhook_message else mensagem_completa
        
        if response.status_code in [200, 201, 202]:
            return jsonify({
                'success': True, 
                'message': 'Produto enviado com sucesso!', 
                'final_message': final_message_to_return,
                'image_url': produto_db.get('imagem_url') or produto_db.get('processed_image_url')
            })
        else:
            return jsonify({'error': f'Webhook retornou status {response.status_code}', 'webhook_response': response.text}), 400
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/storage/imagens', methods=['GET'])
def listar_imagens():
    try:
        bucket_name = request.args.get('bucket', os.getenv('SUPABASE_BUCKET_NAME', 'imagens_melhoradas_tech'))
        pasta = request.args.get('pasta', '')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        search_term = request.args.get('search', '')
        imagens = database.listar_imagens_bucket(
            bucket_name=bucket_name, pasta=pasta, limit=limit,
            offset=offset, search_term=search_term
        )
        return jsonify({'success': True, 'imagens': imagens})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao listar imagens: {str(e)}'}), 500

@main_bp.route('/storage/pastas', methods=['GET'])
def listar_pastas():
    try:
        bucket_name = request.args.get('bucket', os.getenv('SUPABASE_BUCKET_NAME', 'imagens_melhoradas_tech'))
        pasta_pai = request.args.get('pasta_pai', '')
        
        pastas = database.listar_pastas_bucket(
            bucket_name=bucket_name,
            pasta_pai=pasta_pai
        )
        
        return jsonify({
            'success': True,
            'pastas': pastas
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao listar pastas: {str(e)}'}), 500

@main_bp.route('/storage/url_publica', methods=['POST'])
def obter_url_publica():
    try:
        data = request.get_json()
        bucket_name = data.get('bucket', os.getenv('SUPABASE_BUCKET_NAME', 'imagens_melhoradas_tech'))
        caminho_arquivo = data.get('caminho', '')
        
        if not caminho_arquivo:
            return jsonify({'success': False, 'error': 'Caminho do arquivo é obrigatório'}), 400
        
        url = database.obter_url_publica_imagem(
            bucket_name=bucket_name,
            caminho_arquivo=caminho_arquivo
        )
        
        if url:
            return jsonify({'success': True, 'url': url})
        else:
            return jsonify({'success': False, 'error': 'Não foi possível obter a URL'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao obter URL: {str(e)}'}), 500

# === NOVAS ROTAS DO SISTEMA UNIFICADO ===

@main_bp.route('/scrape/unified', methods=['POST'])
def scrape_unified():
    """Endpoint unificado para scraping de qualquer plataforma"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        affiliate_link = data.get('affiliate_link', '').strip()
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Detectar plataforma automaticamente
        platform = ScraperFactory.detect_platform_from_url(url)
        if not platform:
            return jsonify({'error': 'Plataforma não suportada'}), 400
        
        # Criar scraper
        scraper = ScraperFactory.create_scraper(platform)
        if not scraper:
            return jsonify({'error': f'Scraper não disponível para {platform}'}), 400
        
        # Fazer scraping
        start_time = time.time()
        try:
            product_data = scraper.scrape_product(url, affiliate_link)
            response_time = time.time() - start_time
            
            if product_data:
                # Registrar métricas
                metrics_collector.record_scraping_metric(
                    platform=platform,
                    operation='product',
                    success=True,
                    response_time=response_time,
                    products_found=1
                )
                
                return jsonify({
                    'success': True,
                    'product': product_data,
                    'platform': platform,
                    'response_time': round(response_time, 2)
                })
            else:
                # Registrar falha
                metrics_collector.record_scraping_metric(
                    platform=platform,
                    operation='product',
                    success=False,
                    response_time=response_time,
                    error_message='Produto não encontrado'
                )
                
                return jsonify({'error': 'Produto não encontrado'}), 404
                
        except Exception as e:
            response_time = time.time() - start_time
            metrics_collector.record_scraping_metric(
                platform=platform,
                operation='product',
                success=False,
                response_time=response_time,
                error_message=str(e)
            )
            raise
            
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/scrape/search', methods=['POST'])
def search_unified():
    """Endpoint unificado para busca em qualquer plataforma"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        platform = data.get('platform', 'todas')
        max_pages = data.get('max_pages', 2)
        
        if not query:
            return jsonify({'error': 'Query é obrigatória'}), 400
        
        products = []
        
        if platform == 'todas':
            # Buscar em todas as plataformas
            available_platforms = ScraperFactory.get_available_platforms()
            for platform_name in available_platforms:
                try:
                    scraper = ScraperFactory.create_scraper(platform_name)
                    if scraper:
                        start_time = time.time()
                        platform_products = scraper.scrape_search(query, max_pages)
                        response_time = time.time() - start_time
                        
                        # Registrar métricas
                        metrics_collector.record_scraping_metric(
                            platform=platform_name,
                            operation='search',
                            success=True,
                            response_time=response_time,
                            products_found=len(platform_products)
                        )
                        
                        products.extend(platform_products)
                        
                except Exception as e:
                    metrics_collector.record_scraping_metric(
                        platform=platform_name,
                        operation='search',
                        success=False,
                        response_time=0,
                        error_message=str(e)
                    )
                    continue
        else:
            # Buscar em plataforma específica
            scraper = ScraperFactory.create_scraper(platform)
            if not scraper:
                return jsonify({'error': f'Plataforma {platform} não suportada'}), 400
            
            start_time = time.time()
            products = scraper.scrape_search(query, max_pages)
            response_time = time.time() - start_time
            
            # Registrar métricas
            metrics_collector.record_scraping_metric(
                platform=platform,
                operation='search',
                success=True,
                response_time=response_time,
                products_found=len(products)
            )
        
        return jsonify({
            'success': True,
            'products': products,
            'total': len(products),
            'platform': platform
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/queue/add', methods=['POST'])
def add_to_queue():
    """Adiciona produto à fila de processamento"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        affiliate_link = data.get('affiliate_link', '').strip()
        priority = data.get('priority', 0)
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Detectar plataforma
        platform = ScraperFactory.detect_platform_from_url(url)
        if not platform:
            return jsonify({'error': 'Plataforma não suportada'}), 400
        
        # Adicionar à fila
        task_id = queue_manager.add_task(url, affiliate_link, platform, priority)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'platform': platform,
            'message': 'Produto adicionado à fila'
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/queue/status', methods=['GET'])
def queue_status():
    """Retorna status da fila"""
    try:
        status = queue_manager.get_queue_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/queue/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Retorna status de uma tarefa específica"""
    try:
        task = queue_manager.get_task(task_id)
        if not task:
            return jsonify({'error': 'Tarefa não encontrada'}), 404
        
        return jsonify({'success': True, 'task': task.to_dict()})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/queue/task/<task_id>', methods=['DELETE'])
def cancel_task(task_id):
    """Cancela uma tarefa"""
    try:
        success = queue_manager.cancel_task(task_id)
        if success:
            return jsonify({'success': True, 'message': 'Tarefa cancelada'})
        else:
            return jsonify({'error': 'Tarefa não encontrada ou não pode ser cancelada'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/monitoring/stats', methods=['GET'])
def get_monitoring_stats():
    """Retorna estatísticas de monitoramento"""
    try:
        stats = metrics_collector.get_stats_summary()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/monitoring/health', methods=['GET'])
def get_health_status():
    """Retorna status de saúde do sistema"""
    try:
        health = health_checker.check_health()
        return jsonify({'success': True, 'health': health})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/monitoring/alerts', methods=['GET'])
def get_alerts():
    """Retorna alertas ativos"""
    try:
        alerts = alert_manager.check_alerts()
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/monitoring/platform/<platform>', methods=['GET'])
def get_platform_stats(platform):
    """Retorna estatísticas de uma plataforma específica"""
    try:
        stats = metrics_collector.get_platform_stats(platform)
        return jsonify({'success': True, 'platform': platform, 'stats': stats})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/cache/stats', methods=['GET'])
def get_cache_stats():
    """Retorna estatísticas do cache"""
    try:
        stats = cache_manager.get_stats()
        memory_usage = cache_manager.get_memory_usage()
        return jsonify({
            'success': True,
            'cache_stats': stats,
            'memory_usage': memory_usage
        })
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@main_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Limpa o cache"""
    try:
        cache_manager.clear()
        return jsonify({'success': True, 'message': 'Cache limpo com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500