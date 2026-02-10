FROM docker.1ms.run/library/node:20-alpine

WORKDIR /app

COPY .npmrc package*.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set strict-ssl false \
    && npm install

COPY . .
RUN npm run build

EXPOSE 4173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]
