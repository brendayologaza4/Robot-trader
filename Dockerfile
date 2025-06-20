# Utilise une image officielle Python comme base
FROM python:3.11-slim

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie les fichiers de dépendances
COPY requirements.txt .

# Installe les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copie tout le contenu du projet dans le conteneur
COPY . .

# Expose le port sur lequel Flask va écouter
EXPOSE 5000

# Définit la commande pour lancer l'application Flask
CMD ["python", "app.py"]
