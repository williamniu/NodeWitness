# Shared base for NodeWitness terminal tasks. Holds tools only: no task files,
# tests, oracle solutions or hidden inputs ever enter this image.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
RUN apt-get update \
 && apt-get install -y --no-install-recommends git sqlite3 procps \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --home-dir /home/agent agent
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
USER 10001:10001
WORKDIR /workspace
CMD ["sleep", "infinity"]
