# Utilise une image Python officielle
FROM python:3.10

# Définir le dossier de travail
WORKDIR /app

# Copier les fichiers
COPY . /app

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port utilisé par Gunicorn
EXPOSE 5000

# Commande pour démarrer l'app avec Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
