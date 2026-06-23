FROM us-central1-docker.pkg.dev/cal-icor-hubs/user-images/base-python-image:aa924984d219

ENV NB_USER=jovyan

USER root
# Install all apt packages
COPY apt.txt /tmp/apt.txt
RUN apt-get -qq update --yes && \
    apt-get -qq install --yes --no-install-recommends \
        $(grep -v ^# /tmp/apt.txt) && \
    apt-get -qq purge && \
    apt-get -qq clean && \
    rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Conda / Python packages
# ------------------------------------------------------------
# Copy environment.yml for additional packages
USER ${NB_USER}
COPY --chown=${NB_USER}:${NB_USER} environment.yml /tmp/environment.yml

# Update existing /srv/conda/notebook environment with new packages
RUN mamba env update -n notebook -f /tmp/environment.yml && \
    mamba clean -afy && rm -rf /tmp/environment.yml

# The .NET SDK comes from apt (dotnet-sdk-10.0 -> /usr/lib/dotnet), which ships
# the Microsoft.AspNetCore.App shared framework the .NET Interactive kernel
# needs. Put it first on PATH and point DOTNET_ROOT at it so the kernel and the
# `dotnet` CLI resolve that runtime.
ENV DOTNET_ROOT=/usr/lib/dotnet
ENV PATH="/usr/lib/dotnet:${CONDA_DIR}/envs/notebook/bin:${PATH}"

# Install the .NET Interactive (Polyglot) Jupyter kernel so users can compile
# and run C# in notebook cells. The `dotnet` SDK itself comes from apt
# (dotnet-sdk-10.0, see apt.txt). https://github.com/dotnet/interactive
#
# The tool and kernelspec must live in baked image locations rather than the
# user's home directory (~/.dotnet, ~/.local/share/jupyter), which is masked by
# a persistent volume at runtime on the hub.
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_NOLOGO=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV DOTNET_TOOLS=${NB_PYTHON_PREFIX}/dotnet-tools
# Tool version targets net10.0; keep its major in sync with the apt dotnet-sdk.
RUN dotnet tool install Microsoft.dotnet-interactive \
    --version 1.0.712001 \
    --tool-path "${DOTNET_TOOLS}"
RUN "${DOTNET_TOOLS}/dotnet-interactive" jupyter install \
    --path "${NB_PYTHON_PREFIX}/share/jupyter/kernels"

COPY --chown=${NB_USER}:${NB_USER} postBuild /tmp/postBuild
RUN chmod +x /tmp/postBuild && /tmp/postBuild && rm -rf /tmp/postBuild

# ------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------
USER root
RUN rm -rf /tmp/*
RUN rm -rf /root/.cache

ENV REPO_DIR=/srv/repo
RUN install -d -o ${NB_USER} -g ${NB_USER} ${REPO_DIR}
COPY --chown=${NB_USER}:${NB_USER} . ${REPO_DIR}

# Add start script
RUN chmod +x "${REPO_DIR}/start"
ENV R2D_ENTRYPOINT="${REPO_DIR}/start"
# Add entrypoint
ENV PYTHONUNBUFFERED=1

USER ${NB_USER}
WORKDIR /home/${NB_USER}

EXPOSE 8888

ENTRYPOINT ["/usr/local/bin/repo2docker-entrypoint"]

#ENTRYPOINT ["tini", "--"]
