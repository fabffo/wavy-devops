FROM node:24-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
ARG API_BASE_URL=http://localhost:8088/api
RUN sed -i -E \
    -e "s|apiBaseUrl:[[:space:]]*'http://localhost:8088/api'|apiBaseUrl: '${API_BASE_URL}'|g" \
    -e "s|apiBaseUrl:[[:space:]]*\"http://localhost:8088/api\"|apiBaseUrl: '${API_BASE_URL}'|g" \
    -e "s|apiBaseUrl:[[:space:]]*'http://localhost:18088/api'|apiBaseUrl: '${API_BASE_URL}'|g" \
    -e "s|apiBaseUrl:[[:space:]]*\"http://localhost:18088/api\"|apiBaseUrl: '${API_BASE_URL}'|g" \
    -e "s|apiBaseUrl:[[:space:]]*' */api *'|apiBaseUrl: '${API_BASE_URL}'|g" \
    -e "s|apiBaseUrl:[[:space:]]*\" */api *\"|apiBaseUrl: '${API_BASE_URL}'|g" \
    src/environments/environment.ts src/environments/environment.local.ts src/environments/environment.prod.ts
RUN npm run build

FROM nginx:1.29-alpine

RUN printf '%s\n' \
    'server {' \
    '  listen 80;' \
    '  server_name _;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  location / {' \
    '    try_files $uri $uri/ /index.html;' \
    '  }' \
    '}' \
    > /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/wavy-pwa/browser /usr/share/nginx/html

EXPOSE 80
