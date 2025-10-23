from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
# Chave secreta para a sessão - Lida da variável de ambiente SECRETE_KEY
app.secret_key = os.environ.get('SECRET_KEY')

# Configuração do banco de dados e pasta de uploads
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Senha de administração - Lida da variável de ambiente ADMIN_PASSWORD
SENHA_ADMIN = os.environ.get('ADMIN_PASSWORD')

# Modelo do Banco de Dados
class Arquivo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(250), nullable=False)
    caminho_arquivo = db.Column(db.String(150), nullable=False)
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
            filename = secure_filename(arquivo.filename)
            caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            arquivo.save(caminho_completo)
            
            novo_arquivo = Arquivo(
                nome=request.form['nome'],
                descricao=request.form['descricao'],
                caminho_arquivo=filename,
                categoria=request.form['categoria']
            )
            db.session.add(novo_arquivo)
            db.session.commit()
            return redirect(url_for('gerenciar'))
    
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
    
    caminho_do_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], arquivo.caminho_arquivo)
    
    if os.path.exists(caminho_do_arquivo):
        os.remove(caminho_do_arquivo)
    
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