FROM node:22-alpine AS build
WORKDIR /app
ENV ASTRO_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/tmp/npm-cache npm ci --cache /tmp/npm-cache
COPY . .
# The public origin goes into the canonical links and the sitemap at build time.
ARG SITE_URL
ENV SITE_URL=$SITE_URL
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
# The revision label changes with each commit. It is the last step, so the layers above stay in the build cache.
ARG REVISION=unknown
LABEL org.opencontainers.image.title="tenant-docs" \
      org.opencontainers.image.revision=$REVISION
