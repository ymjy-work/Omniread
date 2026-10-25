# Java 网关 + 前端静态资源。
#
# 三阶段：构建前端 → 构建 jar → 运行镜像。
# 构建阶段必须保留仓库布局（contracts/ + services/backend/）：DTO 由 openapi-generator
# 从 `contracts/openapi/rag-internal-v1.yaml` 生成，pom 里的路径是相对 `project.basedir` 的
# `../../contracts/openapi/…`——把契约漏掉，构建会以「生成器找不到 inputSpec」失败。

FROM node:22-bookworm-slim AS web
WORKDIR /workspace
COPY web/package.json web/package-lock.json ./web/
RUN cd web && npm ci --no-audit --no-fund
COPY web ./web
# Vite 的 `VITE_*` 是**构建期**静态内联进 bundle 的：运行时传环境变量没用，必须在这里注入。
# 缺省为空时须知第 8 条会渲染成「（联系方式见站点配置）」——门禁 G1 第 2 条过的就是它。
ARG VITE_RIGHTS_CONTACT
ENV VITE_RIGHTS_CONTACT=$VITE_RIGHTS_CONTACT
RUN cd web && npm run build

FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /workspace
COPY contracts ./contracts
COPY services/backend ./services/backend
RUN mvn -q -f services/backend/pom.xml -DskipTests package

FROM eclipse-temurin:25-jre
WORKDIR /app

# eMudhra 的根证书已从 Mozilla / Debian 的信任库里移除（其下属中间 CA 私钥泄露），
# 而 temurin 镜像自带的 cacerts 还没跟上。按 `keytool -list` 的结果匹配并删除，
# 不写死别名——JDK 换版本时别名会变，写死会静默失效。
# 本服务没有出站 HTTPS（唯一下游是 http://rag:8000），删掉不影响任何调用；
# 留着只会让人以为它在校验一张已经不该被信任的证书。
RUN for a in $(keytool -list -cacerts -storepass changeit 2>/dev/null \
      | grep -i emudhra | cut -d, -f1); do \
      keytool -delete -cacerts -storepass changeit -alias "$a" || exit 1; \
    done

COPY --from=build /workspace/services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar app.jar
COPY --from=web /workspace/web/dist ./web/dist

# 账户 / 会话 / 进度 / 配额都落这个 SQLite 文件：容器重建不能丢，部署侧要挂卷。
ENV OMNIREAD_DB_FILE=/app/var/omniread.db \
    OMNIREAD_WEB_DIST=/app/web/dist

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
