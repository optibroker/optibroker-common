<#import "layout.ftl" as layout>
<@layout.main>
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="font-family:Arial,Helvetica,sans-serif; color:#333;">
    <tr>
      <td style="text-align:center; padding:10px 0 20px;">
        <h1 style="font-size:24px; margin:0; color:@@BRAND@@;">Reset Your Password</h1>
      </td>
    </tr>
    <tr>
      <td style="font-size:16px; line-height:1.6; color:#374151;">
        <p>Hello <strong>${user.firstName!user.username}</strong>,</p>
        <p>
          We received a request to reset your ${msg("companyName")} account password.
          Click the button below to choose a new one.
        </p>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:30px 0;">
        <a href="${link}" 
           style="background-color:@@BRAND@@; color:#ffffff; text-decoration:none; 
                  padding:14px 24px; border-radius:6px; font-weight:bold; display:inline-block;">
          Reset Password
        </a>
      </td>
    </tr>
    <tr>
      <td style="font-size:15px; line-height:1.6; color:#374151;">
        <p>
          This link will expire in ${linkExpiration!} mins for your security.
          If you didn’t request a password reset, you can safely ignore this email.
        </p>
      </td>
    </tr>
    <tr>
      <td style="padding-top:20px; text-align:center; font-size:12px; color:#6b7280;">
        <p>Thank you,<br/>The ${msg("companyName")} Team</p>
      </td>
    </tr>
  </table>
</@layout.main>
