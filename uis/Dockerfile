FROM node:22-alpine
WORKDIR /app

# Copy package manifests and install dependencies
COPY uis/website/package.json /app/website/
COPY uis/backoffice/package.json uis/backoffice/package-lock.json /app/backoffice/

RUN cd /app/website && npm install && \
    cd /app/backoffice && npm ci

# Copy application source code
COPY uis/website /app/website
COPY uis/backoffice /app/backoffice

# Copy start script
COPY uis/start.sh /app/
RUN chmod +x /app/start.sh

EXPOSE 3000 3001
CMD ["/app/start.sh"]