FROM alpine:3.21

RUN apk add --no-cache \
    bash \
    coreutils \
    curl \
    python3 \
    py3-pip \
    jq \
    git \
    && adduser -D -s /bin/bash sandbox

WORKDIR /workspace
USER sandbox

CMD ["sleep", "infinity"]
