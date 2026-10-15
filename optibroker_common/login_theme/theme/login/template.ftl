<#--
  Shared pieces of the company login theme, imported by every page as
  <#import "template.ftl" as layout>. The company's branding is published into
  messages_en.properties, so everything here reads it back with msg().

  registrationLayout keeps Keycloak's own signature: pages this theme does not
  override (inherited from the parent theme) import it too, and so still get
  the company's card, logo and footer.
-->

<#-- Whether a branding message is set. msg() returns the key itself when missing. -->
<#function has key>
  <#local value = msg(key)>
  <#return value?has_content && value != key>
</#function>

<#macro head title>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="robots" content="noindex, nofollow"/>
  <title>${title} · ${msg("companyName")}</title>
  <#-- ?v= changes with every publish: Keycloak lets browsers cache this for 30 days. -->
  <link rel="stylesheet" href="${url.resourcesPath}/css/style.css?v=@@ASSET_VERSION@@"/>
</head>
</#macro>

<#-- The company's logo, or a house mark drawn in the current text colour.
     logoKey="fswPanelLogo" falls back to the main logo before the mark. -->
<#macro brandMark logoKey="fswLogo" cls="fsw-mark">
  <#if has(logoKey)>
    <img class="${cls} fsw-mark-img" src="${url.resourcesPath}/${msg(logoKey)}" alt=""/>
  <#elseif logoKey != "fswLogo" && has("fswLogo")>
    <img class="${cls} fsw-mark-img" src="${url.resourcesPath}/${msg("fswLogo")}" alt=""/>
  <#else>
    <svg class="${cls}" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3.4"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M5 23 24 6l19 17"/><path d="M10.5 18.5V42h27V18.5"/><path d="M19 42V31a5 5 0 0 1 10 0v11"/>
    </svg>
  </#if>
</#macro>

<#-- The logo and the company name beside it. A company whose logo already
     carries its name turns the name off; it is then hidden, not removed, so
     a screen reader still says whose page this is. -->
<#macro brand logoKey="fswLogo" cls="fsw-brand">
  <#local nameCls = (msg("fswShowCompanyName") == "false")?then("fsw-brand-name fsw-brand-name-hidden", "fsw-brand-name")>
  <div class="${cls}"><@brandMark logoKey=logoKey/><span class="${nameCls}">${msg("companyName")}</span></div>
</#macro>

<#macro icon name>
  <svg class="fsw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <#switch name>
    <#case "user"><circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5"/><#break>
    <#case "lock"><rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/><circle cx="12" cy="15.5" r="1.2"/><#break>
    <#case "eye"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/><#break>
    <#case "shield"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m8.8 12 2.2 2.2 4.3-4.4"/><#break>
    <#case "info"><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6v.2" stroke-width="2.2"/><#break>
    <#case "help"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.8c0 1.7-2.4 2.2-2.4 3.8"/><path d="M12 17.2v.2" stroke-width="2.2"/><#break>
    <#case "copy"><rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/><#break>
    <#case "mail"><rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="m3.5 7 8.5 6.5L20.5 7"/><#break>
    <#case "arrow"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/><#break>
    <#case "check"><path d="m5 12.5 4.5 4.5L19 7.5"/><#break>
    <#case "phone"><rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M10.5 18.5h3"/><#break>
    <#default><circle cx="12" cy="12" r="9"/>
  </#switch>
  </svg>
</#macro>

<#macro alert>
  <#if message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
    <div class="fsw-alert ${message.type}" role="alert">${kcSanitize(message.summary)?no_esc}</div>
  </#if>
</#macro>

<#macro footer>
  <footer class="fsw-footer">&copy; ${.now?string("yyyy")} ${msg("companyName")}.<#if has("fswFooterText")> ${msg("fswFooterText")}</#if></footer>
</#macro>

<#macro script>
<script>
  // Show/hide password, and copy-to-clipboard buttons. Nothing here is needed
  // to log in: without script the page works and the buttons do nothing.
  document.querySelectorAll('[data-fsw-reveal]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.getAttribute('data-fsw-reveal'));
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
    });
  });
  document.querySelectorAll('[data-fsw-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = document.getElementById(btn.getAttribute('data-fsw-copy')).textContent.replace(/\s+/g, '');
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () {
        var label = btn.querySelector('span');
        var before = label.textContent;
        label.textContent = btn.getAttribute('data-fsw-copied');
        setTimeout(function () { label.textContent = before; }, 1600);
      });
    });
  });
