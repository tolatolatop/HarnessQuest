# OAuth 第三方用户管理接入

HarnessQuest 支持把第三方用户目录接入为登录入口。系统完成 OAuth 授权后，会用第三方返回的邮箱匹配本地用户；如果邮箱不存在，会自动创建一个 `member` 用户。

## 接入模型

- 前端入口：`GET /api/v1/auth/oauth/status` 判断是否启用，启用后跳转 `GET /api/v1/auth/oauth/login`。
- 后端回调：`GET /api/v1/auth/oauth/callback`。
- 兼容旧入口：`/api/v1/auth/oidc/*` 仍保留，已有 OIDC 配置不需要立即迁移。
- 安全校验：登录发起时写入 `hq_oauth_state` HttpOnly cookie，回调时校验 `state`，校验失败会拒绝登录。
- 用户落库：以邮箱为唯一身份标识；新用户默认 `role=member`，无本地密码。

## GitHub 快速接入示例

GitHub OAuth App 使用授权码流程：用户授权后，服务端用 `code` 换取 access token，再调用 GitHub API 获取用户信息。GitHub 官方文档说明 access token 可用于请求 `GET https://api.github.com/user`，`user:email` scope 可读取用户私有邮箱。参考 GitHub Docs：

- Authorizing OAuth apps: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- Scopes for OAuth apps: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps

### 1. 创建 GitHub OAuth App

在 GitHub 创建 OAuth App：

- Homepage URL: `https://db.lan:18443`
- Authorization callback URL: `https://db.lan:18443/api/v1/auth/oauth/callback`

保存 GitHub 生成的 `Client ID` 和 `Client Secret`。

### 2. 配置 HarnessQuest

编辑 `.env`：

```env
OAUTH_ENABLED=true
OAUTH_PROVIDER=github
OAUTH_CLIENT_ID=<github-client-id>
OAUTH_CLIENT_SECRET=<github-client-secret>
OAUTH_REDIRECT_URI=https://db.lan:18443/api/v1/auth/oauth/callback
OAUTH_SCOPE=read:user user:email
```

GitHub provider 已内置默认端点：

```env
OAUTH_AUTHORIZATION_URL=https://github.com/login/oauth/authorize
OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
OAUTH_USERINFO_URL=https://api.github.com/user
OAUTH_EMAIL_URL=https://api.github.com/user/emails
```

通常不需要显式配置这些端点。只有接入 GitHub Enterprise 或代理网关时才需要覆盖。

### 3. 重启服务

```bash
docker compose up -d --force-recreate api web
```

如果只改 OAuth 配置，通常不需要重建镜像；重启 `api` 让环境变量生效即可。重启 `web` 可确保登录页使用最新前端包。

### 4. 验证

```bash
curl -k https://db.lan:18443/api/v1/auth/oauth/status
```

期望返回：

```json
{"enabled": true}
```

然后打开登录页，点击 `使用 OAuth 登录`。授权完成后，系统会把 JWT 写入浏览器 `localStorage.hq_token` 并回到首页。

## 接入其他 OAuth/OIDC 提供方

### OIDC 提供方

如果对方支持 OIDC discovery，保留旧配置也可用：

```env
OIDC_ENABLED=true
OIDC_ISSUER=https://idp.example.com
OIDC_CLIENT_ID=<client-id>
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://db.lan:18443/api/v1/auth/oidc/callback
```

新配置方式也支持 OIDC：

```env
OAUTH_ENABLED=true
OAUTH_PROVIDER=oidc
OIDC_ISSUER=https://idp.example.com
OAUTH_CLIENT_ID=<client-id>
OAUTH_CLIENT_SECRET=<client-secret>
OAUTH_REDIRECT_URI=https://db.lan:18443/api/v1/auth/oauth/callback
OAUTH_SCOPE=openid email profile
```

### 通用 OAuth2 提供方

如果对方不支持 OIDC discovery，直接配置端点：

```env
OAUTH_ENABLED=true
OAUTH_PROVIDER=generic
OAUTH_CLIENT_ID=<client-id>
OAUTH_CLIENT_SECRET=<client-secret>
OAUTH_REDIRECT_URI=https://db.lan:18443/api/v1/auth/oauth/callback
OAUTH_AUTHORIZATION_URL=https://idp.example.com/oauth/authorize
OAUTH_TOKEN_URL=https://idp.example.com/oauth/token
OAUTH_USERINFO_URL=https://idp.example.com/oauth/userinfo
OAUTH_SCOPE=email profile
```

要求 `userinfo` 返回中包含 `email` 字段。若邮箱在单独接口返回，可额外配置：

```env
OAUTH_EMAIL_URL=https://idp.example.com/oauth/user/emails
```

## 当前边界

- 当前只做登录和本地用户自动创建，不同步第三方组织、团队、角色。
- 用户角色默认 `member`，管理员仍需在本系统内调整。
- 账号唯一键是邮箱；第三方账号更换邮箱会被视为新用户。
- 退出登录只清理本系统 token，不会退出第三方登录态。
