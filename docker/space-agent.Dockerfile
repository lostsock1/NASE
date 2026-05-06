FROM node:22-bookworm-slim

ARG SPACE_AGENT_REPO=https://github.com/agent0ai/space-agent.git
ARG SPACE_AGENT_REF=main

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --depth 1 --branch "${SPACE_AGENT_REF}" "${SPACE_AGENT_REPO}" space-agent

WORKDIR /opt/space-agent
RUN npm ci

EXPOSE 8788

CMD ["node", "space", "serve"]
