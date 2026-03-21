FROM node:22-alpine
WORKDIR /app
COPY dist/ dist/
COPY bin/ bin/
COPY package.json .
RUN npm install --omit=dev 2>/dev/null || true
EXPOSE 5180
CMD ["node", "bin/opensens-office.js", "--port", "5180", "--host", "0.0.0.0"]
