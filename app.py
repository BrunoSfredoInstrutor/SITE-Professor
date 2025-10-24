from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import boto3

# --- CONFIGURAÇÃO DE SEGURANÇA AWS S3 ---
# CORREÇÃO CRÍTICA: Lendo o NOME da variável de ambiente, não o VALOR.
# Os VALORES de AKIAZX... e zDEK... devem estar apenas nas Config Vars do Render.
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
S3_REGION = os.environ.get('S3_REGION', 'sa-east-1')

# Inicializa o cliente S3
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=S3_REGION
)
# --- FIM DA CONFIGURAÇÃO AWS S3 ---

app = Flask(__name__)
# Chave secreta para a sessão - Lida da variável de ambiente
app.secret_key = os.environ.get('SECRET_KEY')

# Configuração do banco de dados (A pasta de uploads local foi REMOVIDA, pois usamos S3)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Senha de administração - Lida da variável de ambiente ADMIN_PASSWORD
SENHA_ADMIN = os.environ.get('ADMIN_PASSWORD')

# Modelo do Banco de Dados
class Arquivo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(250), nullable=False)
    # caminho_arquivo AGORA ARMAZENA A URL COMPLETA DO S3
    caminho_arquivo = db.Column(db.String(300), nullable=False) # Aumentando o tamanho para URLs longas
    categoria = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Arquivo('{self.nome}', '{self.descricao}', '{self.categoria}')"

with app.app_context():
    db.create_all()

# --- Rotas Principais do Site ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fisica')
def fisica():
    arquivos = Arquivo.query.filter_by(categoria='fisica').all()
    return render_template('fisica.html', arquivos=arquivos)

@app.route('/programacao')
def programacao():
    arquivos = Arquivo.query.filter_by(categoria='programacao').all()
    return render_template('programacao.html', arquivos=arquivos)

@app.route('/robotica')
def robotica():
    arquivos = Arquivo.query.filter_by(categoria='robotica').all()
    return render_template('robotica.html', arquivos=arquivos)

@app.route('/atividades')
def atividades():
    arquivos = Arquivo.query.filter_by(categoria='atividades').all()
    return render_template('atividades.html', arquivos=arquivos)

# --- Funcionalidades de Administração ---

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_arquivo():
    if 'logado' not in session or not session['logado']:
        return redirect(url_for('gerenciar'))

    if request.method == 'POST':
        if 'arquivo' not in request.files:
            return 'Nenhum arquivo enviado'
        
        arquivo = request.files['arquivo']
        if arquivo.filename == '':
            return 'Nenhum arquivo selecionado'

        if arquivo:
            # 1. Gera um nome de arquivo seguro
            filename = secure_filename(arquivo.filename)
            
            # --- LÓGICA DE UPLOAD PARA O S3 ---
            try:
                # 2. Faz o upload do stream do arquivo diretamente para o S3
                s3_client.upload_fileobj(
                    arquivo.stream,                # O stream de dados do arquivo
                    S3_BUCKET_NAME,                # Nome do Bucket S3
                    filename,                      # Nome do arquivo no S3
                    ExtraArgs={
                        # Configuração de acesso público de leitura
                        'ContentType': arquivo.content_type,
                        'ACL': 'public-read' 
                    }
                )
                
                # 3. CRIA A URL PÚBLICA do S3
                s3_url = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{filename}"
                
                # 4. Salva a URL no banco de dados
                novo_arquivo = Arquivo(
                    nome=request.form['nome'],
                    descricao=request.form['descricao'],
                    caminho_arquivo=s3_url, # <--- SALVANDO A URL DO S3
                    categoria=request.form['categoria']
                )
                db.session.add(novo_arquivo)
                db.session.commit()
                
                return redirect(url_for('gerenciar'))
            
            except Exception as e:
                return f"Erro ao fazer upload para o S3. Verifique as credenciais e o nome do bucket: {e}"
            # --- FIM DA LÓGICA S3 ---
    
    return render_template('adicionar.html')

@app.route('/gerenciar', methods=['GET', 'POST'])
def gerenciar():
    if request.method == 'POST':
        senha = request.form.get('senha')
        if senha == SENHA_ADMIN:
            session['logado'] = True
            return redirect(url_for('gerenciar'))
        else:
            return "Senha Incorreta. Tente novamente."
    
    if 'logado' in session and session['logado']:
        arquivos = Arquivo.query.all()
        return render_template('gerenciar.html', arquivos=arquivos)
    
    return render_template('login.html')

@app.route('/deletar/<int:id>')
def deletar(id):
    if 'logado' not in session or not session['logado']:
        return "Acesso negado."

    arquivo = Arquivo.query.get_or_404(id)
    
    # --- LÓGICA DE DELEÇÃO DO S3 ---
    
    # 1. Obtém o nome do arquivo a partir da URL salva no DB (é a última parte da URL)
    nome_arquivo_s3 = arquivo.caminho_arquivo.split('/')[-1]
    
    try:
        s3_client.delete_object(
            Bucket=S3_BUCKET_NAME,
            Key=nome_arquivo_s3
        )
    except Exception as e:
        # Se falhar no S3 (ex: arquivo já foi deletado), apenas registra o aviso
        print(f"Aviso: Não foi possível deletar o arquivo {nome_arquivo_s3} do S3. Erro: {e}")
    # --- FIM DA LÓGICA DE DELEÇÃO DO S3 ---
    
    # 2. Deleta o registro do banco de dados
    db.session.delete(arquivo)
    db.session.commit()
    return redirect(url_for('gerenciar'))

# --- Funcionalidade de Busca ---

@app.route('/buscar', methods=['GET'])
def buscar():
    termo = request.args.get('q')
    if termo:
        resultados = Arquivo.query.filter(
            db.or_(
                Arquivo.nome.like(f'%{termo}%'),
                Arquivo.descricao.like(f'%{termo}%')
            )
        ).all()
        return render_template('busca_resultados.html', resultados=resultados, termo=termo)
    return render_template('busca_resultados.html', resultados=[], termo=termo)

# --- Execução do Servidor ---
if __name__ == '__main__':
    app.run(debug=True)