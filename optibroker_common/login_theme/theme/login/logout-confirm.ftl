<#import "template.ftl" as layout>
<@layout.card title=msg("fswLogoutTitle") subtitle=msg("fswLogoutSubtitle")>
  <@layout.alert/>

  <form id="kc-logout-confirm-form" class="fsw-form" action="${url.logoutConfirmAction}" method="POST">
    <input type="hidden" name="session_code" value="${logoutConfirm.code}"/>
    <#if !(logoutConfirm.skipLink?? && logoutConfirm.skipLink) && (client.baseUrl)??>
      <input type="hidden" name="client_id" value="${client.clientId}"/>
    </#if>
    <button class="fsw-btn" type="submit" name="confirmLogout" id="kc-logout" value="true">${msg("fswLogoutButton")}</button>
  </form>

  <#if !(logoutConfirm.skipLink?? && logoutConfirm.skipLink) && (client.baseUrl)?has_content>
    <p class="fsw-center fsw-gap">
      <a class="fsw-link" href="${client.baseUrl}">${msg("fswBackToApp")}</a>
    </p>
  </#if>
</@layout.card>
