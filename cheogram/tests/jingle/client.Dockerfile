FROM python:3.12-slim
# 1.x pinned: the connect()/TLS API differs between major versions.
RUN pip install --no-cache-dir "slixmpp~=1.17"
COPY client.py /client.py
CMD ["python3", "-u", "/client.py"]
