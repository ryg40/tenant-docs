# The clean container of scripts/capture.py. See captures/README.md.
# The image holds no project file, no Pi profile, no credential and no value of a host.
# The capture script copies the history of the release or of a branch into the container at run time.
ARG BASE_IMAGE=node:22.23.3-bookworm-slim
# The scanner that `scripts/scan.sh` of tenant-pi pins, with the same digest.
ARG SCANNER_IMAGE=zricethezav/gitleaks:v8.28.0@sha256:cdbb7c955abce02001a9f6c9f602fb195b7fadc1e812065883f695d1eeaba854
FROM ${SCANNER_IMAGE} AS scanner

FROM ${BASE_IMAGE}

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git asciinema \
 && rm -rf /var/lib/apt/lists/*

# One neutral user. The base image has the user `node` with the id 1000.
RUN usermod --login alex --home /home/alex --move-home node \
 && groupmod --new-name alex node \
 && mkdir -p /capture \
 && chown alex:alex /capture

# The scanner binary is not in PATH, so a clean client does not have it.
# A capture that needs the scanner adds this directory to PATH in its setup.
COPY --from=scanner /usr/bin/gitleaks /usr/local/scanner/gitleaks

ENV LANG=C.UTF-8 TZ=UTC
USER alex
WORKDIR /home/alex
CMD ["sleep", "infinity"]