</script>
</#macro>

<#-- The wave panel beside (or, on a phone, behind) the card. -->
<#macro waves>
  <aside class="fsw-panel fsw-panel-waves" aria-hidden="true">
    <svg class="fsw-waves" viewBox="0 0 700 1024" preserveAspectRatio="xMidYMid slice">
      <rect width="700" height="1024" class="w0"/>
      <path class="w1" d="M470 0c-40 190 40 360 230 420V0Z"/>
      <path class="w1" d="M0 230c190 50 330 250 700 300v494H0Z"/>
      <path class="w2" d="M0 360c230 0 380 260 700 330v334H0Z"/>
      <path class="w3" d="M0 520c210-70 360 200 700 300v204H0Z"/>
      <path class="w4" d="M0 600c170-60 300 160 500 290 70 45 140 80 200 96v38H0Z"/>
      <path class="w2 soft" d="M0 760c200-70 380 40 700 200v64H0Z"/>
      <path class="w1 soft" d="M0 900c180-60 360-10 560 124H0Z"/>
    </svg>
  </aside>
</#macro>

<#-- Every page but login and authenticator setup: a card beside the wave
     panel. The forgot and new password designs have no brand row (split);
     the pages without a design of their own keep it (card). -->
<#macro split title subtitle="" showBrand=false>
<!DOCTYPE html>
<html lang="en">
<@head title=title/>
<body class="fsw-page fsw-login fsw-split">
  <@waves/>
  <div class="fsw-main">
    <main class="fsw-card">
      <#if showBrand><@brand/></#if>
      <h1 class="fsw-title">${title}</h1>
      <#if subtitle?has_content><p class="fsw-subtitle">${subtitle}</p></#if>
      <#nested>
    </main>
    <@footer/>
  </div>
  <@script/>
</body>
</html>
</#macro>

<#macro card title subtitle="">
  <@split title=title subtitle=subtitle showBrand=true><#nested></@split>
</#macro>

<#macro securityNote>
  <#if has("fswSecurityTitle") || has("fswSecurityText")>
    <div class="fsw-note">
      <span class="fsw-note-badge"><@icon name="shield"/></span>
      <div>
        <#if has("fswSecurityTitle")><p class="fsw-note-title">${msg("fswSecurityTitle")}</p></#if>
        <#if has("fswSecurityText")><p class="fsw-note-text">${msg("fswSecurityText")}</p></#if>
      </div>
    </div>
  </#if>
</#macro>

<#-- Keycloak's layout macro, for the parent theme's pages. -->
<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false displayWide=false showAnotherWayIfPresent=true>
<!DOCTYPE html>
<html lang="en">
<@head title=msg("companyName")/>
<body class="fsw-page fsw-login fsw-split ${bodyClass}">
  <@waves/>
  <div class="fsw-main">
    <main class="fsw-card fsw-kc">
      <@brand/>
      <h1 class="fsw-title"><#nested "header"></h1>
      <#if displayRequiredFields><p class="fsw-muted"><span class="fsw-required">*</span> ${msg("requiredFields")}</p></#if>
      <#if displayMessage><@alert/></#if>
      <#nested "form">
      <#if auth?has_content && auth.showTryAnotherWayLink() && showAnotherWayIfPresent>
        <form id="kc-select-try-another-way-form" action="${url.loginAction}" method="post">
          <input type="hidden" name="tryAnotherWay" value="on"/>
          <p class="fsw-center"><a class="fsw-link" href="#" id="try-another-way"
             onclick="document.forms['kc-select-try-another-way-form'].submit();return false;">${msg("doTryAnotherWay")}</a></p>
        </form>
      </#if>
      <#nested "socialProviders">
      <#if displayInfo><div class="fsw-info"><#nested "info"></div></#if>
    </main>
    <@footer/>
  </div>
  <@script/>
</body>
</html>
</#macro>

<#-- The login panel's lower half: the company's photo, or a line drawing of a
     coastal village tinted from the panel colour, or nothing. -->
