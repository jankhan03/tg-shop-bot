FROM nginx:1.25-alpine
COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
# базовая копия; в compose у нас ещё примонтированы локальные папки для hot-reload
COPY webapp /usr/share/nginx/html
RUN mkdir -p /var/www/media
