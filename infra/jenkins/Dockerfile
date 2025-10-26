# Jenkins LTS with JDK17
FROM jenkins/jenkins:lts-jdk17

USER root

# Install Docker CLI inside the Jenkins container so pipelines can use `agent { docker { ... } }`
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io curl ca-certificates python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# (Optional but handy) Install Docker Compose v2 CLI plugin
# Comment these lines if your host already provides `docker compose` to the container.
RUN mkdir -p /usr/libexec/docker/cli-plugins \
    && curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.2/docker-compose-linux-x86_64" -o /usr/libexec/docker/cli-plugins/docker-compose \
    && chmod +x /usr/libexec/docker/cli-plugins/docker-compose

# Preinstall required Jenkins plugins (Pipeline, Docker Pipeline, Git, JUnit, GitHub, JCasC)
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Skip setup wizard (we’ll create the admin user on first login if needed)
ENV JAVA_OPTS -Djenkins.install.runSetupWizard=false

USER jenkins

# Expose ports (documentary; compose maps them)
EXPOSE 8080 50000
