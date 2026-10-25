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
# 而 temurin 镜像自带的 cacerts 还没跟上——实测仍有 4 条，同镜像的 Debian 信任库是 0 条。
# 本服务没有出站 HTTPS（唯一下游是 http://rag:8000），删掉不影响任何调用；
# 留着只会让人以为它在校验一张已经不该被信任的证书。
#
# 别名要从 `-v` 的 `Alias name:` 取，不能拿 `-list` 的第一列按逗号切：
# temurin 的 cacerts 用 DN 当别名，别名本身就含逗号
# （`cn_emsign_root_ca__c1,o_emudhra_inc,ou_emsign_pki,c_us [jdk]`），切了就删不到。
# grep 没命中时用 `|| true` 兜住：将来 JDK 自己清干净了，这一步应当直接通过。
RUN keytool -list -v -cacerts -storepass changeit 2>/dev/null \
      | sed -n 's/^Alias name: //p' \
      | (grep -i emudhra || true) \
      | while IFS= read -r a; do \
          keytool -delete -cacerts -storepass changeit -alias "$a" || exit 1; \
        done

COPY --from=build /workspace/services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar app.jar
COPY --from=web /workspace/web/dist ./web/dist

# 账户 / 会话 / 进度 / 配额都落这个 SQLite 文件：容器重建不能丢，部署侧要挂卷。
ENV OMNIREAD_DB_FILE=/app/var/omniread.db \
    OMNIREAD_WEB_DIST=/app/web/dist

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
