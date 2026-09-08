# 构建阶段
FROM node:20-alpine AS build
WORKDIR /app
# 默认国内镜像源（本地构建免代理）；海外/CI 可 --build-arg NPM_REGISTRY= 覆盖
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY package*.json ./
# React 19 与部分插件的 peer 声明冲突，lockfile 以 legacy-peer-deps 生成，此处须一致
RUN npm ci --legacy-peer-deps --registry=${NPM_REGISTRY}
COPY . .
RUN npm run build

# 运行阶段：nginx 托管静态资源 + 反代后端
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
