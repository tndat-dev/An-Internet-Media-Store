FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . ./
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app
RUN addgroup -g 10001 -S aims && adduser -u 10001 -S aims -G aims
COPY --from=build --chown=aims:aims /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build --chown=aims:aims /app/.next ./.next
USER 10001
EXPOSE 3000
CMD ["npm", "run", "start"]
