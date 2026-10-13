<#import "template.ftl" as layout>
<#-- Users can be found by email unless the realm turned that off. -->
<#assign byEmail = realm.loginWithEmailAllowed>
<@layout.split title=msg("fswResetTitle") subtitle=byEmail?then(msg("fswResetSubtitleEmail"), msg("fswResetSubtitleUsername"))>
  <@layout.alert/>

  <form id="kc-reset-password-form" class="fsw-form" action="${url.loginAction}" method="post">
    <div class="fsw-field">
      <label for="username"><#if byEmail>${msg("fswEmailAddress")}<#else>${msg("username")}</#if></label>
      <div class="fsw-input">
        <@layout.icon name=byEmail?then("mail", "user")/>
        <input id="username" name="username" type="${(byEmail && realm.registrationEmailAsUsername)?then('email', 'text')}"
               value="${(auth.attemptedUsername)!''}" autocomplete="${byEmail?then('email', 'username')}" autofocus
               placeholder="${byEmail?then(msg("fswEmailPlaceholder"), msg("fswUsernameOnlyPlaceholder"))}"
               aria-invalid="<#if messagesPerField.existsError('username')>true</#if>"/>
      </div>
      <#if messagesPerField.existsError('username')>
        <span class="fsw-field-error" aria-live="polite">${kcSanitize(messagesPerField.get('username'))?no_esc}</span>
      </#if>
    </div>

    <button class="fsw-btn" id="kc-reset-submit" type="submit">${msg("fswSendResetLink")}</button>
  </form>

  <div class="fsw-divider"><span>${msg("fswOr")}</span></div>
  <p class="fsw-center"><a class="fsw-link" id="backToLogin" href="${url.loginUrl}">${msg("backToLogin")}</a></p>

  <div class="fsw-gap"><@layout.securityNote/></div>
</@layout.split>
