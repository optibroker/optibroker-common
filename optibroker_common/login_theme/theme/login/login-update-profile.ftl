<#import "template.ftl" as layout>
<@layout.card title=msg("fswProfileTitle") subtitle=msg("fswProfileSubtitle")>
  <@layout.alert/>

  <form id="kc-update-profile-form" class="fsw-form" action="${url.loginAction}" method="post">
    <#if user.editUsernameAllowed>
      <div class="fsw-field">
        <label for="username">${msg("username")}</label>
        <input id="username" name="username" type="text" value="${(user.username!'')}" autocomplete="username"/>
      </div>
    </#if>

    <div class="fsw-field">
      <label for="email">${msg("email")}</label>
      <input id="email" name="email" type="email" value="${(user.email!'')}" autocomplete="email"/>
    </div>

    <div class="fsw-row">
      <div class="fsw-field">
        <label for="firstName">${msg("firstName")}</label>
        <input id="firstName" name="firstName" type="text" value="${(user.firstName!'')}" autocomplete="given-name"/>
      </div>
      <div class="fsw-field">
        <label for="lastName">${msg("lastName")}</label>
        <input id="lastName" name="lastName" type="text" value="${(user.lastName!'')}" autocomplete="family-name"/>
      </div>
    </div>

    <button class="fsw-btn" type="submit">${msg("doSubmit")}</button>

    <#if isAppInitiatedAction?? && isAppInitiatedAction>
      <button class="fsw-btn fsw-btn-secondary" name="cancel-aia" value="true" type="submit">${msg("doCancel")}</button>
    </#if>
  </form>
</@layout.card>
