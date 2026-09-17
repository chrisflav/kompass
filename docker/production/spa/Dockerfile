# The Kompass SPA, served as static files with the API proxied in beside it.
#
# Build context is the repository root (the frontend lives outside this
# directory, and the build needs its sources).

FROM node:22-alpine AS build

WORKDIR /build

# Dependencies first, so a source-only change does not reinstall them.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Empty on purpose: nginx serves the API from the same origin as the SPA, so
# every request the client makes is relative and no CORS is involved. A build
# that points the SPA at a different backend can override this.
ARG VITE_API_BASE=""
ARG VITE_OAUTH_CLIENT_ID="kompass-frontend-dev"
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_OAUTH_CLIENT_ID=$VITE_OAUTH_CLIENT_ID
RUN npm run build

FROM nginx:latest

COPY docker/production/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/production/spa/spa.nginx.conf /etc/nginx/sites-available/spa.nginx.conf
RUN mkdir /etc/nginx/sites-enabled \
    && ln -s /etc/nginx/sites-available/spa.nginx.conf /etc/nginx/sites-enabled/

COPY --from=build /build/dist /var/www/kompass_spa

CMD ["nginx", "-g", "daemon off;"]
