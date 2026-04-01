FROM node:22-slim AS deps
WORKDIR /app
COPY ui/package.json ui/package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY ui/ .

# NEXT_PUBLIC_* vars are baked at build time. Pass them as build args so each
# environment gets an image with the correct OIDC and API endpoint wired in.
ARG NEXT_PUBLIC_OIDC_ISSUER=""
ARG NEXT_PUBLIC_OIDC_CLIENT_ID="sparkpilot-ui"
ARG NEXT_PUBLIC_OIDC_REDIRECT_URI=""
ARG NEXT_PUBLIC_OIDC_AUDIENCE="sparkpilot-api"
ARG NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE="false"

ENV NEXT_PUBLIC_OIDC_ISSUER=${NEXT_PUBLIC_OIDC_ISSUER}
ENV NEXT_PUBLIC_OIDC_CLIENT_ID=${NEXT_PUBLIC_OIDC_CLIENT_ID}
ENV NEXT_PUBLIC_OIDC_REDIRECT_URI=${NEXT_PUBLIC_OIDC_REDIRECT_URI}
ENV NEXT_PUBLIC_OIDC_AUDIENCE=${NEXT_PUBLIC_OIDC_AUDIENCE}
ENV NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE=${NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE}

RUN npm run build

FROM node:22-slim AS runner
ENV NODE_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN addgroup --system sparkpilot && adduser --system --ingroup sparkpilot sparkpilot

COPY --from=builder --chown=sparkpilot:sparkpilot /app/.next/standalone ./
COPY --from=builder --chown=sparkpilot:sparkpilot /app/.next/static ./.next/static
COPY --from=builder --chown=sparkpilot:sparkpilot /app/public ./public

USER sparkpilot

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
