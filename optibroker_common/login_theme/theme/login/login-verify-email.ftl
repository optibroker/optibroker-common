<#import "template.ftl" as layout>
<@layout.card title=msg("fswVerifyTitle") subtitle=msg("fswVerifySubtitle")>
  <@layout.alert/>

  <p class="fsw-muted">${msg("fswVerifySent")}<#if user?? && user.email?has_content> <b>${user.email}</b></#if></p>
  <p class="fsw-muted">${msg("fswVerifyFollow")}</p>

  <p class="fsw-muted">${msg("fswVerifyNotReceived")}</p>
  <a class="fsw-btn fsw-btn-secondary" href="${url.loginAction}">${msg("fswResendEmail")}</a>

  <p class="fsw-center fsw-gap"><a class="fsw-link" href="${url.loginUrl}">${msg("backToLogin")}</a></p>
</@layout.card>
