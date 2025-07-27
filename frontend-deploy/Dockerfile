# Use nginx alpine image for minimal size
FROM nginx:alpine

# Remove default nginx site
RUN rm -rf /usr/share/nginx/html/*

# Copy custom nginx config to handle React router
RUN echo 'server { \
    listen 8080; \
    server_name localhost; \
    root /usr/share/nginx/html; \
    index index.html; \
    \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
    \
    location /api { \
        return 404; \
    } \
    \
    gzip on; \
    gzip_vary on; \
    gzip_min_length 1024; \
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json; \
}' > /etc/nginx/conf.d/default.conf

# Configure nginx to run on port 8080 as non-root user
RUN sed -i 's/listen       80;/listen       8080;/g' /etc/nginx/conf.d/default.conf \
    && sed -i '/user  nginx;/d' /etc/nginx/nginx.conf \
    && touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx

# Copy the React build output
# Note: You'll need to adjust this path based on whether the build creates 'dist' or 'build' folder
COPY dist/ /usr/share/nginx/html/

# Expose port 8080 (running as non-root)
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"] 