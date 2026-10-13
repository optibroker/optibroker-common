<#import "template.ftl" as layout>
<@layout.split title=msg("fswUpdatePasswordTitle") subtitle=msg("fswUpdatePasswordSubtitle")>
  <#-- Keycloak's own prompt ("You need to change your password...") reads as
       information here; a rejected password stays an error. -->
  <#if message?has_content && !messagesPerField.existsError('password','password-confirm')>
    <div class="fsw-alert <#if message.type == 'error'>error<#else>info</#if>" role="alert">${kcSanitize(message.summary)?no_esc}</div>
  </#if>

  <form id="kc-passwd-update-form" class="fsw-form" action="${url.loginAction}" method="post"
        data-fsw-username="${(auth.attemptedUsername)!''}">
    <div class="fsw-field">
      <label for="password-new">${msg("passwordNew")}</label>
      <div class="fsw-input">
        <@layout.icon name="lock"/>
        <input id="password-new" name="password-new" type="password" autocomplete="new-password" autofocus
               placeholder="${msg("fswNewPasswordPlaceholder")}" aria-describedby="fsw-strength fsw-rules"
               aria-invalid="<#if messagesPerField.existsError('password')>true</#if>"/>
        <button type="button" class="fsw-reveal" data-fsw-reveal="password-new" aria-pressed="false"
                aria-label="${msg("fswShowPassword")}" title="${msg("fswShowPassword")}"><@layout.icon name="eye"/></button>
      </div>
      <#if messagesPerField.existsError('password')>
        <span class="fsw-field-error" aria-live="polite">${kcSanitize(messagesPerField.get('password'))?no_esc}</span>
      </#if>

      <div class="fsw-strength" id="fsw-strength" data-level="0">
        <div class="fsw-strength-bars" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
        <p class="fsw-strength-label">${msg("fswPwStrength")}<span class="fsw-strength-word" aria-live="polite"
           data-words="${msg("fswPwWeak")}|${msg("fswPwFair")}|${msg("fswPwGood")}|${msg("fswPwStrong")}"></span></p>
      </div>

      <div class="fsw-rules" id="fsw-rules">
        <p class="fsw-rules-title">${msg("fswPwRulesTitle")}</p>
        <ul>
          <li data-rule="length"><@layout.icon name="check"/>${msg("fswPwRuleLength")}</li>
          <li data-rule="mix"><@layout.icon name="check"/>${msg("fswPwRuleMix")}</li>
          <li data-rule="username"><@layout.icon name="check"/>${msg("fswPwRuleUsername")}</li>
        </ul>
      </div>
    </div>

    <div class="fsw-field">
      <label for="password-confirm">${msg("passwordConfirm")}</label>
      <div class="fsw-input">
        <@layout.icon name="lock"/>
        <input id="password-confirm" name="password-confirm" type="password" autocomplete="new-password"
               placeholder="${msg("fswConfirmPasswordPlaceholder")}"
               aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"/>
        <button type="button" class="fsw-reveal" data-fsw-reveal="password-confirm" aria-pressed="false"
                aria-label="${msg("fswShowPassword")}" title="${msg("fswShowPassword")}"><@layout.icon name="eye"/></button>
      </div>
      <span class="fsw-field-error" id="fsw-mismatch" hidden>${msg("fswPwMismatch")}</span>
      <#if messagesPerField.existsError('password-confirm')>
        <span class="fsw-field-error" aria-live="polite">${kcSanitize(messagesPerField.get('password-confirm'))?no_esc}</span>
      </#if>
    </div>

    <button class="fsw-btn" id="kc-update-password" type="submit">${msg("doSubmit")}</button>

    <#if isAppInitiatedAction?? && isAppInitiatedAction>
      <button class="fsw-btn fsw-btn-secondary" name="cancel-aia" value="true" type="submit">${msg("doCancel")}</button>
    </#if>
  </form>

  <p class="fsw-center fsw-gap"><a class="fsw-link" href="${url.loginUrl}">${msg("backToLogin")}</a></p>

  <script>
    // Strength meter and rule ticks. Keycloak's password policy is what
    // actually decides; this only shows the user how they are doing.
    (function () {
      var form = document.getElementById('kc-passwd-update-form');
      var pw = document.getElementById('password-new');
      var confirm = document.getElementById('password-confirm');
      var meter = document.getElementById('fsw-strength');
      var word = meter.querySelector('.fsw-strength-word');
      var words = word.getAttribute('data-words').split('|');
      var username = (form.getAttribute('data-fsw-username') || '').toLowerCase();
      var common = ['password', 'passw0rd', '12345678', '123456789', 'qwerty', 'qwertyuiop', 'letmein', 'welcome',
        'iloveyou', 'admin', 'abc123', 'monkey', 'dragon', 'football', 'baseball', 'sunshine', 'princess',
        'trustno1', 'mortgage', 'changeme', '11111111', '00000000', 'asdfghjk', 'zaq12wsx', 'qazwsx'];

      function rules(v) {
        return {
          length: v.length >= 8,
          mix: /[A-Za-z]/.test(v) && /\d/.test(v) && /[^A-Za-z0-9]/.test(v),
          username: v.length > 0 && (!username || v.toLowerCase() !== username)
        };
      }
      function score(v) {
        if (!v) return 0;
        var base = v.toLowerCase().replace(/[^a-z]/g, '');
        if (common.some(function (c) { return base === c.replace(/[^a-z]/g, '') && base.length > 3 || v.toLowerCase() === c; })) return 1;
        var classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(function (r) { return r.test(v); }).length;
        var s = 0;
        if (v.length >= 8) s++;
        if (v.length >= 12) s++;
        if (classes >= 3) s++;
        if (classes === 4 || v.length >= 16) s++;
        if (/(.)\1\1/.test(v)) s--;
        return Math.max(1, Math.min(4, s));
      }
      function update() {
        var v = pw.value, met = rules(v), level = score(v);
        Object.keys(met).forEach(function (k) {
          var li = document.querySelector('[data-rule="' + k + '"]');
          if (li) li.classList.toggle('is-met', met[k]);
        });
        meter.setAttribute('data-level', level);
        word.textContent = level ? ' · ' + words[level - 1] : '';
        checkMatch(false);
      }
      function checkMatch(strict) {
        var bad = confirm.value && (strict || confirm.value.length >= pw.value.length) && confirm.value !== pw.value;
        document.getElementById('fsw-mismatch').hidden = !bad;
        confirm.setAttribute('aria-invalid', bad ? 'true' : '');
      }
      pw.addEventListener('input', update);
      confirm.addEventListener('input', function () { checkMatch(false); });
      confirm.addEventListener('blur', function () { checkMatch(true); });
      update();
    })();
  </script>
</@layout.split>