<#macro panelArt>
  <#if has("fswHeroImage")>
    <img class="fsw-hero" src="${url.resourcesPath}/${msg("fswHeroImage")}" alt=""/>
  <#elseif msg("fswShowIllustration") == "true">
    <svg class="fsw-art" viewBox="0 0 640 430" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
      <g fill="none" stroke-linecap="round" stroke-linejoin="round">
        <circle class="sun" cx="540" cy="168" r="50"/>
        <#-- headland, sea and far shore -->
        <path class="a1" d="M0 96c52-22 118-30 176-18 46 10 74 34 104 60 22 19 44 30 74 36l-354 0Z"/>
        <path class="ln" d="M0 96c52-22 118-30 176-18 46 10 74 34 104 60 22 19 44 30 74 36"/>
        <path class="ln thin" d="M40 104c30-8 60-10 92-4M150 96c26 6 48 20 66 36M60 130c40-10 90-8 130 6"/>
        <path class="ln" d="M354 174H640"/>
        <path class="ln thin" d="M400 196h46M486 206h60M430 224h34M560 232h48M380 250h28"/>
        <#-- birds -->
        <path class="ln" d="M496 50q7-7 14 0q7-7 14 0M540 82q5-5 10 0q5-5 10 0M470 92q4-4 8 0q4-4 8 0"/>
        <#-- the slope down to the shore -->
        <path class="a2" d="M0 198c70-26 150-34 222-20 54 11 94 38 140 64 40 22 82 30 140 30 46 0 96-6 138-12V430H0Z"/>
        <path class="ln" d="M0 198c70-26 150-34 222-20 54 11 94 38 140 64 40 22 82 30 140 30 46 0 96-6 138-12"/>
        <#-- cottages -->
        <path class="hs" d="M-10 262 46 214l58 48v118H-10Z"/>
        <path class="ln" d="M-14 266 46 212l62 54M-4 262v118M98 262v118"/>
        <path class="ln thin" d="M0 236l40-36M10 244l46-40M22 252l44-38M34 260l40-34"/>
        <path class="ln" d="M60 300h26v36H60ZM73 300v36M60 318h26M12 300h24v34H12Z"/>
        <path class="hs" d="M112 292 166 248l54 44v94H112Z"/>
        <path class="ln" d="M108 296 166 246l58 50M116 292v94M216 292v94"/>
        <path class="ln" d="M184 236h14v26M184 236v14"/>
        <path class="ln" d="M130 318h22v30h-22ZM141 318v30M178 318h22v30h-22ZM189 318v30"/>
        <path class="hs" d="M226 312 270 276l50 36v74h-94Z"/>
        <path class="ln" d="M222 316l48-42 54 42M230 312v74M316 312v74M286 266h12v24"/>
        <path class="ln" d="M244 334h20v26h-20ZM290 334h16v22h-16Z"/>
        <path class="hs" d="M330 336 366 312l40 24v52h-76Z"/>
        <path class="ln" d="M326 338l40-28 44 28M334 336v52M402 336v52M354 352h22v18h-22Z"/>
        <#-- hedges and bushes -->
        <path class="a3" d="M-10 380c14-22 40-26 56-12 12-20 42-20 54-2 14-16 40-14 50 4 16-14 42-10 50 8 18-12 42-6 50 12 16-10 38-2 44 14 14-6 30 0 36 12v26H-10Z"/>
        <path class="ln" d="M-10 380c14-22 40-26 56-12 12-20 42-20 54-2 14-16 40-14 50 4 16-14 42-10 50 8 18-12 42-6 50 12 16-10 38-2 44 14 14-6 30 0 36 12"/>
        <path class="ln thin" d="M30 392c4-8 10-12 18-12M90 390c6-8 12-10 20-10M150 396c4-8 12-12 20-10M222 402c4-6 10-10 18-8M296 408c4-6 10-8 16-6"/>
        <path class="a3" d="M430 332c10-16 32-18 44-6 10-14 32-12 40 4 14-8 32-2 36 14 18-4 32 8 30 24 18-6 40 0 60 10V430H424Z"/>
        <path class="ln" d="M430 332c10-16 32-18 44-6 10-14 32-12 40 4 14-8 32-2 36 14 18-4 32 8 30 24 18-6 40 0 60 10"/>
        <#-- foreground grass -->
        <path class="a4" d="M0 410c120-14 260-16 400-8 90 5 170 12 240 20v8H0Z"/>
        <path class="ln" d="M0 410c120-14 260-16 400-8 90 5 170 12 240 20"/>
        <path class="ln thin" d="M40 430c-2-14 2-26 10-36M58 430c0-12 4-22 12-30M120 430c-4-16-2-28 6-40M136 430c2-12 8-20 16-26M262 430c-2-10 2-20 8-26M372 430c0-14 6-24 14-30M500 430c-4-14-2-24 6-34M516 430c2-10 6-18 14-24M590 430c-2-12 2-22 8-28"/>
      </g>
    </svg>
  </#if>
</#macro>
