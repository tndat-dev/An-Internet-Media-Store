FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . ./
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

FROM node:22-alpine
ARG AIMS_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision="${AIMS_SOURCE_REVISION}"
ENV NODE_ENV=production
WORKDIR /app
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
 && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
           /usr/local/bin/yarn /usr/local/bin/yarnpkg /usr/local/bin/pnpm \
 && addgroup -g 10001 -S aims \
 && adduser -u 10001 -S aims -G aims
COPY --from=build --chown=aims:aims /app/.next/standalone ./
COPY --from=build --chown=aims:aims /app/.next/static ./.next/static
USER 10001
EXPOSE 3000
CMD ["node", "server.js"]
