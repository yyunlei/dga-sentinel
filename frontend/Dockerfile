FROM node:22-alpine AS build
WORKDIR /app

# 1) 先复制依赖清单（最大化缓存）
COPY package.json package-lock.json ./

# 2) npm 缓存持久化（速度提升明显）
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# 3) 再复制源码并构建
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
