<#import "template.ftl" as layout>
<@layout.card title=msg("fswExpiredTitle") subtitle=msg("fswExpiredSubtitle")>
  <@layout.alert/>

  <p class="fsw-muted">${msg("fswExpiredText")}</p>

  <a class="fsw-btn" id="loginRestartLink" href="${url.loginRestartFlowUrl}">${msg("fswRestartLogin")}</a>

  <p class="fsw-center fsw-gap">
    <a class="fsw-link" id="loginContinueLink" href="${url.loginAction}">${msg("fswContinueLogin")}</a>
  </p>
</@layout.card>
