FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/task
COPY finance_runtime/__init__.py finance_runtime/engine.py finance_runtime/sources.py finance_runtime/task.py ./finance_runtime/
USER 10001:10001
CMD ["python", "-c", "import time; time.sleep(3600)"]
