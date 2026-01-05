FROM python:3.9-slim

WORKDIR /app

# Instala as dependências (pandas, openpyxl, etc)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

# Expõe a porta 8501
EXPOSE 8501

# Inicia o app na porta 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
