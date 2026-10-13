<#import "template.ftl" as layout>
<@layout.card title=msg("fswErrorTitle") subtitle=msg("fswErrorSubtitle")>
  <div class="fsw-alert error" id="kc-error-message" role="alert">
    <#if message?has_content>${kcSanitize(message.summary)?no_esc}<#else>${msg("fswErrorDefault")}</#if>
  </div>

  <#if !skipLink?? && client?? && client.baseUrl?has_content>
    <a class="fsw-btn" id="backToApplication" href="${client.baseUrl}">${msg("fswBackToApp")}</a>
  </#if>
</@layout.card>
