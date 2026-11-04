FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Uygulama yalnızca Python standart kütüphanesini kullanır; pip kurulumu gerekmez.
COPY . /app

# Veritabanı ve HTML yedeği için kalıcı volume önerilir:
#   docker run -v yazilimsec-data:/app/data -p 3000:3000 yazilimsec
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=3)"

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "3000"]
