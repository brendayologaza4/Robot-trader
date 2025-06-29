from flask import Flask, render_template, request, redirect, url_for, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import datetime
import os
import numpy as np

app = Flask(__name__)
app.secret_key = 'votre_clé_ultra_secrète'

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Robottrader")
app.config["MONGO_URI"] = MONGO_URI
mongo = PyMongo(app)
db = mongo.db

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = db.users.find_one({"username": request.form['username']})
        if user and check_password_hash(user['password'], request.form['password']):
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return "Identifiants incorrects"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/config_api', methods=['GET', 'POST'])
def config_api():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = db.users.find_one({"username": session['username']})
    if user['role'] != 'admin':
        return "Accès refusé"
    if request.method == 'POST':
        db.users.update_one({"username": session['username']},
                            {"$set": {"api_key": request.form['api_key'],
                                      "api_secret": request.form['api_secret']}})
        return redirect(url_for('dashboard'))
    return render_template('config_api.html', api_key=user.get('api_key', ''), api_secret=user.get('api_secret', ''))

@app.route('/dashboard')
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
                           performance=round(fake_growth[-1]-fake_growth[0], 2))

@app.route('/update_balance', methods=['POST'])
def update_balance():
    if 'username' not in session:
        return redirect(url_for('login'))
    admin = db.users.find_one({"username": session['username']})
    if admin['role'] != 'admin':
        return "Accès refusé"
    db.users.update_one({"username": request.form['username']},
                        {"$set": {"balance": float(request.form['new_balance'])}})
    return redirect(url_for('dashboard'))

@app.route('/user/<username>')
def user_profile(username):
    if 'username' not in session:
        return redirect(url_for('login'))
    current_user = db.users.find_one({"username": session['username']})
    if current_user['role'] != 'admin':
        return render_template('403.html'), 403
    target = db.users.find_one({"username": username})
    if not target:
        return render_template('404.html'), 404
    balance = target.get('balance', 0)
    fake_growth = [round(balance * (1 + np.random.uniform(-0.02, 0.05)), 2) for _ in range(10)]
    dates = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%d-%m') for i in reversed(range(10))]
    performance = round(fake_growth[-1] - fake_growth[0], 2)
    return render_template('user_profile.html',
                           username=target['username'],
                           balance=balance,
                           chart_labels=dates,
                           chart_data=fake_growth,
                           performance=performance)

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = db.users.find_one({"username": session['username']})
    if user['role'] != 'client':
        return "Accès refusé"
    if request.method == 'POST':
        mode = request.form.get('mode')
        try:
            amount = float(request.form.get('amount', 0))
        except:
            return "Montant invalide"
        if amount <= 0:
            return "Montant invalide"
        data = { "username": user['username'],
                 "amount": amount,
                 "mode": "Carte bancaire" if mode=="card" else "Compte bancaire",
                 "date": datetime.datetime.now(),
                 "status": "En attente" }
        if mode == "card":
            if not all(request.form.get(f) for f in ("card_number","card_expiry","card_cvv")):
                return "Veuillez remplir tous les champs de la carte bancaire"
            data.update(card_number=request.form['card_number'],
                        card_expiry=request.form['card_expiry'],
                        card_cvv=request.form['card_cvv'])
        elif mode == "bank":
            if not all(request.form.get(f) for f in ("iban","bank_name","account_holder")):
                return "Veuillez remplir tous les champs du compte bancaire"
            data.update(iban=request.form['iban'],
                        bank_name=request.form['bank_name'],
                        account_holder=request.form['account_holder'])
        else:
            return "Mode non valide"
        db.withdraw_requests.insert_one(data)
        return redirect(url_for('dashboard'))
    return render_template('withdraw.html')

@app.route('/withdraw_requests')
def withdraw_requests():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = db.users.find_one({"username": session['username']})
    if user['role'] != 'admin':
        return "Accès refusé"
    reqs = list(db.withdraw_requests.find().sort("date", -1))
    return render_template('withdraw_requests.html', requests=reqs, admin=user)

@app.route('/process_withdrawal/<req_id>', methods=['POST'])
def process_withdrawal(req_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    user = db.users.find_one({"username": session['username']})
    if user['role'] != 'admin':
        return "Accès refusé"
    action = request.form.get('action')
    wr = db.withdraw_requests.find_one({"_id": ObjectId(req_id)})
    if not wr:
        return "Demande introuvable"
    if action in ('accept','reject'):
        db.withdraw_requests.update_one({"_id": ObjectId(req_id)},
                                        {"$set": {"status": "Traité" if action=="accept" else "Rejeté",
                                                  "processed_date": datetime.datetime.now()}})
    return redirect(url_for('withdraw_requests'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
