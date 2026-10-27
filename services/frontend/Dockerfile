# Build the SPA, then serve it with nginx, proxying /api and /ws to C2_UPSTREAM (set at runtime).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY default.conf.template /etc/nginx/templates/default.conf.template
ENV C2_UPSTREAM=http://c2:8000
ENV NGINX_ENVSUBST_FILTER=C2_UPSTREAM
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
