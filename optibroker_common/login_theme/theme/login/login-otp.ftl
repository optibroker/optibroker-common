<#import "template.ftl" as layout>
<@layout.card title=msg("fswOtpTitle") subtitle=msg("fswOtpSubtitle")>
  <#-- A wrong code shows under the field; anything else shows here. -->
  <#if message?has_content && !messagesPerField.existsError('totp')>
    <div class="fsw-alert ${message.type}" role="alert">${kcSanitize(message.summary)?no_esc}</div>
  </#if>

  <form id="kc-otp-login-form" class="fsw-form" action="${url.loginAction}" method="post">
    <#-- Only when the user has registered more than one authenticator. -->
    <#if otpLogin.userOtpCredentials?size gt 1>
      <fieldset class="fsw-devices">
        <legend>${msg("fswWhichAuthenticator")}</legend>
        <#list otpLogin.userOtpCredentials as otpCredential>
          <label class="fsw-device" for="kc-otp-credential-${otpCredential?index}">
            <input id="kc-otp-credential-${otpCredential?index}" type="radio" name="selectedCredentialId"
                   value="${otpCredential.id}" <#if otpCredential.id == otpLogin.selectedCredentialId>checked</#if>/>
            <span>${otpCredential.userLabel}</span>
          </label>
        </#list>
      </fieldset>
    </#if>

    <div class="fsw-field">
      <label for="otp">${msg("loginOtpOneTime")}</label>
      <input id="otp" name="otp" type="text" inputmode="numeric" autocomplete="one-time-code" autofocus
             placeholder="${msg("fswCodePlaceholder")}"
             aria-invalid="<#if messagesPerField.existsError('totp')>true</#if>"
             <#if messagesPerField.existsError('totp')>aria-describedby="input-error-otp-code"</#if>/>
      <#if messagesPerField.existsError('totp')>
        <span id="input-error-otp-code" class="fsw-field-error" aria-live="polite">
          ${kcSanitize(messagesPerField.get('totp'))?no_esc}
        </span>
      </#if>
    </div>

    <button class="fsw-btn" name="login" id="kc-login" type="submit">${msg("fswOtpButton")}</button>
  </form>

  <p class="fsw-muted fsw-center fsw-gap">${msg("fswOtpLost")}</p>
</@layout.card>
