ARG NODE_IMAGE=docker.m.daocloud.io/library/node:20-alpine
ARG NGINX_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine
FROM ${NODE_IMAGE} AS build

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

ARG NGINX_IMAGE
FROM ${NGINX_IMAGE}
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 5173
