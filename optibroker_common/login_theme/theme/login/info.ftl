<#import "template.ftl" as layout>
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
    <#elseif (client.baseUrl)?has_content>
      <a class="fsw-btn" href="${client.baseUrl}">${msg("fswBackToApp")}</a>
    </#if>
  </#if>
</@layout.card>
