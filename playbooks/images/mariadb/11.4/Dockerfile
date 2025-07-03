FROM mariadb:11.4

# The default timeout is 30 seconds, which may not be sufficient in lower performance environments.
RUN sed -i 's/sleep 1/sleep 4/' /usr/local/bin/docker-entrypoint.sh
