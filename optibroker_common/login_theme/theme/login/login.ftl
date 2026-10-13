<#import "template.ftl" as layout>
<!DOCTYPE html>
<html lang="en">
<@layout.head title=msg("doLogIn")/>
<body class="fsw-page fsw-login">
  <aside class="fsw-panel">
    <@layout.brand logoKey="fswPanelLogo" cls="fsw-panel-brand"/>
    <div class="fsw-panel-copy">
      <#if layout.has("fswHeadline")><h2 class="fsw-headline">${msg("fswHeadline")}</h2></#if>
      <span class="fsw-rule" aria-hidden="true"></span>
      <#if layout.has("fswTagline")><p class="fsw-tagline">${msg("fswTagline")}</p></#if>
    </div>
    <@layout.panelArt/>
  </aside>

  <div class="fsw-main">
    <main class="fsw-card">
      <@layout.brand/>
      <h1 class="fsw-title">${layout.has("fswWelcomeTitle")?then(msg("fswWelcomeTitle"), msg("doLogIn"))}</h1>
      <#if layout.has("fswWelcomeSubtitle")><p class="fsw-subtitle">${msg("fswWelcomeSubtitle")}</p></#if>

      <@layout.alert/>

      <form id="kc-form-login" class="fsw-form" action="${url.loginAction}" method="post">
        <div class="fsw-field">
          <label for="username">${msg("usernameOrEmail")}</label>
          <div class="fsw-input">
            <@layout.icon name="user"/>
            <input tabindex="1" id="username" name="username" type="text" value="${login.username!''}"
                   placeholder="${msg("fswUsernamePlaceholder")}" autocomplete="username" autofocus
                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"/>
          </div>
        </div>

        <#if realm.password>
          <div class="fsw-field">
            <label for="password">${msg("password")}</label>
            <div class="fsw-input">
              <@layout.icon name="lock"/>
              <input tabindex="2" id="password" name="password" type="password" placeholder="${msg("fswPasswordPlaceholder")}"
                     autocomplete="current-password"
                     aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"/>
              <button type="button" class="fsw-reveal" data-fsw-reveal="password" aria-pressed="false"
                      aria-label="${msg("fswShowPassword")}" title="${msg("fswShowPassword")}"><@layout.icon name="eye"/></button>
            </div>
          </div>
        </#if>

        <div class="fsw-actions">
          <#if realm.rememberMe && !usernameEditDisabled??>
            <label class="fsw-check">
              <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox"
                     <#if login.rememberMe?has_content>checked</#if>/>
              <span>${msg("rememberMe")}</span>
            </label>
          <#else>
            <span></span>
          </#if>
          <#if realm.resetPasswordAllowed>
            <a class="fsw-link" tabindex="5" href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a>
          </#if>
        </div>

        <input type="hidden" id="id-hidden-input" name="credentialId"
               <#if auth?? && auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
        <button class="fsw-btn" tabindex="4" name="login" id="kc-login" type="submit">${msg("doLogIn")}<span class="fsw-btn-arrow"><@layout.icon name="arrow"/></span></button>
      </form>

      <#if realm.password && social?? && social.providers?has_content>
        <div class="fsw-divider"><span>${msg("fswOr")}</span></div>
        <ul class="fsw-social">
          <#list social.providers as p>
            <li><a class="fsw-social-btn" id="social-${p.alias}" href="${p.loginUrl}">${p.displayName!p.alias}</a></li>
          </#list>
        </ul>
      </#if>

      <@layout.securityNote/>

      <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
        <p class="fsw-muted fsw-center fsw-gap">
          ${msg("noAccount")} <a class="fsw-link" tabindex="6" href="${url.registrationUrl}">${msg("doRegister")}</a>
        </p>
      </#if>
    </main>
    <@layout.footer/>
  </div>
  <@layout.script/>
</body>
</html>
