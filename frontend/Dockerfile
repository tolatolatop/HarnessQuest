FROM m.daocloud.io/docker.io/library/node:22.22.3-alpine3.24 AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY index.html tsconfig.json ./
COPY src ./src
RUN npm run build

FROM m.daocloud.io/docker.io/library/nginx:1.27.5-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY certs /etc/nginx/certs
EXPOSE 80
EXPOSE 443
