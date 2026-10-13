<#-- Company email layout. Placeholders are filled in by the provisioner. -->
<#macro main>
<!DOCTYPE html>
<html lang="${locale!}">
  <body style="margin:0; padding:0; background:@@PAGE_BG@@;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:@@PAGE_BG@@;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0"
                 style="background:#ffffff; margin:24px 0; border-radius:8px;
                        box-shadow:0 2px 6px rgba(0,0,0,0.05); overflow:hidden;">
            <!-- Header -->
            <tr>
              <td style="background:@@BRAND@@; text-align:center; padding:20px; font-family:Arial,Helvetica,sans-serif;
                         font-size:20px; font-weight:bold; color:@@ON_BRAND@@;">
                ${msg("companyName")}
              </td>
            </tr>

            <!-- Body -->
            <tr>
              <td style="padding:32px;">
                <#nested>
              </td>
            </tr>

            <!-- Footer -->
            <tr>
              <td style="background:@@BRAND_TINT@@; text-align:center; padding:20px; font-size:12px; color:#6b7280;">
                &copy; ${msg("companyName")}. All rights reserved.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
</#macro>
