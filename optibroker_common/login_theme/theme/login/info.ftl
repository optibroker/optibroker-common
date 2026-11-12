<#import "template.ftl" as layout>
<#-- Where the company's app is: where Keycloak was asked to go back to, else
     the client's home page, else the app URL the theme was published with.
     Keycloak often has neither of the first two on an "already logged in"
     page (it shows one when the sign-in tab it belongs to has gone), so the
     theme carries its own. -->
<#assign appUrl = pageRedirectUri?has_content?then(pageRedirectUri,
                  (client.baseUrl)?has_content?then(client.baseUrl, layout.has("fswAppUrl")?then(msg("fswAppUrl"), "")))>

<#if message?has_content && message.summary == msg("alreadyLoggedIn") && appUrl?has_content>
  <#-- Someone already signed in reached a sign-in page again (an old tab, the
       back button, a link opened twice). Keycloak says "You are already logged
       in" and offers no way on; they are signed in, so take them to the app.
       The button is for a browser that blocks the redirect. -->
  <@layout.card title=msg("fswSignedInTitle") subtitle=msg("fswSignedInSubtitle")>
    <meta http-equiv="refresh" content="0;url=${appUrl}"/>
    <#-- js_string escapes quotes and "</", so the URL cannot end the script. -->
    <script>window.location.replace("${appUrl?js_string?no_esc}");</script>
    <a class="fsw-btn" style="margin-top:28px" href="${appUrl}" data-testid="already-signed-in">${msg("fswGoToApp")}</a>
  </@layout.card>
<#else>
<@layout.card title=(messageHeader?has_content)?then(messageHeader!"", msg("fswNotice"))>
  <div class="fsw-alert <#if message?has_content>${message.type}<#else>success</#if>" id="kc-info-message">
    <#if message?has_content>${kcSanitize(message.summary)?no_esc}</#if>
    <#if requiredActions??>
      <b><#list requiredActions>
        <#items as reqActionItem>${msg("requiredAction.${reqActionItem}")}<#sep>, </#sep></#items>
      </#list></b>
    </#if>
  </div>

  <#if !skipLink??>
    <#if pageRedirectUri?has_content>
      <a class="fsw-btn" href="${pageRedirectUri}">${msg("fswBackToApp")}</a>
    <#elseif actionUri?has_content>
      <a class="fsw-btn" href="${actionUri}">${msg("fswProceed")}</a>
    <#elseif appUrl?has_content>
      <a class="fsw-btn" href="${appUrl}">${msg("fswBackToApp")}</a>
    </#if>
  </#if>
</@layout.card>
</#if>
