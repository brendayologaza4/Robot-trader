# 🚀 Démarrage de l'app Flask
# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import ccxt
import pandas as pd
import numpy as np
import datetime
import os
from xgboost import XGBClassifier

# --------- CONFIG ---------
app = Flask(__name__)
app.secret_key = "votre_cle_super_secrete"

# MongoDB (local ou Render)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Robottrader")
app.config["MONGO_URI"] = MONGO_URI
mongo = PyMongo(app)
db = mongo.db

# --------- RSI CALCUL ---------
def rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --------- ROUTES ---------
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

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
            "api_key": "",
            "api_secret": ""
        })
        return redirect(url_for('login'))
    return render_template("register.html")

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
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/config_api', methods=['GET', 'POST'])
def config_api():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = db.users.find_one({"username": session['username']})
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

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = db.users.find_one({"username": session['username']})
    if not user:
        return "Utilisateur introuvable"
    
    api_key = user.get('api_key')
    api_secret = user.get('api_secret')
    
    balance = 0
    if api_key and api_secret:
        try:
            binance = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret
            })
            account = binance.fetch_balance()
            balance = float(account['total'].get('USDT', 0))
        except Exception as e:
            print(f"❌ Erreur récupération solde : {e}")

    investments = list(db.history.find({"username": user['username']}))
    dates = [inv['date'] for inv in investments]
    profits = [inv['profit'] for inv in investments]
    performance = round(sum(profits), 2) if profits else 0

    transactions = [{
        "date": inv.get("date"),
        "asset": "BTC/USDT",
        "type": inv.get("action", "N/A"),
        "amount": inv.get("amount", 0),
        "result": inv.get("profit", 0)
    } for inv in investments]

    return render_template("dashboard.html",
                           username=user['username'],
                           balance=round(balance, 2),
                           performance=performance,
                           is_admin=(user['role'] == "admin"),
                           transactions=transactions,
                           chart_labels=dates,
                           chart_data=profits)

@app.route('/set_balance', methods=['POST'])
def set_balance():
    if 'username' in session:
        user = db.users.find_one({"username": session['username']})
        if user['role'] != "admin":
            return "Accès refusé"
        db.users.update_one(
            {"username": request.form['target_username']},
            {"$set": {"balance": float(request.form['new_balance'])}})
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/trade_auto')
def trade_auto():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session['username']})
    if not user.get('api_key') or not user.get('api_secret'):
        return "API Binance non configurée"

    try:
        binance = ccxt.binance({
            'apiKey': user['api_key'],
            'secret': user['api_secret']
        })
        binance.set_sandbox_mode(False)

        symbol = "BTC/USDT"
        ohlcv = binance.fetch_ohlcv(symbol, timeframe='1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = rsi(df['close'])
        df.dropna(inplace=True)
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

        X = df[['rsi']]
        y = df['target']
        model = XGBClassifier(use_label_encoder=False, eval_metric='logloss')
        model.fit(X[:-1], y[:-1])
        prediction = model.predict(X.tail(1))

        action = "buy" if prediction[0] == 1 else "sell"
        amount = 10  # valeur fixe pour test

        if action == "buy":
            order = binance.create_market_buy_order(symbol, amount / df['close'].iloc[-1])
        else:
            order = binance.create_market_sell_order(symbol, amount / df['close'].iloc[-1])

        profit = np.random.uniform(-5, 10)  # simulation de profit
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        db.history.insert_one({
            "username": session['username'],
            "date": now,
            "action": action,
            "amount": amount,
            "profit": round(profit, 2)
        })

        return redirect(url_for('dashboard'))

    except Exception as e:
        return f"Erreur trading automatique : {e}"

@app.route('/api/market-data')
def market_data():
    try:
        binance = ccxt.binance()
        ohlcv = binance.fetch_ohlcv('PAXG/USDT', timeframe='1m', limit=30)
        return jsonify([{
            'timestamp': x[0],
            'open': x[1],
            'high': x[2],
            'low': x[3],
            'close': x[4],
            'volume': x[5]
        } for x in ohlcv])
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/dashboard_data')
def dashboard_data_api():
    if 'username' not in session:
        return jsonify({"error": "Non autorisé"}), 401

    user = db.users.find_one({"username": session['username']})
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    username = user.get("username", "N/A")
    balance = round(user.get("balance", 0), 2)

    investments = list(db.history.find({"username": username}))
    dates = [inv['date'] for inv in investments]
    profits = [inv['profit'] for inv in investments]
    performance = round(sum(profits), 2) if profits else 0

    transactions = [{
        "date": inv.get("date"),
        "asset": "BTC/USDT",
        "type": inv.get("action", "N/A"),
        "amount": inv.get("amount", 0),
        "result": inv.get("profit", 0)
    } for inv in investments]

    return jsonify({
        "username": username,
        "balance": balance,
        "performance": performance,
        "chart_labels": dates,
        "chart_data": profits,
        "transactions": transactions
    })

# --------- RUN APP ---------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("✅ Serveur en ligne avec la base Robottrader !")
    app.run(debug=False, host="0.0.0.0", port=port)
