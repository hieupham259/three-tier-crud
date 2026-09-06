# Frontend image: Vite/React static build served by nginx-unprivileged on 0.0.0.0:8080.
#
# Stages:
#   deps    - npm ci from the committed lockfile with lifecycle scripts disabled
#   build   - type-check + unit tests + production build; a failing test fails the image build
#   runtime - nginx-unprivileged: uid 101, port 8080, nginx.pid and temp dirs under /tmp so the
#             root filesystem can be mounted read-only with only /tmp writable

FROM node:24.20.0-alpine3.24 AS deps
ENV CI=true \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM deps AS build
COPY . .
RUN npm test && npm run build

FROM nginxinc/nginx-unprivileged:1.30.4-alpine3.24 AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 8080
# USER 101 and CMD ["nginx", "-g", "daemon off;"] are inherited from the base image.
