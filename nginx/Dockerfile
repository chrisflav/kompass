FROM nginx:latest

COPY nginx.conf /etc/nginx/nginx.conf
COPY kompass.nginx.conf /etc/nginx/sites-available/kompass.nginx.conf
RUN mkdir /etc/nginx/sites-enabled
RUN ln -s /etc/nginx/sites-available/kompass.nginx.conf /etc/nginx/sites-enabled/

CMD ["nginx", "-g", "daemon off;"]
