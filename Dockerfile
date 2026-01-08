# Usamos a imagem completa (não-slim) para garantir que tenha tudo sem precisar de internet extra
FROM python:3.9

WORKDIR /app

# Copia os requisitos
COPY requirements.txt .

# Instala as bibliotecas do Python direto
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

# Expõe a porta
EXPOSE 8501

# Comando de inicialização
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
