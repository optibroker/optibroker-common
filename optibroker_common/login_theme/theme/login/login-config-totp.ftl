<#import "template.ftl" as layout>
<#assign manual = mode?? && mode = "manual">
<!DOCTYPE html>
<html lang="en">
<@layout.head title=msg("loginTotpTitle")/>
<body class="fsw-page fsw-totp">
  <header class="fsw-topbar">
    <@layout.brand cls="fsw-topbar-brand"/>
  </header>

  <div class="fsw-setup">
    <h1 class="fsw-setup-title">${layout.has("fswTotpTitle")?then(msg("fswTotpTitle"), msg("loginTotpTitle"))}</h1>
    <#if layout.has("fswTotpSubtitle")><p class="fsw-setup-subtitle">${msg("fswTotpSubtitle")}</p></#if>

    <#-- Field errors show under their field; anything else shows here, except
         Keycloak's "You need to set up Mobile Authenticator" warning, which the
         page itself already says. -->
    <#if message?has_content && message.type != 'warning' && !messagesPerField.existsError('totp','userLabel')>
      <div class="fsw-alert ${message.type}" role="alert">${kcSanitize(message.summary)?no_esc}</div>
    </#if>

    <main class="fsw-setup-card" id="kc-totp-settings">
      <section class="fsw-setup-step is-tinted">
        <span class="fsw-step-num">1</span>
        <div class="fsw-step-body">
          <h2>${msg("fswTotpInstallTitle")}</h2>
          <p>${msg("fswTotpInstallText")}</p>
          <ul class="fsw-apps" id="kc-totp-supported-apps">
            <#-- Keycloak's list, less FreeOTP (look-alike paid apps share its
                 name in the stores), plus Authy: free on iOS and Android. Any TOTP app
                 works; these are suggestions for someone who has none. -->
            <#list totp.supportedApplications?filter(a -> a != "totpAppFreeOTPName") + ["fswAuthy"] as app>
              <#assign slug = (app == "fswAuthy")?then("authy", app?keep_after("totpApp")?keep_before("Name")?lower_case)>
              <li class="fsw-app">
                <span class="fsw-app-icon">
                <#switch slug>
                  <#case "google">
                    <svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#4285F4" d="M43.6 24.5c0-1.4-.1-2.8-.4-4.1H24v7.8h11c-.5 2.5-1.9 4.6-4 6v5h6.5c3.8-3.5 6.1-8.6 6.1-14.7Z"/><path fill="#34A853" d="M24 44c5.4 0 10-1.8 13.4-4.8l-6.5-5c-1.8 1.2-4.1 1.9-6.9 1.9-5.3 0-9.7-3.6-11.3-8.4H6v5.2C9.3 39.5 16.1 44 24 44Z"/><path fill="#FBBC05" d="M12.7 27.7c-.4-1.2-.6-2.5-.6-3.7s.2-2.6.6-3.7v-5.2H6A20 20 0 0 0 4 24c0 3.2.8 6.3 2 9l6.7-5.3Z"/><path fill="#EA4335" d="M24 11.9c3 0 5.7 1 7.8 3l5.8-5.8C34 5.9 29.4 4 24 4 16.1 4 9.3 8.5 6 15.1l6.7 5.2c1.6-4.8 6-8.4 11.3-8.4Z"/></svg>
                    <#break>
                  <#case "authy">
                    <svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="20" fill="#ec1c24"/><g fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round"><path d="M17 27.5 13.5 24a3 3 0 0 1 4.2-4.2l5.5 5.5"/><path d="M31 20.5l3.5 3.5a3 3 0 0 1-4.2 4.2l-5.5-5.5"/><path d="M20.5 17l3.5-3.5"/><path d="M27.5 31 24 34.5"/></g></svg>
                    <#break>
                  <#case "microsoftauthenticator">
                    <svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#1a73d6" d="M24 4 7 10v12c0 10.5 7.3 19.4 17 22 9.7-2.6 17-11.5 17-22V10L24 4Z"/><circle cx="24" cy="19" r="6" fill="#fff"/><path fill="#fff" d="M13.5 33c2-5 6-7.5 10.5-7.5S32.5 28 34.5 33c-2.9 3.3-6.5 5.6-10.5 6.7-4-1.1-7.6-3.4-10.5-6.7Z"/></svg>
                    <#break>
                  <#default>
                    <@layout.icon name="phone"/>
                </#switch>
                </span>
                <span class="fsw-app-name">${msg(app)}</span>
              </li>
            </#list>
          </ul>
        </div>
      </section>

      <section class="fsw-setup-step">
        <span class="fsw-step-num">2</span>
        <#if manual>
          <div class="fsw-step-body fsw-scan">
            <div>
              <h2>${msg("fswTotpManualTitle")}</h2>
              <p>${msg("fswTotpManualText")}</p>
              <ul class="fsw-policy">
                <li id="kc-totp-type">${msg("loginTotpType")}: ${msg("loginTotp." + totp.policy.type)}</li>
                <li id="kc-totp-algorithm">${msg("loginTotpAlgorithm")}: ${totp.policy.getAlgorithmKey()}</li>
                <li id="kc-totp-digits">${msg("loginTotpDigits")}: ${totp.policy.digits}</li>
                <#if totp.policy.type = "totp">
                  <li id="kc-totp-period">${msg("loginTotpInterval")}: ${totp.policy.period}</li>
                <#elseif totp.policy.type = "hotp">
                  <li id="kc-totp-counter">${msg("loginTotpCounter")}: ${totp.policy.initialCounter}</li>
                </#if>
              </ul>
            </div>
            <div class="fsw-qr-col">
              <p class="fsw-secret" id="kc-totp-secret-key">${totp.totpSecretEncoded}</p>
              <button type="button" class="fsw-chip" data-fsw-copy="kc-totp-secret-key" data-fsw-copied="${msg("fswTotpCopied")}">
                <@layout.icon name="copy"/><span>${msg("fswTotpCopy")}</span>
              </button>
              <a class="fsw-chip" href="${totp.qrUrl}" id="mode-barcode">${msg("fswTotpScanInstead")}</a>
            </div>
          </div>
        <#else>
          <div class="fsw-step-body fsw-scan">
            <div>
              <h2>${msg("fswTotpScanTitle")}</h2>
              <p>${msg("fswTotpScanText")}</p>
            </div>
            <div class="fsw-qr-col">
              <div class="fsw-qr">
                <img id="kc-totp-secret-qr-code" src="data:image/png;base64, ${totp.totpSecretQrCode}" alt="QR code to scan with your authenticator app"/>
              </div>
              <a class="fsw-chip" href="${totp.manualUrl}" id="mode-manual"><@layout.icon name="copy"/><span>${msg("fswTotpCantScan")}</span></a>
            </div>
            <div class="fsw-hint">
              <svg class="fsw-hint-art" viewBox="0 0 64 56" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="8" y="4" width="24" height="46" rx="5" transform="rotate(-8 20 27)"/><path d="M44 12l6-4M46 22h8M44 32l6 4"/>
              </svg>
              <p class="fsw-hint-title">${msg("fswTotpHintTitle")}</p>
              <p class="fsw-hint-text">${msg("fswTotpHintText")}</p>
            </div>
          </div>
        </#if>
      </section>

      <section class="fsw-setup-step">
        <span class="fsw-step-num">3</span>
        <div class="fsw-step-body">
          <h2>${msg("fswTotpVerifyTitle")}</h2>
          <p>${msg("fswTotpVerifyText")}</p>

          <form id="kc-totp-settings-form" class="fsw-form" action="${url.loginAction}" method="post">
            <div class="fsw-row">
              <div class="fsw-field">
                <label for="totp">${msg("fswTotpCode")} <span class="fsw-required">*</span></label>
                <input id="totp" name="totp" type="text" inputmode="numeric" autocomplete="one-time-code"
                       placeholder="${msg("fswCodePlaceholder")}"
                       aria-invalid="<#if messagesPerField.existsError('totp')>true</#if>"
                       <#if messagesPerField.existsError('totp')>aria-describedby="input-error-otp-code"</#if>/>
                <#if messagesPerField.existsError('totp')>
                  <span id="input-error-otp-code" class="fsw-field-error" aria-live="polite">
                    ${kcSanitize(messagesPerField.get('totp'))?no_esc}
                  </span>
                </#if>
              </div>

              <div class="fsw-field">
                <label for="userLabel">
                  ${msg("fswTotpDevice")}
                  <#if totp.otpCredentials?size gte 1><span class="fsw-required">*</span><#else><span class="fsw-optional">${msg("fswOptional")}</span></#if>
                </label>
                <input id="userLabel" name="userLabel" type="text" autocomplete="off" placeholder="${msg("fswTotpDevicePlaceholder")}"
                       aria-invalid="<#if messagesPerField.existsError('userLabel')>true</#if>"
                       <#if messagesPerField.existsError('userLabel')>aria-describedby="input-error-otp-label"</#if>/>
                <#if messagesPerField.existsError('userLabel')>
                  <span id="input-error-otp-label" class="fsw-field-error" aria-live="polite">
                    ${kcSanitize(messagesPerField.get('userLabel'))?no_esc}
                  </span>
                </#if>
              </div>
            </div>

            <p class="fsw-inline-note"><span class="fsw-inline-note-icon"><@layout.icon name="info"/></span>${msg("fswTotpNote")}</p>

            <input type="hidden" id="totpSecret" name="totpSecret" value="${totp.totpSecret}"/>
            <#if mode??><input type="hidden" id="mode" name="mode" value="${mode}"/></#if>

            <button class="fsw-btn" id="saveTOTPBtn" type="submit">${msg("fswTotpSubmit")}</button>
            <#if isAppInitiatedAction??>
              <button class="fsw-btn fsw-btn-secondary" id="cancelTOTPBtn" name="cancel-aia" value="true" type="submit">
                ${msg("doCancel")}
              </button>
            </#if>
          </form>
        </div>
      </section>
    </main>

    <#if layout.has("fswHelpUrl")>
      <p class="fsw-help"><a class="fsw-link" href="${msg("fswHelpUrl")}" target="_blank" rel="noopener"><@layout.icon name="help"/>${msg("fswNeedHelp")}</a></p>
    </#if>
    <div class="fsw-setup-footer"><@layout.footer/></div>
  </div>

  <@layout.script/>
</body>
</html>
